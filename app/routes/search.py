"""Semantic search over sites and field entries."""
import unicodedata

from fastapi import APIRouter, Query

from app.schemas.heritage import SearchResponse, SearchResult
from app.services.search_index import index

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(min_length=1, max_length=200),
    k: int = Query(default=10, ge=1, le=50),
) -> SearchResponse:
    """Hybrid word and character TF-IDF search; handles Hindi, Gujarati and typos."""
    query = unicodedata.normalize("NFC", q).strip()
    if not query:
        return SearchResponse(query=q, results=[])
    return SearchResponse(
        query=q, results=[SearchResult(**hit) for hit in index.search(query, k)]
    )
