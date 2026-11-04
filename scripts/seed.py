"""Seed the database with DEMO DATA for Virasat Atlas.

*** DEMO DATA NOTICE ***
Everything below is sample content for demonstration. Sites, coordinates and eras are
based on public references (coordinates cross-checked against Wikipedia where listed
there) but descriptions are short summaries, not scholarly records. The field entries
are invented sample notes written by fictional "Demo Fellow" authors; they are not real
fieldwork. Do not treat any of it as an authoritative archive.

Usage:
    python scripts/seed.py              # seed only if the database has no sites (default)
    python scripts/seed.py --if-empty   # same, explicit (used by docker-compose)
    python scripts/seed.py --reset      # drop every table, recreate, then seed
"""
import argparse
import asyncio
import math
import os
import secrets
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.models.entry import Entry  # noqa: E402
from app.models.site import Site  # noqa: E402
from app.models.user import User  # noqa: E402

DEMO_AUTHOR_PREFIX = "Demo Fellow"

# --------------------------------------------------------------------------------------
# DEMO DATA: sites. era is free text; eras outside the tagger's list (e.g. Mauryan) are fine.
# --------------------------------------------------------------------------------------
SITES: list[dict[str, Any]] = [
    {
        "name": "Rani ki Vav", "site_type": "stepwell", "era": "Chaulukya (Solanki)",
        "century": 11, "district": "Patan", "lat": 23.8589, "lng": 72.1017,
        "description": "A seven-storey stepwell whose walls carry hundreds of carved panels of "
        "avatars of Vishnu, apsaras and sages. The steps descend to a deep well chamber, "
        "turning a water source into a temple-like inverted monument.",
        "folklore": None,
        "themes": ["water-architecture", "stone-carving", "unesco"], "unesco": True,
    },
    {
        "name": "Adalaj Stepwell", "site_type": "stepwell", "era": "Gujarat Sultanate",
        "century": 15, "district": "Gandhinagar", "lat": 23.1664, "lng": 72.5805,
        "description": "A five-level stepwell completed in 1498, mixing Hindu and Islamic motifs. "
        "Octagonal landings and carved pillars keep the shaft cool even in peak summer.",
        "folklore": "Local legend says Queen Rudabai (Roopba) asked the Sultan to finish the "
        "stepwell before she would consent to marry him, and on its completion she circled "
        "it and gave up her life in the water.",
        "themes": ["water-architecture", "stone-carving", "royalty", "folklore"], "unesco": False,
    },
    {
        "name": "Dada Harir Vav", "site_type": "stepwell", "era": "Gujarat Sultanate",
        "century": 15, "district": "Ahmedabad", "lat": 23.0588, "lng": 72.6143,
        "description": "A five-storey stepwell in the Asarwa area of Ahmedabad, built in 1499 and "
        "associated with a lady of the royal household. Its carved pillars and brackets show "
        "the confident stonework of the Sultanate period.",
        "folklore": None,
        "themes": ["water-architecture", "stone-carving", "royalty"], "unesco": False,
    },
    {
        "name": "Modhera Sun Temple", "site_type": "temple", "era": "Chaulukya (Solanki)",
        "century": 11, "district": "Mehsana", "lat": 23.5838, "lng": 72.1327,
        "description": "A sun temple of the early 11th century, planned so that dawn light on the "
        "equinoxes falls on the sanctum. A stepped tank in front, the Surya Kund, holds many "
        "small shrines along its terraces.",
        "folklore": None,
        "themes": ["stone-carving", "pilgrimage", "water-architecture"], "unesco": False,
    },
    {
        "name": "Rudra Mahalaya", "site_type": "temple", "era": "Chaulukya (Solanki)",
        "century": 12, "district": "Patan", "lat": 23.9192, "lng": 72.3792,
        "description": "The ruined remains of a grand Shiva temple at Siddhpur, associated with "
        "the Chaulukya king Siddharaja Jayasimha. Only parts of the porch and pillars survive "
        "after centuries of damage and reuse.",
        "folklore": None,
        "themes": ["stone-carving", "pilgrimage", "royalty"], "unesco": False,
    },
    {
        "name": "Champaner-Pavagadh Archaeological Park", "site_type": "fort",
        "era": "Gujarat Sultanate", "century": 15, "district": "Panchmahal",
        "lat": 22.4833, "lng": 73.5333,
        "description": "A hill fortress and walled town that became Mahmud Begada's capital in the "
        "late 15th century. Mosques, gateways, step tanks and a hilltop shrine sit within a "
        "landscape of older Rajput fortifications.",
        "folklore": None,
        "themes": ["royalty", "stone-carving", "pilgrimage", "water-architecture", "unesco"],
        "unesco": True,
    },
    {
        "name": "Dholavira", "site_type": "harappan-site", "era": "Harappan",
        "century": -26, "district": "Kutch", "lat": 23.8886, "lng": 70.2136,
        "description": "A Harappan city on Khadir island in the Rann of Kutch, notable for its "
        "carefully planned layout and a chain of stone-lined water reservoirs. A large "
        "signboard with Harappan script symbols was found near a gateway.",
        "folklore": None,
        "themes": ["water-architecture", "maritime-trade", "unesco"], "unesco": True,
    },
    {
        "name": "Lothal", "site_type": "harappan-site", "era": "Harappan",
        "century": -24, "district": "Ahmedabad", "lat": 22.5214, "lng": 72.2494,
        "description": "A Harappan settlement with a large brick basin long interpreted as a "
        "dockyard, together with bead-making workshops. It shows how this inland-looking site "
        "was tied into sea trade routes.",
        "folklore": None,
        "themes": ["maritime-trade", "living-craft", "water-architecture"], "unesco": False,
    },
    {
        "name": "Sidi Saiyyed Mosque", "site_type": "mosque", "era": "Gujarat Sultanate",
        "century": 16, "district": "Ahmedabad", "lat": 23.0269, "lng": 72.5811,
        "description": "A small mosque finished around 1573, known for the stone lattice windows "
        "on its western wall. One pierced panel of intertwined tree branches is among the "
        "best-known images of Ahmedabad.",
        "folklore": None,
        "themes": ["stone-carving", "unesco"], "unesco": True,
    },
    {
        "name": "Jama Masjid, Ahmedabad", "site_type": "mosque", "era": "Gujarat Sultanate",
        "century": 15, "district": "Ahmedabad", "lat": 23.0238, "lng": 72.5872,
        "description": "A congregational mosque built in 1424 by Ahmad Shah I. A forest of "
        "yellow sandstone pillars supports its prayer hall, with details borrowed from "
        "older Hindu and Jain temple craft.",
        "folklore": None,
        "themes": ["stone-carving", "royalty", "unesco"], "unesco": True,
    },
    {
        "name": "Bhadra Fort", "site_type": "fort", "era": "Gujarat Sultanate",
        "century": 15, "district": "Ahmedabad", "lat": 23.0236, "lng": 72.5811,
        "description": "A walled royal complex raised in 1411 at the start of Ahmedabad. It holds "
        "gateways, an open ground and the Azam Khan Sarai, and marked the seat of Sultanate "
        "power in the new city.",
        "folklore": None,
        "themes": ["royalty", "unesco"], "unesco": True,
    },
    {
        "name": "Sabarmati Ashram", "site_type": "memorial", "era": "Colonial",
        "century": 20, "district": "Ahmedabad", "lat": 23.0607, "lng": 72.5807,
        "description": "The riverside ashram where Gandhi lived from 1917 and from which the Salt "
        "March began in 1930. Simple huts, a spinning room and a small museum preserve his "
        "daily life and the practice of hand-spun cloth.",
        "folklore": None,
        "themes": ["living-craft"], "unesco": False,
    },
    {
        "name": "Uparkot Fort", "site_type": "fort", "era": "Mauryan",
        "century": -3, "district": "Junagadh", "lat": 21.5237, "lng": 70.4695,
        "description": "An ancient hill fort in the heart of Junagadh, with Buddhist cave "
        "complexes, deep stepped wells and long stretches of rampart. It was repeatedly "
        "abandoned and refortified over about two thousand years.",
        "folklore": "Tradition tells of the Chudasama ruler Ra' Khengar and a long siege by the "
        "Chaulukya king Siddharaja Jayasimha, ending with betrayal from within.",
        "themes": ["royalty", "water-architecture", "folklore"], "unesco": False,
    },
    {
        "name": "Adi Kadi Vav", "site_type": "stepwell", "era": "Gujarat Sultanate",
        "century": 15, "district": "Junagadh", "lat": 21.5266, "lng": 70.4713,
        "description": "A stepwell cut deep into the rock inside Uparkot, reached by a long run "
        "of steps. Its pale stone is plain compared with decorated stepwells elsewhere in "
        "Gujarat, which makes the sheer depth more striking.",
        "folklore": "Local tradition links the name to two maidservants, Adi and Kadi, said to "
        "have been connected with the well.",
        "themes": ["water-architecture", "folklore"], "unesco": False,
    },
    {
        "name": "Mahabat Maqbara", "site_type": "mausoleum", "era": "Princely/Maratha",
        "century": 19, "district": "Junagadh", "lat": 21.5272, "lng": 70.4600,
        "description": "The mausoleum of the Nawabs of Junagadh, completed in the late 19th "
        "century. Its bulbous domes and spiralling minarets blend Indo-Islamic, Gothic and "
        "European details.",
        "folklore": None,
        "themes": ["royalty", "stone-carving"], "unesco": False,
    },
    {
        "name": "Palitana Shatrunjaya Temples", "site_type": "temple", "era": "Chaulukya (Solanki)",
        "century": 11, "district": "Bhavnagar", "lat": 21.4683, "lng": 71.8000,
        "description": "A dense city of hundreds of Jain temples on Shatrunjaya hill, reached by "
        "climbing about 3,000 steps. Construction continued over centuries, so shrines of "
        "very different ages stand side by side.",
        "folklore": "Jain tradition holds that the first tirthankara, Rishabhanatha, "
        "preached on this hill.",
        "themes": ["pilgrimage", "stone-carving", "folklore"], "unesco": False,
    },
    {
        "name": "Somnath Temple", "site_type": "temple", "era": "Modern",
        "century": 20, "district": "Gir Somnath", "lat": 20.8880, "lng": 70.4014,
        "description": "A Shiva temple on the Arabian Sea coast at Prabhas Patan, destroyed and "
        "rebuilt many times. The present building, in the Chaulukya style, was completed "
        "in 1951.",
        "folklore": "Tradition says the moon god Soma was freed from a curse here, which is "
        "why the place carries his name.",
        "themes": ["pilgrimage", "maritime-trade", "folklore"], "unesco": False,
    },
    {
        "name": "Dwarkadhish Temple", "site_type": "temple", "era": "Gujarat Sultanate",
        "century": 16, "district": "Devbhumi Dwarka", "lat": 22.2379, "lng": 68.9676,
        "description": "A tall, multi-storey temple of Krishna on the Gomti creek at Dwarka, "
        "with a spire rising high above the town. The present form is generally dated to "
        "the 15th or 16th century on much older foundations.",
        "folklore": "Tradition holds that Krishna's great-grandson Vajranabha first raised a "
        "shrine on the spot where Krishna's palace had stood.",
        "themes": ["pilgrimage", "maritime-trade", "folklore"], "unesco": False,
    },
    {
        "name": "Prag Mahal", "site_type": "palace", "era": "Princely/Maratha",
        "century": 19, "district": "Kutch", "lat": 23.2548, "lng": 69.6683,
        "description": "A 19th-century palace in Bhuj designed in an Italianate Gothic style, "
        "with a tall bell tower and a grand durbar hall. It was damaged in the 2001 "
        "earthquake and remains partly under restoration.",
        "folklore": None,
        "themes": ["royalty"], "unesco": False,
    },
    {
        "name": "Aina Mahal", "site_type": "palace", "era": "Princely/Maratha",
        "century": 18, "district": "Kutch", "lat": 23.2553, "lng": 69.6688,
        "description": "The 'Palace of Mirrors' in Bhuj, built in the mid-18th century under "
        "Maharao Lakhpatji. Its hall of mirrors, tiled fountain room and Kutchi craft "
        "collection reflect the court's taste for both local and European art.",
        "folklore": None,
        "themes": ["royalty", "living-craft"], "unesco": False,
    },
    {
        "name": "Laxmi Vilas Palace", "site_type": "palace", "era": "Princely/Maratha",
        "century": 19, "district": "Vadodara", "lat": 22.2939, "lng": 73.1914,
        "description": "The residence of the Gaekwad rulers of Baroda, finished around 1890. Its "
        "Indo-Saracenic exterior covers a very large complex of halls, gardens and a "
        "private museum.",
        "folklore": None,
        "themes": ["royalty"], "unesco": False,
    },
    {
        "name": "Patan Patola Weaving", "site_type": "craft", "era": "Chaulukya (Solanki)",
        "century": 12, "district": "Patan", "lat": 23.8493, "lng": 72.1266,
        "description": "Patola are double-ikat silk saris in which both warp and weft threads "
        "are tie-dyed before weaving. The skill is held by a small number of families in "
        "Patan, and a single sari can take many months to finish.",
        "folklore": None,
        "themes": ["living-craft"], "unesco": False,
    },
    {
        "name": "Nirona Rogan Art", "site_type": "craft", "era": "Princely/Maratha",
        "century": 18, "district": "Kutch", "lat": 23.5200, "lng": 69.4300,
        "description": "Rogan is a Kutchi textile art in which a thick paste made from boiled "
        "castor oil and pigments is drawn onto cloth with a metal stylus. Nirona village "
        "is the last place where one family tradition keeps the craft going.",
        "folklore": None,
        "themes": ["living-craft"], "unesco": False,
    },
    {
        "name": "Polo Forest Temples", "site_type": "temple", "era": "Chaulukya (Solanki)",
        "century": 12, "district": "Sabarkantha", "lat": 23.9851, "lng": 73.2688,
        "description": "A group of Jain and Hindu temples scattered through a forest along the "
        "Harnav river near Vijaynagar, dated roughly between the 10th and 15th centuries. "
        "Ruined, ivy-wrapped stonework gives the site a quiet, abandoned feel.",
        "folklore": None,
        "themes": ["stone-carving", "pilgrimage"], "unesco": False,
    },
]

# --------------------------------------------------------------------------------------
# DEMO DATA: field entries by fictional authors. site is matched by name.
# --------------------------------------------------------------------------------------
ENTRIES: list[dict[str, Any]] = [
    {
        "site": "Rani ki Vav", "title": "Morning light on the lower landings", "kind": "journal",
        "language": "en", "author": "Demo Fellow A", "dlat": 0.0003, "dlng": 0.0002,
        "body": "Reached the stepwell before the crowds. The carved panels on the lowest "
        "landings are almost fully lit by 8 am; the Vishnu avatars are far sharper than in "
        "photographs. Our guide explained that the vav was a water source and a place of "
        "worship at once, and that silt buried the lower levels for centuries, which is why "
        "so much detail survived.",
    },
    {
        "site": "Adalaj Stepwell", "title": "Queen Roopba story told by the caretaker", "kind": "folklore",
        "language": "en", "author": "Demo Fellow B", "dlat": 0.0004, "dlng": -0.0003,
        "body": "The caretaker told the legend of the queen who asked for the stepwell to be "
        "completed before she would marry the Sultan. He pointed to the octagonal landing "
        "where, he said, she walked round the well one last time. The retelling differed from "
        "the plaque, a reminder that oral versions drift from the written one.",
    },
    {
        "site": "Modhera Sun Temple", "title": "Surya Kund at noon", "kind": "photo",
        "language": "en", "author": "Demo Fellow A", "dlat": 0.0005, "dlng": 0.0004,
        "body": "Photograph series of the stepped tank in front of the sun temple. Small shrines "
        "line the terraces; the geometry of the steps makes strong diagonals at midday. "
        "Caption notes: Chaulukya period, early 11th century, sandstone carving.",
    },
    {
        "site": "Dholavira", "title": "Reservoir chain walk-through", "kind": "journal",
        "language": "en", "author": "Demo Fellow C", "dlat": 0.0006, "dlng": 0.0003,
        "body": "Walked the edge of the stone-lined reservoirs on the eastern side. Harappan "
        "engineers captured seasonal rain in a chain of tanks, which is striking in such a dry "
        "landscape. The site museum displays the signboard with its large script symbols.",
    },
    {
        "site": "Patan Patola Weaving", "title": "Double ikat at the loom", "kind": "journal",
        "language": "en", "author": "Demo Fellow B", "dlat": 0.0004, "dlng": 0.0002,
        "body": "A weaver family showed how both warp and weft are tied and dyed before the "
        "sari is woven. One sari can take six months or more. They said fewer young people "
        "are learning the skill because the work is slow and exact. A living craft with few "
        "apprentices.",
    },
    {
        "site": "Sabarmati Ashram", "title": "Visitor ledger page, transcribed", "kind": "document",
        "language": "en", "author": "Demo Fellow D", "dlat": 0.0003, "dlng": 0.0003,
        "body": "Transcription of a handwritten page from the visitor register on display in the "
        "museum. Entries are in English, Hindi and Gujarati, mostly short notes of thanks and "
        "reflections on non-violence, dated to the early 20th century.",
    },
    {
        "site": "Nirona Rogan Art", "title": "Rogan paste preparation", "kind": "journal",
        "language": "en", "author": "Demo Fellow C", "dlat": 0.0007, "dlng": 0.0004,
        "body": "The artisan boils castor oil down to a thick paste and mixes it with powdered "
        "colour. Designs are drawn onto cloth with a thin metal stylus, never touching the "
        "surface with fingers. He folds the cloth over to print a mirror image of the tree of "
        "life motif.",
    },
    {
        "site": "Polo Forest Temples", "title": "Ivy on the forest temples", "kind": "photo",
        "language": "en", "author": "Demo Fellow D", "dlat": 0.0008, "dlng": -0.0004,
        "body": "Photographs of two ruined temples overgrown with ivy along the river path. "
        "Carved doorframes are still visible, but several shikharas have fallen. No signage "
        "describes the period; local guide places them between the 10th and 15th centuries.",
    },
    # --- Hindi (Devanagari) ---
    {
        "site": "Rani ki Vav", "title": "रानी की वाव, पाटन - यात्रा नोट", "kind": "journal",
        "language": "hi", "author": "Demo Fellow E", "dlat": -0.0004, "dlng": 0.0003,
        "body": "पाटन की रानी की वाव सुबह की रोशनी में बहुत शांत लगती है। सीढ़ियों की दीवारों पर "
        "विष्णु के अवतारों की नक्काशी है और सबसे नीचे का कुआँ आज भी गहरा दिखता है। गाइड ने बताया "
        "कि सोलंकी काल में यह वाव एक रानी की याद में बनवाई गई मानी जाती है।",
    },
    {
        "site": "Somnath Temple", "title": "सोमनाथ की लोककथा", "kind": "folklore",
        "language": "hi", "author": "Demo Fellow E", "dlat": 0.0005, "dlng": -0.0003,
        "body": "सोमनाथ मंदिर के बारे में स्थानीय लोग कहते हैं कि चंद्रदेव को यहीं श्राप से मुक्ति "
        "मिली थी, इसलिए इस जगह का नाम सोमनाथ पड़ा। समुद्र के किनारे शाम की आरती के समय सैकड़ों "
        "तीर्थयात्री इकट्ठा होते हैं।",
    },
    {
        "site": "Lothal", "title": "लोथल का पुराना बंदरगाह", "kind": "journal",
        "language": "hi", "author": "Demo Fellow F", "dlat": 0.0004, "dlng": 0.0004,
        "body": "लोथल में पुराने बंदरगाह का बड़ा हौज़ देखा। हड़प्पा काल के व्यापारी यहाँ से समुद्र के "
        "रास्ते माल भेजते थे। मिट्टी की ईंटों की दीवारें अब भी साफ़ दिखती हैं और पास की कार्यशाला में "
        "मनके बनाने के निशान मिले हैं।",
    },
    # --- Gujarati ---
    {
        "site": "Sidi Saiyyed Mosque", "title": "સીદી સૈયદની જાળી", "kind": "journal",
        "language": "gu", "author": "Demo Fellow F", "dlat": 0.0003, "dlng": -0.0002,
        "body": "સીદી સૈયદની જાળી ખૂબ જ સુંદર છે. પથ્થરમાં કોતરેલા ઝાડની ડાળીઓ જોવા માટે લોકો દૂર દૂરથી "
        "આવે છે. સાંજના સમયે તડકો જાળીમાંથી પસાર થાય ત્યારે દીવાલ પર પડછાયા બને છે. આ મસ્જિદ અમદાવાદની "
        "ઓળખ બની ગઈ છે.",
    },
]

DEVANAGARI = (0x0900, 0x097F)
GUJARATI = (0x0A80, 0x0AFF)


def _script_language(text: str) -> str:
    """Dominant-script language guess, used only when the tagger is unavailable."""
    counts = {"hi": 0, "gu": 0}
    for ch in text:
        cp = ord(ch)
        if DEVANAGARI[0] <= cp <= DEVANAGARI[1]:
            counts["hi"] += 1
        elif GUJARATI[0] <= cp <= GUJARATI[1]:
            counts["gu"] += 1
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "en"


async def _tag(text: str, language: str) -> dict[str, Any]:
    """Run the real tagger; if it is not available yet, return a minimal tag dict."""
    try:
        from app.services.tagger import tag_text

        tags = await tag_text(text)
        return dict(tags)
    except NotImplementedError:
        return {"site_type": None, "era": None, "century": None, "themes": [],
                "language": language, "source": "seed-fallback"}
    except Exception as exc:  # tagging must never block seeding demo data
        print(f"  warning: tagger failed ({type(exc).__name__}); using fallback tags")
        return {"site_type": None, "era": None, "century": None, "themes": [],
                "language": language, "source": "seed-fallback"}


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km (kept local so the seed has no extra imports)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((phi2 - phi1) / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


async def populate(db: AsyncSession, password: str) -> dict[str, int]:
    """Insert demo users, sites and entries into an initialised database."""
    users = [
        User(name="Demo Admin", email="admin@virasat.local", hashed_password=hash_password(password),
             role="admin"),
        User(name="Demo Researcher", email="researcher@virasat.local",
             hashed_password=hash_password(password), role="researcher"),
        User(name="Demo Contributor", email="contributor@virasat.local",
             hashed_password=hash_password(password), role="contributor"),
    ]
    db.add_all(users)

    sites_by_name: dict[str, Site] = {}
    for data in SITES:
        site = Site(**data)
        db.add(site)
        sites_by_name[data["name"]] = site
    await db.flush()

    for data in ENTRIES:
        site = sites_by_name[data["site"]]
        tags = await _tag(data["body"], data["language"])
        db.add(Entry(
            site_id=site.id,
            title=data["title"],
            body=data["body"],
            kind=data["kind"],
            language=data["language"],
            author=data["author"],
            lat=round(site.lat + data["dlat"], 6),
            lng=round(site.lng + data["dlng"], 6),
            tags=tags,
        ))
    await db.commit()
    return {"users": len(users), "sites": len(SITES), "entries": len(ENTRIES)}


async def seed_database(reset: bool = False) -> None:
    """Create tables (optionally wiping first), seed if empty, rebuild the search index."""
    from app.db.init_db import drop_db, init_db
    from app.db.session import AsyncSessionLocal, engine

    if reset:
        await drop_db()
        print("Dropped all tables")
    await init_db()

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(func.count()).select_from(Site))).scalar_one()
        if existing and not reset:
            print(f"Database already has {existing} sites; skipping seed (use --reset to wipe)")
            await engine.dispose()
            return

        generated = "SEED_PASSWORD" not in os.environ
        password = os.environ.get("SEED_PASSWORD") or secrets.token_urlsafe(12)
        counts = await populate(db, password)
        print(f"Seeded {counts['users']} users, {counts['sites']} sites, "
              f"{counts['entries']} entries (DEMO DATA)")
        print("Demo accounts: admin@virasat.local, researcher@virasat.local, "
              "contributor@virasat.local")
        if generated:
            print(f"Generated demo password (shown once): {password}")
        else:
            print("Password taken from SEED_PASSWORD")

        try:
            from app.services.search_index import rebuild_from_db

            await rebuild_from_db(db)
            print("Search index rebuilt")
        except NotImplementedError:
            print("Search index not available yet; it is rebuilt at server startup")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Virasat Atlas with demo data.")
    parser.add_argument("--reset", action="store_true", help="drop all tables, then seed")
    parser.add_argument("--if-empty", action="store_true",
                        help="seed only when no sites exist (this is already the default)")
    args = parser.parse_args()
    asyncio.run(seed_database(reset=args.reset))


if __name__ == "__main__":
    main()
