"""Tests for the rule-based tagger and its optional model layer."""
import asyncio

import pytest

from app.core.config import settings
from app.services import tagger
from app.services.tagger import detect_language, extract_century, tag_rules, tag_text


# --- site type ---
def test_english_stepwell():
    tags = tag_rules("Rani ki Vav is an 11th century stepwell in Patan.")
    assert tags["site_type"] == "stepwell"
    assert tags["century"] == 11
    assert "water-architecture" in tags["themes"]
    assert tags["language"] == "en"
    assert tags["source"] == "rules"


@pytest.mark.parametrize("text", ["the old baoli", "Adalaj Vav", "a deep step well", "three stepwells"])
def test_stepwell_spellings(text):
    assert tag_rules(text)["site_type"] == "stepwell"


def test_hindi_stepwell():
    tags = tag_rules("रानी की वाव पाटन में 11वीं शताब्दी की एक बावड़ी है")
    assert tags["site_type"] == "stepwell"
    assert tags["language"] == "hi"
    assert tags["century"] == 11


def test_gujarati_stepwell_and_era():
    tags = tag_rules("રાણકી વાવ પાટણમાં આવેલી સોલંકી યુગની એક ભવ્ય વાવ છે")
    assert tags["site_type"] == "stepwell"
    assert tags["era"] == "Chaulukya (Solanki)"
    assert tags["language"] == "gu"


def test_hindi_fort_and_temple():
    assert tag_rules("जूनागढ़ का ऊपरकोट किला बहुत पुराना है")["site_type"] == "fort"
    assert tag_rules("सोमनाथ मंदिर समुद्र के किनारे है")["site_type"] == "temple"


def test_other_types():
    assert tag_rules("Sidi Saiyyed Mosque is known for its jali windows")["site_type"] == "mosque"
    assert tag_rules("Mahabat Maqbara, the mausoleum of the Junagadh nawabs")["site_type"] == "mausoleum"
    assert tag_rules("Patan Patola weaving takes months on a handloom")["site_type"] == "craft"
    assert tag_rules("Dholavira was a Harappan city")["site_type"] == "harappan-site"


def test_no_match_returns_nothing():
    tags = tag_rules("A pleasant afternoon with tea.")
    assert tags["site_type"] is None and tags["era"] is None and tags["century"] is None
    assert tags["themes"] == []


# --- word-boundary false positives ---
def test_port_does_not_match_inside_important():
    assert "maritime-trade" not in tag_rules("This is an important building")["themes"]
    assert "maritime-trade" not in tag_rules("A portrait of the king")["themes"]
    assert "maritime-trade" in tag_rules("Lothal was an important Harappan port")["themes"]


def test_fort_does_not_match_fortune_or_effort():
    assert tag_rules("Good fortune and great effort")["site_type"] is None
    assert tag_rules("Uparkot Fort stands above the city")["site_type"] == "fort"
    assert tag_rules("the fortified gateway")["site_type"] == "fort"


def test_stem_keywords_match_prefixes():
    assert "stone-carving" in tag_rules("Finely carved pillars")["themes"]
    assert "pilgrimage" in tag_rules("Thousands of pilgrims climb the hill")["themes"]


# --- eras ---
@pytest.mark.parametrize(
    "text,era",
    [
        ("A Maitraka period copper plate", "Maitraka"),
        ("Built under the Solanki dynasty", "Chaulukya (Solanki)"),
        ("Raised by the Gujarat Sultanate under Ahmed Shah", "Gujarat Sultanate"),
        ("A Mughal era garden", "Mughal"),
        ("Gaekwad rulers of Baroda", "Princely/Maratha"),
        ("A colonial railway station", "Colonial"),
        ("Dholavira, a Harappan city", "Harappan"),
    ],
)
def test_eras(text, era):
    assert tag_rules(text)["era"] == era


# --- century ---
def test_century_phrases():
    assert extract_century("an 11th century temple") == 11
    assert extract_century("the 13th-century wall") == 13
    assert extract_century("built in the twelfth century") == 12


def test_century_from_year():
    assert extract_century("completed in 1498") == 15
    assert extract_century("restored in 1900") == 19
    assert extract_century("founded 1411 by Ahmed Shah") == 15


def test_century_bce():
    assert extract_century("the city flourished around 2500 BCE") == -25
    assert extract_century("a 3rd century BCE inscription") == -3
    assert extract_century("dated to 600 BC") == -6
    assert tag_rules("Dholavira, a Harappan city of about 2500 BCE")["century"] == -25


def test_century_ignores_measurements():
    assert extract_century("the hall is 120 metres long with 512 steps") is None
    assert extract_century("a 500 km journey") is None


def test_century_indic_scripts():
    assert extract_century("यह मंदिर 11वीं शताब्दी का है") == 11
    assert extract_century("આ વાવ ૧૧મી સદીની છે") == 11
    assert extract_century("ईसा पूर्व 3 शताब्दी की मुहर") == -3


# --- language ---
def test_language_detection():
    assert detect_language("A stepwell in Patan") == "en"
    assert detect_language("पाटन की रानी की वाव") == "hi"
    assert detect_language("પાટણની રાણકી વાવ") == "gu"
    assert detect_language("") == "en"
    assert detect_language("12345 !!") == "en"


def test_mostly_english_with_one_hindi_word_stays_english():
    assert detect_language("We visited the Rani ki Vav (वाव) near Patan on a clear morning") == "en"


# --- themes ---
def test_themes_follow_canonical_order():
    tags = tag_rules("The queen's legend: a UNESCO stepwell with carved panels")
    assert tags["themes"] == ["water-architecture", "stone-carving", "royalty", "folklore", "unesco"]


# --- model layer ---
@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
    tagger._cache.clear()
    yield
    tagger._cache.clear()


def test_without_key_model_is_never_called(monkeypatch):
    async def boom(_):
        raise AssertionError("must not be called")

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(tagger, "_call_gemini", boom)
    assert asyncio.run(tag_text("An old stepwell"))["source"] == "rules"


def test_model_fills_gaps_but_keeps_rules(monkeypatch, with_key):
    async def fake(_):
        return {"site_type": "temple", "era": "Mughal", "century": 17, "themes": ["pilgrimage"]}

    monkeypatch.setattr(tagger, "_call_gemini", fake)
    tags = asyncio.run(tag_text("An old stepwell near the river"))
    assert tags["site_type"] == "stepwell"  # rules win
    assert tags["era"] == "Mughal"  # gap filled
    assert tags["century"] == 17
    assert "pilgrimage" in tags["themes"] and "water-architecture" in tags["themes"]
    assert tags["source"] == "rules+gemini"


def test_model_failure_never_breaks_tagging(monkeypatch, with_key):
    async def fail(_):
        raise RuntimeError("network down")

    monkeypatch.setattr(tagger, "_call_gemini", fail)
    tags = asyncio.run(tag_text("An old stepwell"))
    assert tags["site_type"] == "stepwell"
    assert tags["source"] == "rules"


def test_model_result_is_cached(monkeypatch, with_key):
    calls = []

    async def fake(text):
        calls.append(text)
        return {"era": "Mughal"}

    monkeypatch.setattr(tagger, "_call_gemini", fake)
    asyncio.run(tag_text("A hilltop shrine"))
    asyncio.run(tag_text("A hilltop shrine"))
    assert len(calls) == 1


def test_model_failure_is_cached_briefly(monkeypatch, with_key):
    calls = []

    async def fail(text):
        calls.append(text)
        raise RuntimeError("boom")

    monkeypatch.setattr(tagger, "_call_gemini", fail)
    asyncio.run(tag_text("A hilltop shrine"))
    asyncio.run(tag_text("A hilltop shrine"))
    assert len(calls) == 1


def test_model_output_is_validated():
    cleaned = tagger._clean_model_output(
        {"site_type": "spaceship", "era": "Mughal", "century": 99, "themes": ["royalty", "nonsense"]}
    )
    assert cleaned == {"era": "Mughal", "themes": ["royalty"]}
    assert tagger._clean_model_output("not a dict") is None
    assert tagger._parse_json_object('Sure! {"era": "Mughal"} done') == {"era": "Mughal"}


def test_gemini_request_shape_and_parsing(monkeypatch):
    """_call_gemini sends the key as a header, asks for JSON, and validates the reply."""
    import httpx

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = request.read().decode()
        reply = {"candidates": [{"content": {"parts": [{"text": '{"site_type": "fort", "century": 15, "themes": ["royalty", "bogus"]}'}]}}]}
        return httpx.Response(200, json=reply)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")

    out = asyncio.run(tagger._call_gemini("A fort built in 1450"))

    assert out == {"site_type": "fort", "century": 15, "themes": ["royalty"]}
    assert seen["key"] == "test-key"
    assert ":generateContent" in seen["url"] and "test-key" not in seen["url"]
    assert "responseMimeType" in seen["body"]
