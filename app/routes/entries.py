"""Field entry endpoints. Submission is open: the capture form has no login."""
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.heritage import EntryOut
from app.services import entry_service

router = APIRouter(prefix="/entries", tags=["entries"])


@router.post("", response_model=EntryOut, status_code=201)
async def create_entry(
    title: str = Form(min_length=1, max_length=300),
    body: str = Form(default="", max_length=50000),
    kind: str = Form(default="journal"),
    author: str | None = Form(default=None),
    site_id: str | None = Form(default=None),
    lat: str | None = Form(default=None),
    lng: str | None = Form(default=None),
    image: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
) -> EntryOut:
    """Ingest a field entry (multipart form).

    The text is auto-tagged. Without site_id but with lat/lng, the entry is attached
    to the nearest site within 2 km; `auto_attached` in the response says so.
    """
    return await entry_service.create_entry(
        db,
        title=title,
        body=body,
        kind=kind,
        author=author,
        site_id=site_id,
        lat=lat,
        lng=lng,
        image=image,
    )


@router.get("/{entry_id}", response_model=EntryOut)
async def get_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> EntryOut:
    """One entry by id."""
    return await entry_service.get_entry(db, entry_id)
