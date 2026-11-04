"""Checks on the demo seed data and that it loads into an empty database."""
import asyncio
import tempfile
from pathlib import Path
from typing import get_args

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models import Entry, Site, User
from app.schemas.heritage import ERAS, THEMES, SiteType
from scripts import seed

LAT_RANGE = (20.0, 24.8)
LNG_RANGE = (68.0, 74.6)


def _script_chars(text: str, lo: int, hi: int) -> int:
    return sum(1 for ch in text if lo <= ord(ch) <= hi)


def test_site_count_and_required_names():
    assert len(seed.SITES) == 24
    names = {s["name"] for s in seed.SITES}
    for required in ("Rani ki Vav", "Dholavira", "Lothal", "Somnath Temple", "Bhadra Fort",
                     "Adi Kadi Vav", "Uparkot Fort", "Prag Mahal", "Aina Mahal"):
        assert required in names
    assert len(names) == len(seed.SITES), "duplicate site names"


def test_all_sites_inside_gujarat_bounding_box():
    for s in seed.SITES:
        assert LAT_RANGE[0] <= s["lat"] <= LAT_RANGE[1], s["name"]
        assert LNG_RANGE[0] <= s["lng"] <= LNG_RANGE[1], s["name"]


def test_site_fields_are_valid():
    valid_types = set(get_args(SiteType))
    for s in seed.SITES:
        assert s["site_type"] in valid_types, s["name"]
        assert -30 <= s["century"] <= 21, s["name"]
        assert s["description"], s["name"]
        assert set(s["themes"]) <= set(THEMES), (s["name"], s["themes"])
        if s["unesco"]:
            assert "unesco" in s["themes"], s["name"]
    harappan = [s for s in seed.SITES if s["era"] == "Harappan"]
    assert harappan and all(s["century"] < 0 for s in harappan)
    assert {s["era"] for s in seed.SITES if s["era"] in ERAS}, "no era from the standard list"


def test_unesco_sites_flagged():
    flagged = {s["name"] for s in seed.SITES if s["unesco"]}
    assert {"Rani ki Vav", "Dholavira", "Champaner-Pavagadh Archaeological Park"} <= flagged


def test_entries_language_mix_matches_script():
    entries = seed.ENTRIES
    assert len(entries) == 12
    langs = [e["language"] for e in entries]
    assert langs.count("hi") == 3 and langs.count("gu") == 1
    for e in entries:
        assert e["author"].startswith(seed.DEMO_AUTHOR_PREFIX)
        hi = _script_chars(e["body"], *seed.DEVANAGARI)
        gu = _script_chars(e["body"], *seed.GUJARATI)
        if e["language"] == "hi":
            assert hi > 20 and gu == 0
        elif e["language"] == "gu":
            assert gu > 20 and hi == 0
        else:
            assert hi == 0 and gu == 0
        assert seed._script_language(e["body"]) == e["language"]


def test_entries_sit_near_their_site():
    sites = {s["name"]: s for s in seed.SITES}
    for e in seed.ENTRIES:
        site = sites[e["site"]]
        dist = seed.haversine_km(site["lat"], site["lng"],
                                 site["lat"] + e["dlat"], site["lng"] + e["dlng"])
        assert dist < 1.0, e["title"]


def test_populate_loads_empty_database():
    """Seed into its own temp SQLite DB so shared test databases stay untouched."""

    async def run() -> tuple[int, int, int, set[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_async_engine(f"sqlite+aiosqlite:///{Path(tmp, 'seed.db').as_posix()}")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as db:
                counts = await seed.populate(db, "demo-password-123")
                assert counts == {"users": 3, "sites": 24, "entries": 12}
                n_sites = (await db.execute(select(func.count()).select_from(Site))).scalar_one()
                n_entries = (await db.execute(select(func.count()).select_from(Entry))).scalar_one()
                roles = set((await db.execute(select(User.role))).scalars())
                orphans = (await db.execute(
                    select(func.count()).select_from(Entry).where(Entry.site_id.is_(None))
                )).scalar_one()
                assert orphans == 0
            await engine.dispose()
            return n_sites, n_entries, 0, roles

    n_sites, n_entries, _, roles = asyncio.run(run())
    assert (n_sites, n_entries) == (24, 12)
    assert roles == {"admin", "researcher", "contributor"}
