"""Auto-tagger endpoint, used for the live tag preview while typing."""
from fastapi import APIRouter

from app.schemas.heritage import TagOut, TagRequest
from app.services import tagger

router = APIRouter(tags=["tagging"])


@router.post("/tag", response_model=TagOut)
async def tag(data: TagRequest) -> TagOut:
    """Return site type, era, century, themes and language detected in the text."""
    return TagOut(**await tagger.tag_text(data.text))
