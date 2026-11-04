"""Frozen API contract for sites, entries, tagging, search, trails, OCR and meta.

Errors from every endpoint use one envelope:
    {"error": {"code": "NOT_FOUND", "message": "...", "detail": null}}
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SiteType = Literal[
    "stepwell", "fort", "temple", "mosque", "mausoleum",
    "palace", "harappan-site", "craft", "memorial",
]
EntryKind = Literal["journal", "photo", "document", "folklore", "ocr"]
Language = Literal["en", "hi", "gu"]

ERAS: tuple[str, ...] = (
    "Harappan", "Maitraka", "Chaulukya (Solanki)", "Vaghela", "Gujarat Sultanate",
    "Mughal", "Princely/Maratha", "Colonial", "Modern",
)
THEMES: tuple[str, ...] = (
    "water-architecture", "stone-carving", "pilgrimage", "maritime-trade",
    "royalty", "living-craft", "folklore", "unesco",
)


# --- Tagging ---
class TagRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class TagOut(BaseModel):
    site_type: SiteType | None = None
    era: str | None = None
    century: int | None = None  # negative = BCE
    themes: list[str] = []
    language: Language = "en"
    source: str = "rules"  # "rules" or "rules+gemini"


# --- Entries ---
class EntryOut(BaseModel):
    """POST /entries takes multipart form fields, so there is no JSON create schema."""
    id: uuid.UUID
    site_id: uuid.UUID | None
    title: str
    body: str
    kind: EntryKind
    language: Language
    author: str | None
    lat: float | None
    lng: float | None
    image_url: str | None
    tags: TagOut
    created_at: datetime
    auto_attached: bool = False  # true when site_id came from the nearest-site lookup

    model_config = {"from_attributes": True}


# --- Sites ---
class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    site_type: SiteType
    era: str | None = None
    century: int | None = Field(default=None, ge=-30, le=21)
    district: str | None = None
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    description: str = ""
    folklore: str | None = None
    themes: list[str] = []
    unesco: bool = False


class SiteOut(BaseModel):
    id: uuid.UUID
    name: str
    site_type: SiteType
    era: str | None
    century: int | None
    district: str | None
    lat: float
    lng: float
    description: str
    folklore: str | None
    themes: list[str]
    unesco: bool
    created_at: datetime
    entry_count: int = 0

    model_config = {"from_attributes": True}


class SiteDetail(SiteOut):
    entries: list[EntryOut] = []


class NearbySite(SiteOut):
    distance_km: float


class SiteImage(BaseModel):
    """A representative photo from Wikipedia or Wikimedia Commons; all null when none was found."""
    image_url: str | None = None
    page_url: str | None = None  # where the photo and its licence can be seen
    title: str | None = None
    source: str | None = None


class SiteList(BaseModel):
    items: list[SiteOut]
    total: int


class NearbyList(BaseModel):
    items: list[NearbySite]
    total: int
    radius_km: float


# --- Meta ---
class FacetCount(BaseModel):
    value: str
    count: int


class MetaOut(BaseModel):
    types: list[FacetCount]
    eras: list[FacetCount]
    themes: list[FacetCount]
    languages: list[FacetCount]  # counted over entries
    sites: int
    entries: int


# --- Search ---
class SearchResult(BaseModel):
    kind: Literal["site", "entry"]
    id: uuid.UUID
    site_id: uuid.UUID | None  # for a site result, equal to id
    title: str
    snippet: str  # plain text, not HTML; the frontend escapes it and highlights terms
    score: float
    lat: float | None
    lng: float | None
    language: Language


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


# --- Trails ---
class TrailRequest(BaseModel):
    site_ids: list[uuid.UUID] | None = None
    theme: str | None = None
    start_lat: float | None = Field(default=None, ge=-90, le=90)
    start_lng: float | None = Field(default=None, ge=-180, le=180)
    max_stops: int = Field(default=8, ge=2, le=15)

    @model_validator(mode="after")
    def _start_needs_both(self) -> "TrailRequest":
        if (self.start_lat is None) != (self.start_lng is None):
            raise ValueError("start_lat and start_lng must be given together")
        return self


class TrailStop(BaseModel):
    order: int  # 1-based
    id: uuid.UUID
    name: str
    site_type: str
    lat: float
    lng: float


class TrailResponse(BaseModel):
    stops: list[TrailStop]
    leg_km: list[float]  # includes start->first stop when a start was given
    total_km: float  # straight-line distance
    est_hours: float  # total_km / 45 + 1 hour per stop
    polyline: list[list[float]]  # [lat, lng] pairs, ready for Leaflet


# --- OCR ---
class OcrOut(BaseModel):
    text: str
    language: Language
    tags: TagOut
