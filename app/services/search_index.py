"""Hybrid in-memory search index. Not yet implemented."""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


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


class SearchIndex:
    def rebuild(self, docs: list[SearchDoc]) -> None:
        """Fit vectorizers and swap the new index in atomically."""
        raise NotImplementedError

    def search(self, query: str, k: int = 10) -> list[dict]:
        """Return SearchResult-shaped dicts, best first, only with score > 0."""
        raise NotImplementedError


index = SearchIndex()


async def rebuild_from_db(db: AsyncSession) -> None:
    """Load all sites and entries and rebuild `index`. An entry with no lat/lng uses its site's."""
    raise NotImplementedError
