"""Tests for the hybrid search index, built from in-test documents."""
import pytest

from app.services.search_index import SearchDoc, SearchIndex, make_snippet, normalize, tokenize

RANI = "11111111-1111-1111-1111-111111111111"
SUN = "22222222-2222-2222-2222-222222222222"
FORT = "33333333-3333-3333-3333-333333333333"
HINDI_ENTRY = "44444444-4444-4444-4444-444444444444"
GUJ_ENTRY = "55555555-5555-5555-5555-555555555555"
EN_ENTRY = "66666666-6666-6666-6666-666666666666"


def make_docs() -> list[SearchDoc]:
    return [
        SearchDoc("site", RANI, RANI, "Rani ki Vav",
                  "An 11th century stepwell at Patan built by Queen Udayamati. Intricate stone carving "
                  "of Vishnu avatars lines the descending galleries. stepwell chaulukya water-architecture",
                  23.8588, 72.1017, "en"),
        SearchDoc("site", SUN, SUN, "Modhera Sun Temple",
                  "A Solanki era temple dedicated to Surya. The kund in front is lined with small shrines.",
                  23.5835, 72.1330, "en"),
        SearchDoc("site", FORT, FORT, "Uparkot Fort",
                  "A fortress on a mound in Junagadh, with rock cut caves and a deep stepped well.",
                  21.5290, 70.4579, "en"),
        SearchDoc("entry", HINDI_ENTRY, RANI, "पाटन की यात्रा",
                  "आज हमने पाटन की बावड़ी देखी। दीवारों पर नक्काशीदार मूर्तियाँ बहुत सुंदर हैं और "
                  "स्थानीय लोग इसे रानी की वाव कहते हैं।",
                  23.8590, 72.1020, "hi"),
        SearchDoc("entry", GUJ_ENTRY, SUN, "મોઢેરાની મુલાકાત",
                  "અમે મોઢેરાનું સૂર્ય મંદિર જોયું. સાંજે કુંડ પાસે બેસીને શિલ્પો જોયા.",
                  23.5836, 72.1331, "gu"),
        SearchDoc("entry", EN_ENTRY, FORT, "Notes from Junagadh",
                  "Climbed to the Uparkot ramparts at dawn. The caves smelled of damp stone.",
                  21.5292, 70.4580, "en"),
    ]


@pytest.fixture(scope="module")
def idx() -> SearchIndex:
    index = SearchIndex()
    index.rebuild(make_docs())
    return index


def ids(results):
    return [r["id"] for r in results]


def test_stepwell_finds_rani_ki_vav_first(idx):
    results = idx.search("stepwell")
    assert results and results[0]["id"] == RANI
    assert results[0]["kind"] == "site"


def test_hindi_query_finds_hindi_entry_first(idx):
    results = idx.search("बावड़ी")
    assert results and results[0]["id"] == HINDI_ENTRY
    assert results[0]["language"] == "hi"
    assert results[0]["site_id"] == RANI


def test_hindi_query_matches_inside_longer_word(idx):
    # "नक्काशी" only occurs inside "नक्काशीदार"; the character layer must still find it.
    assert idx.search("नक्काशी")[0]["id"] == HINDI_ENTRY


def test_hindi_text_in_nfd_form_still_matches(idx):
    import unicodedata

    assert idx.search(unicodedata.normalize("NFD", "बावड़ी"))[0]["id"] == HINDI_ENTRY


def test_gujarati_query(idx):
    results = idx.search("સૂર્ય મંદિર")
    assert results[0]["id"] == GUJ_ENTRY and results[0]["language"] == "gu"


def test_typo_still_finds_stepwell(idx):
    assert idx.search("stepwel")[0]["id"] == RANI
    assert idx.search("steppwell")[0]["id"] == RANI


def test_transliteration_vaav(idx):
    assert RANI in ids(idx.search("rani ki vaav"))


def test_title_match_wins(idx):
    assert idx.search("Modhera")[0]["id"] in {SUN, GUJ_ENTRY}


def test_result_shape(idx):
    result = idx.search("uparkot")[0]
    assert set(result) == {"kind", "id", "site_id", "title", "snippet", "score", "lat", "lng", "language"}
    assert result["lat"] is not None and result["lng"] is not None
    assert 0 < result["score"] <= 1.0001
    assert "<" not in result["snippet"]


def test_site_result_site_id_equals_id(idx):
    site_hit = next(r for r in idx.search("stepwell") if r["kind"] == "site")
    assert site_hit["site_id"] == site_hit["id"]


def test_k_limits_results(idx):
    assert len(idx.search("stone", k=1)) <= 1
    assert idx.search("stone", k=0) == []


def test_nonsense_and_empty_queries(idx):
    assert idx.search("zzzzqxj") == []
    assert idx.search("") == []
    assert idx.search("   ?!  ") == []


def test_scores_are_sorted_and_positive(idx):
    scores = [r["score"] for r in idx.search("temple stone well")]
    assert scores == sorted(scores, reverse=True) and all(s > 0 for s in scores)


def test_cached_results_are_independent_copies(idx):
    first = idx.search("stepwell")
    first[0]["title"] = "mutated"
    assert idx.search("stepwell")[0]["title"] == "Rani ki Vav"


def test_empty_index():
    empty = SearchIndex()
    assert empty.search("anything") == []
    empty.rebuild([])
    assert empty.search("anything") == []


def test_rebuild_swaps_in_new_documents():
    index = SearchIndex()
    index.rebuild(make_docs()[:1])
    assert index.search("fortress") == [] or index.search("fortress")[0]["id"] == RANI
    index.rebuild(make_docs())
    assert index.search("fortress")[0]["id"] == FORT  # also clears the stale query cache


def test_old_state_is_unaffected_by_a_later_rebuild():
    # A reader holding the old state keeps a consistent snapshot after a rebuild.
    other = SearchIndex()
    other.rebuild(make_docs())
    state_before = other._state
    other.rebuild(make_docs()[:2])
    assert state_before.docs and len(state_before.docs) == 6


def test_tokenizer_keeps_indic_words_whole():
    assert tokenize(normalize("रानी की वाव, पाटन।")) == ["रानी", "की", "वाव", "पाटन"]
    assert tokenize(normalize("રાણકી વાવ")) == ["રાણકી", "વાવ"]


def test_snippet_centres_on_match_and_is_plain_text():
    text = ("x " * 120) + "the stepwell is deep " + ("y " * 120)
    snippet = make_snippet(text, "stepwell")
    assert "stepwell" in snippet and len(snippet) < 260
    assert snippet.startswith("…") and snippet.endswith("…")


def test_snippet_short_text_returned_whole():
    assert make_snippet("A short note.", "note") == "A short note."


def test_snippet_without_match_falls_back_to_start():
    text = "Opening words here. " + ("filler " * 60)
    assert make_snippet(text, "zzzz").startswith("Opening words")
