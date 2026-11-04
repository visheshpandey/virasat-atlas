"""Async engine and session factory. Works with both PostgreSQL and SQLite."""
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_pool_args = {"pool_size": 5, "max_overflow": 15} if settings.is_postgres else {}

engine = create_async_engine(settings.DATABASE_URL, echo=False, **_pool_args)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    async with AsyncSessionLocal() as session:
        yield session
