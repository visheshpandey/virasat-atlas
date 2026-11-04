"""Schema creation, shared by app startup and the seed script.

lat/lng columns are the source of truth on every database. On PostgreSQL a generated
geography column and GIST index are added on top, so nearby queries can use ST_DWithin.
SQLite has neither and falls back to Haversine in Python.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

_GEO_TABLES = ("sites", "entries")


async def _apply_postgis(conn: AsyncConnection) -> None:
    """Add the PostGIS column and spatial index. Safe to run repeatedly."""
    for table in _GEO_TABLES:
        await conn.execute(text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS geog geography(Point, 4326) "
            "GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography) STORED"
        ))
        await conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_geog ON {table} USING GIST (geog)"
        ))


async def _add_state_columns(conn: AsyncConnection) -> None:
    """Add the `state` column to databases created before regions existed, then backfill.

    Sites that predate the column were all Gujarat. Entries inherit their site's state.
    """
    for table in ("sites", "entries"):
        if settings.is_postgres:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS state VARCHAR(60)"))
        else:
            columns = (await conn.execute(text(f"PRAGMA table_info({table})"))).all()
            if "state" not in {c[1] for c in columns}:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN state VARCHAR(60)"))
        await conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_state ON {table} (state)"))
    await conn.execute(text("UPDATE sites SET state = 'Gujarat' WHERE state IS NULL"))
    await conn.execute(text(
        "UPDATE entries SET state = (SELECT s.state FROM sites s WHERE s.id = entries.site_id) "
        "WHERE state IS NULL AND site_id IS NOT NULL"
    ))


async def init_db() -> None:
    """Create all tables, plus spatial columns when running on PostGIS."""
    async with engine.begin() as conn:
        if settings.is_postgres:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)
        await _add_state_columns(conn)
        if settings.is_postgres:
            await _apply_postgis(conn)


async def drop_db() -> None:
    """Drop all tables. Only used by `scripts/seed.py --reset`."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
