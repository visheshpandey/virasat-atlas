"""Auto-tagger endpoint, used for the live tag preview while typing."""
from fastapi import APIRouter

from app.schemas.heritage import TagOut, TagRequest
from app.services import tagger

# The live preview fires while the user types, so it must not wait long on the model.
PREVIEW_TIMEOUT_SECONDS = 3.0

router = APIRouter(tags=["tagging"])


@router.post("/tag", response_model=TagOut)
async def tag(data: TagRequest) -> TagOut:
    """Return site type, era, century, themes and language detected in the text."""
    return TagOut(**await tagger.tag_text(data.text, timeout=PREVIEW_TIMEOUT_SECONDS))
