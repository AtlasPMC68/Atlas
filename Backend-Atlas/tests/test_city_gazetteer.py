"""The city gazetteer behind city control points.

Built once per module from the pinned geonamescache into a temp directory, so
the tests exercise the real data and never touch ``app/.cache``.
"""

import os

import pytest

from app.utils import city_gazetteer
from app.utils.city_gazetteer import (
    find_cities_in_text,
    frame_city_index,
    normalize_name,
    search_cities,
)

QUEBEC = {"west": -80.0, "south": 44.0, "east": -56.0, "north": 53.0}


@pytest.fixture(scope="module", autouse=True)
def built_gazetteer(tmp_path_factory):
    cache = tmp_path_factory.mktemp("gazetteer")
    original = city_gazetteer.CACHE_DIR
    city_gazetteer.CACHE_DIR = str(cache)
    try:
        path = city_gazetteer.ensure_gazetteer()
        yield path
    finally:
        city_gazetteer.CACHE_DIR = original


def _names(query, bounds=QUEBEC, **kwargs):
    return [c.name for c in search_cities(query, bounds, **kwargs)]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Trois-Rivières", "trois rivieres"),
        ("  TROIS   rivieres ", "trois rivieres"),
        ("Saint-Jean-sur-Richelieu", "saint jean sur richelieu"),
        ("L'Assomption", "l assomption"),
        ("", ""),
    ],
)
def test_names_normalise_accents_case_and_punctuation(raw, expected):
    assert normalize_name(raw) == expected


def test_the_file_is_small_and_keyed_on_the_library_version(built_gazetteer):
    assert os.path.basename(built_gazetteer).startswith("cities15000-gnc")
    # Latin-script alternate names only: the whole point is not to hold 56 MB.
    assert os.path.getsize(built_gazetteer) < 15 * 1024 * 1024


def test_exact_match_ignores_accents_and_case():
    found = search_cities("montreal", QUEBEC)
    assert found[0].name == "Montréal"
    assert found[0].match == "exact"


def test_hyphens_and_spaces_are_interchangeable():
    assert _names("Trois Rivieres")[0] == "Trois-Rivières"


def test_alternate_names_match():
    """Historical and foreign spellings live in the alternate names."""
    found = search_cities("Kebek", QUEBEC)
    assert found and found[0].name == "Québec"
    assert found[0].matched_name.casefold() == "kebek"


def test_near_misses_match_as_fuzzy():
    found = search_cities("Montral", QUEBEC)
    assert found[0].name == "Montréal"
    assert found[0].match == "fuzzy"


def test_exact_ranks_above_prefix_and_fuzzy():
    kinds = [c.match for c in search_cities("Quebec", QUEBEC)]
    assert kinds[0] == "exact"
    assert kinds == sorted(kinds, key=lambda k: {"exact": 0, "prefix": 1, "fuzzy": 2}[k])


def test_cities_outside_the_frame_are_never_returned():
    assert "Toronto" not in _names("Toronto")
    assert "Toronto" in _names(
        "Toronto", {"west": -90.0, "south": 40.0, "east": -70.0, "north": 50.0}
    )


def test_a_frame_crossing_the_antimeridian_is_searched_on_both_sides():
    fiji = {"west": 175.0, "south": -20.0, "east": -175.0, "north": -15.0}
    assert "Suva" in _names("Suva", fiji)


def test_an_unknown_name_is_an_empty_list_not_an_error():
    assert search_cities("Stadacona", QUEBEC) == []
    assert search_cities("", QUEBEC) == []
    assert search_cities("   ", QUEBEC) == []


def test_limit_is_honoured():
    assert len(search_cities("Sa", QUEBEC, limit=3)) <= 3


def test_candidates_serialise_for_the_frontend():
    payload = search_cities("Montreal", QUEBEC)[0].to_dict()
    assert set(payload) == {
        "id", "name", "lat", "lon", "country", "population", "matchedName", "match",
    }
    assert isinstance(payload["id"], int) and payload["id"] > 0


# --- place names read off the map -----------------------------------------


def test_text_cities_are_looked_up_inside_the_frame_only():
    index = frame_city_index(QUEBEC)
    assert normalize_name(index.lookup("Montréal").name) == "montreal"
    # Paris exists, but not inside a Quebec frame.
    assert index.lookup("Paris") is None


def test_text_matches_are_exact_not_fuzzy():
    # OCR noise must not become a city: "Montral" is a near miss only.
    assert frame_city_index(QUEBEC).lookup("Montral") is None


def test_multi_word_names_are_read_as_one_city():
    phrases = find_cities_in_text("Trois Rivieres et Quebec", frame_city_index(QUEBEC))
    matched = [(phrase, city.name if city else None) for phrase, city in phrases]
    assert matched[0][0] == "Trois Rivieres"
    assert normalize_name(matched[0][1]) == "trois rivieres"
    assert matched[1] == ("et", None)
    assert matched[2][1] is not None and matched[2][1].startswith("Qu")


def test_the_frame_is_read_once_per_frame():
    from app.utils import city_gazetteer

    city_gazetteer._read_frame.cache_clear()
    search_cities("Montreal", QUEBEC)
    search_cities("Quebec", QUEBEC)
    info = city_gazetteer._read_frame.cache_info()
    assert (info.misses, info.hits) == (1, 1)
