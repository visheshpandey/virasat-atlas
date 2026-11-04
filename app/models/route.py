import uuid
from datetime import datetime, timezone
from sqlalchemy import ForeignKey, DateTime, Double, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_lat: Mapped[float] = mapped_column(Double, nullable=False)
    source_lng: Mapped[float] = mapped_column(Double, nullable=False)
    dest_lat: Mapped[float] = mapped_column(Double, nullable=False)
    dest_lng: Mapped[float] = mapped_column(Double, nullable=False)
    safety_score: Mapped[float] = mapped_column(Float, nullable=False)
    path: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", back_populates="routes")

    __table_args__ = (
        Index("idx_routes_safety_score", "safety_score"),
    )
