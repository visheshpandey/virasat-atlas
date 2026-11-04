"""Hybrid in-memory search over sites and field entries.

Score = 0.6 * word TF-IDF (1-2 grams) + 0.4 * char TF-IDF (3-5 grams inside words). The
character layer is what makes Hindi, Gujarati, transliteration and typos work. If
SEMANTIC_MODEL is set and sentence-transformers is installed, a dense multilingual layer is
fused 50/50 with the lexical score.

The index is rebuilt as a whole and swapped in with one assignment, so searches running
during a rebuild see either the old index or the new one, never a mix.
"""
import asyncio
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.utils.logger import get_logger
from app.utils.states import state_key

logger = get_logger(__name__)

WORD_WEIGHT = 0.6
CHAR_WEIGHT = 0.4
DEFAULT_DENSE_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
MIN_SCORE = 0.03        # absolute floor
RELATIVE_FLOOR = 0.2    # drop results scoring under 20% of the best one
SNIPPET_WIDTH = 180
_QUERY_CACHE_MAX = 256

# Word characters plus the Devanagari and Gujarati blocks. Python's \w skips combining
# vowel signs, which would split Indic words apart. Danda marks (U+0964, U+0965) are excluded.
_TOKEN_CHARS = r"\wऀ-ॣ०-ॿ઀-૯"
_TOKEN_RE = re.compile(f"[{_TOKEN_CHARS}]+")
_NON_TOKEN_RE = re.compile(f"[^{_TOKEN_CHARS}]+")


def normalize(text: str) -> str:
    """NFC-normalise, lowercase and turn punctuation into spaces."""
    return _NON_TOKEN_RE.sub(" ", unicodedata.normalize("NFC", text).lower()).strip()


def tokenize(text: str) -> list[str]:
    """Split already-normalised text into tokens, keeping Indic words whole."""
    return _TOKEN_RE.findall(text)


@dataclass
class SearchDoc:
    kind: str  # "site" or "entry"
    id: str
    site_id: str | None
    title: str
    text: str  # full searchable text, also the source of snippets
    lat: float | None
    lng: float | None
    language: str
    state: str | None = None


@dataclass
class _State:
    docs: list[SearchDoc]
    version: int
    word_vec: TfidfVectorizer | None = None
    word_mat: object = None
    char_vec: TfidfVectorizer | None = None
    char_mat: object = None
    dense: "np.ndarray | None" = None
    cache: "OrderedDict[tuple, list[dict]]" = field(default_factory=OrderedDict)


def make_snippet(text: str, query: str, width: int = SNIPPET_WIDTH) -> str:
    """Plain-text excerpt around the first query match (exact, then 4-char prefix)."""
    flat = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()
    if len(flat) <= width:
        return flat
    low = flat.lower()
    pos = -1
    if len(low) == len(flat):
        tokens = sorted((t for t in tokenize(normalize(query)) if len(t) > 1), key=len, reverse=True)
        for token in tokens:
            pos = low.find(token)
            if pos >= 0:
                break
        if pos < 0:
            for token in tokens:
                if len(token) >= 4 and (pos := low.find(token[:4])) >= 0:
                    break
    start = max(0, pos - width // 3) if pos >= 0 else 0
    if start > 0:
        space = flat.rfind(" ", 0, start + 1)
        start = space + 1 if space >= 0 else 0
    end = min(len(flat), start + width)
    if end < len(flat):
        space = flat.find(" ", end)
        end = space if 0 <= space - end < 20 else end
    return ("…" if start > 0 else "") + flat[start:end].strip() + ("…" if end < len(flat) else "")


class SearchIndex:
    """In-memory hybrid index. Safe to search from request handlers while rebuilding."""

    def __init__(self) -> None:
        self._state = _State(docs=[], version=0)
        self._version = 0
        self._model = None
        self._dense_failed = False

    # ---- dense layer (optional) ----
    def _dense_model(self):
        name = settings.SEMANTIC_MODEL.strip()
        if not name or self._dense_failed:
            return None
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                model_name = DEFAULT_DENSE_MODEL if name.lower() in {"1", "true", "yes", "on"} else name
                self._model = SentenceTransformer(model_name)
            except Exception as exc:  # missing package, offline, bad model name
                logger.warning(f"dense_search_disabled error={type(exc).__name__}")
                self._dense_failed = True
                return None
        return self._model

    def _encode(self, texts: list[str]) -> "np.ndarray | None":
        model = self._dense_model()
        if model is None:
            return None
        try:
            return np.asarray(model.encode(texts, normalize_embeddings=True, show_progress_bar=False))
        except Exception as exc:
            logger.warning(f"dense_encode_failed error={type(exc).__name__}")
            self._dense_failed = True
            return None

    # ---- build ----
    def rebuild(self, docs: list[SearchDoc]) -> None:
        """Fit vectorizers and swap the new index in atomically."""
        self._version += 1
        state = _State(docs=list(docs), version=self._version)
        # Titles are repeated so a title match outranks a passing mention in the body.
        texts = [normalize(f"{d.title} {d.title} {d.text}") for d in state.docs]
        if texts and any(texts):
            try:
                state.word_vec = TfidfVectorizer(
                    tokenizer=tokenize, token_pattern=None, lowercase=False,
                    ngram_range=(1, 2), sublinear_tf=True,
                )
                state.word_mat = state.word_vec.fit_transform(texts)
                state.char_vec = TfidfVectorizer(
                    analyzer="char_wb", ngram_range=(3, 5), lowercase=False, sublinear_tf=True,
                )
                state.char_mat = state.char_vec.fit_transform(texts)
                state.dense = self._encode(texts)
            except ValueError:  # empty vocabulary
                state = _State(docs=list(docs), version=self._version)
        self._state = state

    # ---- query ----
    def search(self, query: str, k: int = 10, region: str | None = None) -> list[dict]:
        """Return SearchResult-shaped dicts, best first, only with score > 0.

        `region` limits results to documents in that state (name or slug).
        """
        state = self._state
        q = normalize(query)
        if not q or state.word_vec is None or not state.docs:
            return []

        key_state = state_key(region)
        key = (q, k, key_state)
        if key in state.cache:
            state.cache.move_to_end(key)
            return [dict(r) for r in state.cache[key]]

        word = (state.word_mat @ state.word_vec.transform([q]).T).toarray().ravel()
        char = (state.char_mat @ state.char_vec.transform([q]).T).toarray().ravel()
        score = WORD_WEIGHT * word + CHAR_WEIGHT * char
        if state.dense is not None:
            qv = self._encode([q])
            if qv is not None:
                dense = np.clip(state.dense @ qv[0], 0.0, None)
                score = 0.5 * score + 0.5 * dense

        if key_state:
            mask = np.array([(d.state or "").lower() == key_state for d in state.docs], dtype=float)
            score = score * mask

        results: list[dict] = []
        order = np.argsort(-score, kind="stable")
        top = float(score[order[0]]) if len(order) else 0.0
        floor = max(MIN_SCORE, RELATIVE_FLOOR * top)
        for idx in order[: max(k, 0)]:
            value = float(score[idx])
            if value <= 0 or value < floor:
                break
            doc = state.docs[int(idx)]
            results.append({
                "kind": doc.kind,
                "id": doc.id,
                "site_id": doc.id if doc.kind == "site" else doc.site_id,
                "title": doc.title,
                "snippet": make_snippet(doc.text, query),
                "score": round(value, 4),
                "lat": doc.lat,
                "lng": doc.lng,
                "language": doc.language,
            })

        state.cache[key] = [dict(r) for r in results]
        while len(state.cache) > _QUERY_CACHE_MAX:
            state.cache.popitem(last=False)
        return results


index = SearchIndex()


def _join(*parts: object) -> str:
    return " ".join(str(p) for p in parts if p)


async def rebuild_from_db(db: AsyncSession) -> None:
    """Load all sites and entries and rebuild `index`. An entry with no lat/lng uses its site's."""
    from app.models.entry import Entry
    from app.models.site import Site

    sites = (await db.execute(select(Site))).scalars().all()
    entries = (await db.execute(select(Entry))).scalars().all()
    by_id = {s.id: s for s in sites}

    docs: list[SearchDoc] = []
    for s in sites:
        docs.append(SearchDoc(
            kind="site", id=str(s.id), site_id=str(s.id), title=s.name,
            text=_join(s.description, s.folklore, s.site_type, s.era, s.district, *(s.themes or [])),
            lat=s.lat, lng=s.lng, language="en", state=s.state,
        ))
    for e in entries:
        site = by_id.get(e.site_id) if e.site_id else None
        tags = e.tags or {}
        docs.append(SearchDoc(
            kind="entry", id=str(e.id), site_id=str(e.site_id) if e.site_id else None, title=e.title,
            text=_join(e.body, site.name if site else None, tags.get("site_type"), tags.get("era"),
                       *(tags.get("themes") or [])),
            lat=e.lat if e.lat is not None else (site.lat if site else None),
            lng=e.lng if e.lng is not None else (site.lng if site else None),
            language=e.language, state=e.state or (site.state if site else None),
        ))
    await asyncio.to_thread(index.rebuild, docs)
    logger.info(f"search_index_rebuilt docs={len(docs)}")
