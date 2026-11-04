"""Field entry ingest: image validation, auto-tagging and nearest-site attachment."""
import io
import os
import uuid
from pathlib import Path
from typing import get_args

from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entry import Entry
from app.models.site import Site
from sqlalchemy import func, select

from app.schemas.heritage import EntryKind, EntryOut, EntryList, TagOut
from app.services import tagger
from app.utils.logger import get_logger
from app.utils.states import state_key

logger = get_logger(__name__)

AUTO_ATTACH_KM = 2.0
# Raster formats only. SVG can carry script and is deliberately absent.
IMAGE_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}


def entry_out(entry: Entry, auto_attached: bool = False) -> EntryOut:
    out = EntryOut.model_validate(entry)
    out.auto_attached = auto_attached
    return out


async def read_upload(upload: UploadFile) -> bytes:
    """Read an upload fully, raising 413 once it exceeds MAX_UPLOAD_MB."""
    data = await upload.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413, detail=f"Upload limit is {settings.MAX_UPLOAD_MB} MB"
        )
    return data


def verify_image(data: bytes) -> str:
    """Confirm the bytes are a real raster image and return its file extension.

    The client's filename and content type are ignored: only Pillow's own
    detection of the content counts.
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            img.verify()
    except Exception:
        raise HTTPException(status_code=415, detail="File is not a valid image")
    if fmt not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=415, detail="Unsupported image type. Use JPEG, PNG, WebP or GIF"
        )
    return IMAGE_EXTENSIONS[fmt]


def save_image(data: bytes, extension: str) -> str:
    """Write the image under a random name in MEDIA_DIR and return that filename."""
    name = f"{uuid.uuid4().hex}{extension}"
    media = Path(settings.MEDIA_DIR)
    media.mkdir(parents=True, exist_ok=True)
    (media / name).write_bytes(data)
    return name


def _parse_float(raw: str | None, name: str, low: float, high: float) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be a number")
    if not low <= value <= high:
        raise HTTPException(status_code=422, detail=f"{name} must be between {low} and {high}")
    return value


async def _tags_for(text: str) -> TagOut:
    """Run the tagger. Ingest must not fail because tagging did."""
    try:
        return TagOut(**await tagger.tag_text(text))
    except Exception as exc:
        logger.error(f"tagging_failed: {exc}", exc_info=exc)
        try:
            return TagOut(language=tagger.detect_language(text))
        except Exception:
            return TagOut()


async def create_entry(
    db: AsyncSession,
    *,
    title: str,
    body: str,
    kind: str,
    author: str | None,
    site_id: str | None,
    lat: str | None,
    lng: str | None,
    image: UploadFile | None,
    state: str | None = None,
) -> EntryOut:
    """Validate, tag, attach to a site and store one field entry.

    Without a site_id but with coordinates, the entry joins the nearest site
    within AUTO_ATTACH_KM. A missing `state` is filled from the attached site, else from the
    nearest site at any distance. The search index is rebuilt after the write.
    """
    # Imported here: site_service imports this module for entry_out.
    from app.services.site_service import canonical_state, nearest_site, nearest_state, reindex

    if kind not in get_args(EntryKind):
        raise HTTPException(
            status_code=422, detail=f"kind must be one of: {', '.join(get_args(EntryKind))}"
        )
    author = (author or "").strip() or None
    if author and len(author) > 100:
        raise HTTPException(status_code=422, detail="author must be at most 100 characters")

    lat_v = _parse_float(lat, "lat", -90, 90)
    lng_v = _parse_float(lng, "lng", -180, 180)
    if (lat_v is None) != (lng_v is None):
        raise HTTPException(status_code=422, detail="lat and lng must be given together")

    site: Site | None = None
    site_uuid: uuid.UUID | None = None
    if site_id and site_id.strip():
        try:
            site_uuid = uuid.UUID(site_id.strip())
        except ValueError:
            raise HTTPException(status_code=422, detail="site_id is not a valid UUID")
        site = await db.get(Site, site_uuid)
        if site is None:
            raise HTTPException(status_code=404, detail="Site not found")

    auto_attached = False
    if site is None and lat_v is not None and lng_v is not None:
        site = await nearest_site(db, lat_v, lng_v, AUTO_ATTACH_KM)
        auto_attached = site is not None

    if len((state or "").strip()) > 60:
        raise HTTPException(status_code=422, detail="state must be at most 60 characters")
    state = await canonical_state(db, state)
    if state is None:
        if site is not None:
            state = site.state
        elif lat_v is not None and lng_v is not None:
            state = await nearest_state(db, lat_v, lng_v)

    image_name: str | None = None
    if image is not None and image.filename:
        data = await read_upload(image)
        if data:
            image_name = save_image(data, verify_image(data))

    tags = await _tags_for(f"{title}\n{body}")
    entry = Entry(
        site_id=site.id if site else None,
        title=title.strip(),
        body=body,
        kind=kind,
        language=tags.language,
        author=author,
        state=state,
        lat=lat_v,
        lng=lng_v,
        image_path=image_name,
        tags=tags.model_dump(),
    )
    db.add(entry)
    try:
        await db.commit()
    except Exception:
        if image_name:
            os.remove(Path(settings.MEDIA_DIR) / image_name)
        raise
    await db.refresh(entry)
    logger.info(f"entry_created id={entry.id} kind={kind} site={entry.site_id} auto={auto_attached}")
    await reindex(db)
    return entry_out(entry, auto_attached)


async def list_entries(
    db: AsyncSession, state: str | None = None, unattached: bool = False, limit: int = 500
) -> EntryList:
    """Newest entries first. `unattached` keeps entries with coordinates but no site (map dots)."""
    stmt = select(Entry).order_by(Entry.created_at.desc()).limit(limit)
    key = state_key(state)
    if key:
        stmt = stmt.where(func.lower(Entry.state) == key)
    if unattached:
        stmt = stmt.where(Entry.site_id.is_(None), Entry.lat.is_not(None), Entry.lng.is_not(None))
    items = [entry_out(e) for e in (await db.execute(stmt)).scalars().all()]
    return EntryList(items=items, total=len(items))


async def get_entry(db: AsyncSession, entry_id: uuid.UUID) -> EntryOut:
    """One entry by id, or 404."""
    entry = await db.get(Entry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry_out(entry)
