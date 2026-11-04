"""Multilingual auto-tagger for heritage text (English, Hindi, Gujarati).

Layer 1 is a deterministic rule engine and always runs. Layer 2 is optional: when
ANTHROPIC_API_KEY is set, a language model fills fields the rules left empty. Layer 2
failures are swallowed so ingest never breaks because of it.

Matching rules:
  * Latin keywords match whole words (plus simple plurals). Only keywords written with a
    trailing "*" match as a prefix, so "port" never fires inside "important" or "portrait".
  * Devanagari and Gujarati keywords match as substrings, because \\b is unreliable around
    combining vowel signs.
"""
import asyncio
import hashlib
import json
import math
import re
import time
import unicodedata
from collections import OrderedDict
from typing import Any, NamedTuple, get_args

from app.core.config import settings
from app.schemas.heritage import ERAS, THEMES, SiteType
from app.utils.logger import get_logger

logger = get_logger(__name__)

SITE_TYPES: tuple[str, ...] = get_args(SiteType)

# --------------------------------------------------------------------------- vocabulary
# name -> (latin keywords, indic keywords). A trailing "*" on a latin keyword means prefix.
_SITE_TYPE_KEYWORDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "stepwell": (
        ("stepwell", "step well", "vav", "vaav", "baoli", "baori", "bawdi", "bawri", "vaav"),
        ("वाव", "बावड़ी", "बावली", "बाउली", "વાવ", "બાવડી"),
    ),
    "fort": (
        ("fort", "fortress", "fortification", "fortified", "qila", "kila", "citadel", "bastion", "rampart"),
        ("किला", "किले", "दुर्ग", "કિલ્લ", "કિલા"),
    ),
    "temple": (
        ("temple", "mandir", "shrine", "devalaya", "mahalaya", "jyotirlinga"),
        ("मंदिर", "मन्दिर", "देवालय", "महालय", "મંદિર", "દેવાલય", "મહાલય"),
    ),
    "mosque": (
        ("mosque", "masjid", "jami", "jama"),
        ("मस्जिद", "मसजिद", "મસ્જિદ", "મસ્જીદ"),
    ),
    "mausoleum": (
        ("mausoleum", "maqbara", "makbara", "tomb", "dargah", "rauza", "dargaah"),
        ("मकबरा", "मक़बरा", "दरगाह", "મકબરો", "દરગાહ", "રોજો"),
    ),
    "palace": (
        ("palace", "mahal", "rajmahal", "darbargadh"),
        ("महल", "राजमहल", "प्रासाद", "મહેલ", "પેલેસ", "રાજમહેલ"),
    ),
    "harappan-site": (
        ("harappan", "indus valley", "indus civilisation", "indus civilization",
         "dholavira", "lothal", "archaeological site"),
        ("हड़प्पा", "सिंधु घाटी", "धोलावीरा", "लोथल", "હડપ્પા", "ધોળાવીરા", "લોથલ"),
    ),
    "craft": (
        ("patola", "weaving", "weaver*", "rogan", "bandhani", "handloom", "loom", "artisan*", "embroider*"),
        ("पटोला", "बुनाई", "बुनकर", "हस्तकला", "कारीगर", "रोगन", "પટોળા", "હસ્તકલા", "કારીગર", "રોગાન", "વણાટ"),
    ),
    "memorial": (
        ("memorial", "ashram", "samadhi", "smarak", "cenotaph"),
        ("स्मारक", "समाधि", "आश्रम", "સ્મારક", "સમાધિ", "આશ્રમ"),
    ),
}

_ERA_KEYWORDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "Harappan": (
        ("harappan", "indus valley", "indus civilisation", "indus civilization"),
        ("हड़प्पा", "सिंधु घाटी", "હડપ્પા"),
    ),
    "Maitraka": (("maitraka", "valabhi"), ("मैत्रक", "वल्लभी", "મૈત્રક", "વલભી")),
    "Chaulukya (Solanki)": (
        ("chaulukya", "chalukya", "solanki", "siddharaj", "jayasimha"),
        ("चौलुक्य", "सोलंकी", "ચૌલુક્ય", "સોલંકી"),
    ),
    "Vaghela": (("vaghela",), ("वाघेला", "વાઘેલા")),
    "Gujarat Sultanate": (
        ("sultanate", "ahmed shah", "mahmud begada", "begada", "muzaffarid"),
        ("सल्तनत", "अहमद शाह", "बेगड़ा", "સલ્તનત", "અહમદ શાહ", "બેગડા"),
    ),
    "Mughal": (
        ("mughal", "mogul", "akbar", "jahangir", "shah jahan", "aurangzeb"),
        ("मुगल", "मुग़ल", "अकबर", "शाहजहां", "औरंगज़ेब", "મુઘલ", "મુગલ", "અકબર"),
    ),
    "Princely/Maratha": (
        ("maratha", "gaekwad", "gaekwar", "princely", "nawab"),
        ("मराठा", "गायकवाड़", "नवाब", "મરાઠા", "ગાયકવાડ", "નવાબ"),
    ),
    "Colonial": (
        ("colonial", "british", "east india company", "raj"),
        ("अंग्रेज", "ब्रिटिश", "औपनिवेशिक", "અંગ્રેજ", "બ્રિટિશ"),
    ),
    "Modern": (
        ("modern", "independence", "gandhi", "freedom struggle", "salt march"),
        ("आधुनिक", "स्वतंत्रता", "गांधी", "આધુનિક", "સ્વતંત્રતા", "ગાંધી"),
    ),
}

_THEME_KEYWORDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "water-architecture": (
        ("stepwell", "step well", "vav", "baoli", "kund", "water", "tank", "reservoir", "cistern"),
        ("वाव", "बावड़ी", "बावली", "कुंड", "तालाब", "पानी", "जल", "વાવ", "કુંડ", "તળાવ", "પાણી"),
    ),
    "stone-carving": (
        ("carv*", "sculpt*", "relief", "bas-relief", "jali", "lattice", "stonework", "stone work", "toran"),
        ("नक्काशी", "तराश", "मूर्तिकला", "शिल्पकला", "કોતરણી", "શિલ્પ"),
    ),
    "pilgrimage": (
        ("pilgrim*", "yatra", "tirth", "tirtha", "devotee*", "jyotirlinga"),
        ("तीर्थ", "यात्रा", "તીર્થ", "યાત્રા"),
    ),
    "maritime-trade": (
        ("port", "seaport", "harbour", "harbor", "maritime", "trade", "trader*", "dockyard",
         "seafaring", "merchant*", "sea"),
        ("बंदरगाह", "समुद्र", "व्यापार", "બંદર", "વેપાર", "દરિયા"),
    ),
    "royalty": (
        ("king", "queen", "kingdom", "rani", "raja", "maharaja", "maharani", "sultan", "emperor",
         "nawab", "royal*", "dynast*", "ruler", "prince*"),
        ("राजा", "रानी", "महाराज", "नवाब", "शाही", "सुल्तान", "बादशाह",
         "રાજા", "રાણી", "મહારાજા", "નવાબ", "સુલતાન", "બાદશાહ"),
    ),
    "living-craft": (
        ("weav*", "patola", "rogan", "craft*", "artisan*", "bandhani", "loom", "embroider*",
         "handloom", "textile*"),
        ("बुनकर", "कारीगर", "हस्तकला", "पटोला", "बुनाई", "હસ્તકલા", "પટોળા", "કારીગર", "વણાટ"),
    ),
    "folklore": (
        ("legend*", "folklore", "folktale*", "myth*", "tale", "tales", "said to", "believed",
         "locals say", "oral tradition"),
        ("लोककथा", "किंवदंती", "दंतकथा", "मान्यता", "माना जाता", "લોકકથા", "દંતકથા", "માન્યતા", "વાયકા"),
    ),
    "unesco": (
        ("unesco", "world heritage"),
        ("यूनेस्को", "विश्व धरोहर", "યુનેસ્કો", "વિશ્વ ધરોહર"),
    ),
}

# Implied by site type, so a bare "Rani ki Vav" still gets its obvious theme.
_IMPLIED_THEMES = {"stepwell": "water-architecture", "craft": "living-craft"}


# --------------------------------------------------------------------------- matching
def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _latin_alt(keyword: str) -> str:
    """Regex alternative for one latin keyword (whole word + plurals, or prefix if starred)."""
    kw = keyword.lower()
    if kw.endswith("*"):
        return r"(?<![a-z0-9])" + re.escape(kw[:-1]) + r"[a-z]*"
    body = r"[\s-]+".join(re.escape(part) for part in kw.split())
    return r"(?<![a-z0-9])" + body + r"(?:s|es)?(?![a-z0-9])"


class _Matcher(NamedTuple):
    name: str
    latin: re.Pattern[str] | None
    indic: tuple[str, ...]

    def hits(self, text: str) -> tuple[int, int]:
        """Return (match count, first match position). Position is len(text) if no match."""
        count, first = 0, len(text)
        if self.latin is not None:
            for m in self.latin.finditer(text):
                count += 1
                first = min(first, m.start())
        for kw in self.indic:
            n = text.count(kw)
            if n:
                count += n
                first = min(first, text.find(kw))
        return count, first


def _build(table: dict[str, tuple[tuple[str, ...], tuple[str, ...]]]) -> list[_Matcher]:
    matchers = []
    for name, (latin, indic) in table.items():
        pattern = re.compile("|".join(dict.fromkeys(_latin_alt(k) for k in latin))) if latin else None
        matchers.append(_Matcher(name, pattern, tuple(dict.fromkeys(_nfc(k) for k in indic))))
    return matchers


_SITE_TYPE_MATCHERS = _build(_SITE_TYPE_KEYWORDS)
_ERA_MATCHERS = _build(_ERA_KEYWORDS)
_THEME_MATCHERS = _build(_THEME_KEYWORDS)


def _best(matchers: list[_Matcher], text: str) -> str | None:
    """Matcher with the most hits; the earliest first mention breaks ties."""
    best_name, best_key = None, None
    for m in matchers:
        count, first = m.hits(text)
        if count:
            key = (-count, first)
            if best_key is None or key < best_key:
                best_name, best_key = m.name, key
    return best_name


# --------------------------------------------------------------------------- language
def detect_language(text: str) -> str:
    """Return "hi", "gu" or "en" from the dominant Unicode script."""
    dev = guj = latin = 0
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            dev += 1
        elif 0x0A80 <= cp <= 0x0AFF:
            guj += 1
        elif ch.isalpha() and cp < 0x250:
            latin += 1
    indic = dev + guj
    if indic == 0 or indic / (indic + latin) < 0.3:
        return "en"
    return "hi" if dev >= guj else "gu"


# --------------------------------------------------------------------------- century
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("૦૧૨૩૪૫૬૭૮૯")})

_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20,
}
_BCE = r"(?:bce|bc|b\.c\.e?\.?)"
_CE = r"(?:ce|ad|a\.d\.)"
_INDIC_BCE = re.compile(r"ईसा\s*पूर्व|ई\.\s*पू|पूर्व|ઈ\.\s*સ\.\s*પૂર્વે|પૂર્વે")

_CENTURY_NUM = re.compile(
    rf"(?<![\d.])(\d{{1,2}})(?:st|nd|rd|th)?[\s-]*century(?:\s*({_BCE}|{_CE})(?![a-z]))?", re.I
)
_CENTURY_WORD = re.compile(
    rf"\b({'|'.join(_ORDINALS)})[\s-]+century(?:\s*({_BCE}|{_CE})(?![a-z]))?", re.I
)
_CENTURY_INDIC = re.compile(r"(?<![\d.])(\d{1,2})\s*[^\d\s]{0,3}\s*(?:शताब्दी|सदी|સદી)")
_YEAR = re.compile(
    rf"(?<![\d.,])(\d{{3,4}})(?![\d,]|\.\d)(?:\s*({_BCE}|{_CE})(?![a-z]))?"
    r"(?!\s*(?:km|kms|m\b|metres|meters|feet|ft|steps|pillars|people|years|sq|rs|%))",
    re.I,
)
_YEAR_INDIC_BCE = re.compile(r"(?<![\d.,])(\d{3,4})\s*(?:ईसा\s*पूर्व|ई\.\s*पू\.?|પૂર્વે|ઈ\.\s*સ\.\s*પૂર્વે)")


def _century_of(year: int) -> int:
    return math.ceil(year / 100)


def _is_bce(marker: str | None) -> bool:
    return bool(marker) and marker.lower().startswith("b")


def extract_century(text: str) -> int | None:
    """Return the century as an int (negative = BCE) from phrases or years, else None."""
    t = _nfc(text).translate(_DIGIT_MAP)

    m = _CENTURY_NUM.search(t)
    if m and 1 <= int(m.group(1)) <= 30:
        n = int(m.group(1))
        return -n if _is_bce(m.group(2)) else n
    m = _CENTURY_WORD.search(t)
    if m:
        n = _ORDINALS[m.group(1).lower()]
        return -n if _is_bce(m.group(2)) else n
    m = _CENTURY_INDIC.search(t)
    if m and 1 <= int(m.group(1)) <= 30:
        window = t[max(0, m.start() - 14): m.end() + 14]
        n = int(m.group(1))
        return -n if _INDIC_BCE.search(window) else n

    m = _YEAR_INDIC_BCE.search(t)
    if m:
        return -_century_of(int(m.group(1)))
    for m in _YEAR.finditer(t):
        year, marker = int(m.group(1)), m.group(2)
        if _is_bce(marker):
            return -_century_of(year)
        if marker or 500 <= year <= 2100:
            return _century_of(year)
    return None


# --------------------------------------------------------------------------- layer 1
def tag_rules(text: str) -> dict:
    """Layer 1. Return TagOut-shaped dict: site_type, era, century, themes, language, source."""
    t = _nfc(text).lower()
    site_type = _best(_SITE_TYPE_MATCHERS, t)
    era = _best(_ERA_MATCHERS, t)

    found = {m.name for m in _THEME_MATCHERS if m.hits(t)[0]}
    if site_type in _IMPLIED_THEMES:
        found.add(_IMPLIED_THEMES[site_type])
    themes = [th for th in THEMES if th in found]

    return {
        "site_type": site_type,
        "era": era,
        "century": extract_century(text),
        "themes": themes,
        "language": detect_language(text),
        "source": "rules",
    }


# --------------------------------------------------------------------------- layer 2
_CACHE_TTL_OK = 600.0   # 10 minutes
_CACHE_TTL_FAIL = 60.0  # do not hammer a failing API
_CACHE_MAX = 256
_cache: "OrderedDict[str, tuple[float, dict | None]]" = OrderedDict()

_SYSTEM_PROMPT = (
    "You classify short heritage field notes about Gujarat, India (English, Hindi or Gujarati). "
    "Reply with ONE JSON object and nothing else, with keys: "
    f'"site_type" (one of {list(SITE_TYPES)} or null), '
    f'"era" (one of {list(ERAS)} or null), '
    '"century" (integer, negative for BCE, or null), '
    f'"themes" (list drawn only from {list(THEMES)}). Use null when unsure.'
)


def _clean_model_output(raw: Any) -> dict | None:
    """Validate model output against our vocabulary; drop anything unexpected."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, Any] = {}
    if raw.get("site_type") in SITE_TYPES:
        out["site_type"] = raw["site_type"]
    if raw.get("era") in ERAS:
        out["era"] = raw["era"]
    century = raw.get("century")
    if isinstance(century, int) and not isinstance(century, bool) and -30 <= century <= 21 and century != 0:
        out["century"] = century
    themes = raw.get("themes")
    if isinstance(themes, list):
        out["themes"] = [x for x in themes if x in THEMES]
    return out


def _parse_json_object(text: str) -> Any:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    return json.loads(text[start: end + 1])


async def _call_claude(text: str) -> dict | None:
    """Ask the model for tags. Raises on any API problem; the caller handles it."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=10.0, max_retries=1)
    message = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text[:4000]}],
    )
    raw = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    return _clean_model_output(_parse_json_object(raw))


def _merge(rules: dict, extra: dict) -> dict:
    """Fill fields the rules left empty; never overwrite what the rules found."""
    merged = dict(rules)
    for key in ("site_type", "era", "century"):
        if merged.get(key) is None and extra.get(key) is not None:
            merged[key] = extra[key]
    union = set(rules["themes"]) | set(extra.get("themes", []))
    merged["themes"] = [th for th in THEMES if th in union]
    merged["source"] = "rules+claude"
    return merged


def _cache_get(key: str) -> tuple[bool, dict | None]:
    entry = _cache.get(key)
    if entry is None:
        return False, None
    expires, value = entry
    if expires < time.monotonic():
        _cache.pop(key, None)
        return False, None
    _cache.move_to_end(key)
    return True, value


def _cache_put(key: str, value: dict | None) -> None:
    ttl = _CACHE_TTL_OK if value is not None else _CACHE_TTL_FAIL
    _cache[key] = (time.monotonic() + ttl, value)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


async def tag_text(text: str) -> dict:
    """Layer 1 plus the optional model layer. Never raises because of the model call."""
    rules = tag_rules(text)
    if not settings.ANTHROPIC_API_KEY or not text.strip():
        return rules

    key = hashlib.sha256(text.encode("utf-8")).hexdigest()
    hit, extra = _cache_get(key)
    if not hit:
        try:
            extra = await asyncio.wait_for(_call_claude(text), timeout=15.0)
        except Exception as exc:  # network, auth, rate limit, bad JSON: all fall back to rules
            logger.warning(f"model_tagging_failed error={type(exc).__name__}")
            extra = None
        _cache_put(key, extra)
    return _merge(rules, extra) if extra is not None else rules
