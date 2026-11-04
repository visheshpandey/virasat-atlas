import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import AsyncSessionLocal, engine
from app.db.base import Base
from app.models.user import User
from app.models.location import Location
from app.models.safety_report import SafetyReport
from app.models.route import Route
from app.core.security import hash_password
import random
from datetime import datetime, timezone, timedelta


INDORE_CENTER = (22.7196, 75.8577)
INDORE_BOUNDS = {
    "lat_min": 22.68,
    "lat_max": 22.76,
    "lng_min": 75.82,
    "lng_max": 75.90,
}

SEED_USERS = [
    {"name": "Admin User", "email": "admin@saferoute.dev", "password": "Admin@1234", "phone": "+919876543210"},
    {"name": "Priya Sharma", "email": "priya@saferoute.dev", "password": "Test@1234", "phone": "+919876543211"},
    {"name": "Test User", "email": "test@saferoute.dev", "password": "Test@1234", "phone": "+919876543212"},
    {"name": "Anjali Verma", "email": "anjali@saferoute.dev", "password": "Test@1234", "phone": "+919876543213"},
    {"name": "Neha Patel", "email": "neha@saferoute.dev", "password": "Test@1234", "phone": "+919876543214"},
]

REPORT_TYPES = ["HARASSMENT", "ASSAULT", "POOR_LIGHTING", "UNSAFE_CROWD", "INFRASTRUCTURE", "OTHER"]

INDORE_HOTSPOTS = [
    (22.7150, 75.8500, "POOR_LIGHTING", "Dark alley near railway underpass"),
    (22.7300, 75.8700, "HARASSMENT", "Frequent catcalling reported"),
    (22.7100, 75.8650, "UNSAFE_CROWD", "Isolated area after 9pm"),
    (22.7220, 75.8590, "INFRASTRUCTURE", "Broken streetlight"),
    (22.7180, 75.8620, "POOR_LIGHTING", "No lights on this stretch"),
]


async def seed_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✓ Tables created")

    async with AsyncSessionLocal() as db:
        # Seed users
        users = []
        for u in SEED_USERS:
            user = User(
                name=u["name"],
                email=u["email"],
                hashed_password=hash_password(u["password"]),
                phone=u["phone"],
            )
            db.add(user)
            users.append(user)
        await db.commit()
        print(f"✓ Seeded {len(users)} users")

        # Seed locations
        for _ in range(20):
            user = random.choice(users)
            loc = Location(
                user_id=user.id,
                latitude=random.uniform(INDORE_BOUNDS["lat_min"], INDORE_BOUNDS["lat_max"]),
                longitude=random.uniform(INDORE_BOUNDS["lng_min"], INDORE_BOUNDS["lng_max"]),
                timestamp=datetime.now(timezone.utc) - timedelta(hours=random.randint(0, 72)),
            )
            db.add(loc)
        await db.commit()
        print("✓ Seeded 20 locations")

        # Seed safety reports (hotspots + random)
        for lat, lng, rtype, desc in INDORE_HOTSPOTS:
            report = SafetyReport(
                user_id=random.choice(users).id,
                latitude=lat,
                longitude=lng,
                report_type=rtype,
                description=desc,
                created_at=datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 168)),
            )
            db.add(report)

        for _ in range(45):
            report = SafetyReport(
                user_id=random.choice(users).id if random.random() > 0.1 else None,
                latitude=random.uniform(INDORE_BOUNDS["lat_min"], INDORE_BOUNDS["lat_max"]),
                longitude=random.uniform(INDORE_BOUNDS["lng_min"], INDORE_BOUNDS["lng_max"]),
                report_type=random.choice(REPORT_TYPES),
                description=f"Random report {random.randint(1000, 9999)}",
                created_at=datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 720)),
            )
            db.add(report)
        await db.commit()
        print("✓ Seeded 50 safety reports")

        # Seed routes
        for _ in range(10):
            user = random.choice(users)
            src_lat = random.uniform(INDORE_BOUNDS["lat_min"], INDORE_BOUNDS["lat_max"])
            src_lng = random.uniform(INDORE_BOUNDS["lng_min"], INDORE_BOUNDS["lng_max"])
            dst_lat = random.uniform(INDORE_BOUNDS["lat_min"], INDORE_BOUNDS["lat_max"])
            dst_lng = random.uniform(INDORE_BOUNDS["lng_min"], INDORE_BOUNDS["lng_max"])

            route = Route(
                user_id=user.id,
                source_lat=src_lat,
                source_lng=src_lng,
                dest_lat=dst_lat,
                dest_lng=dst_lng,
                safety_score=round(random.uniform(0.5, 0.95), 2),
                path={"type": "LineString", "coordinates": [[src_lng, src_lat], [dst_lng, dst_lat]]},
            )
            db.add(route)
        await db.commit()
        print("✓ Seeded 10 routes")

    print("\n✅ Database seeded successfully for Indore region!")
    print("\nTest credentials:")
    for u in SEED_USERS:
        print(f"  {u['email']} / {u['password']}")


if __name__ == "__main__":
    asyncio.run(seed_database())
