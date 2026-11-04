"""A field entry: a journal note, photo, document, folklore record or OCR text."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Double, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="journal")
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lat: Mapped[float | None] = mapped_column(Double, nullable=True)
    lng: Mapped[float | None] = mapped_column(Double, nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    site = relationship("Site", back_populates="entries")

    @property
    def image_url(self) -> str | None:
        """Public URL of the uploaded image. image_path is a filename inside MEDIA_DIR."""
        return f"/media/{self.image_path}" if self.image_path else None
