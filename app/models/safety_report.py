import uuid
from datetime import datetime, timezone
from sqlalchemy import ForeignKey, DateTime, Double, String, Text, Index, Computed
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geography
from app.db.base import Base


class SafetyReport(Base):
    __tablename__ = "safety_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    latitude: Mapped[float] = mapped_column(Double, nullable=False)
    longitude: Mapped[float] = mapped_column(Double, nullable=False)
    geog = mapped_column(
        Geography(geometry_type='POINT', srid=4326),
        Computed("ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography"),
        index=True
    )
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    user = relationship("User", back_populates="safety_reports")

    __table_args__ = (
        Index("idx_reports_created_at", "created_at"),
    )
