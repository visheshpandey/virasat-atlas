"""A heritage site on the map."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Double, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    site_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    era: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    century: Mapped[int | None] = mapped_column(Integer, nullable=True)  # negative = BCE
    district: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lng: Mapped[float] = mapped_column(Double, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    folklore: Mapped[str | None] = mapped_column(Text, nullable=True)
    themes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    unesco: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    entries = relationship("Entry", back_populates="site")
