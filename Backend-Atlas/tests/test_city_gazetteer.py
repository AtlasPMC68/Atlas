"""The city gazetteer behind city control points.

Built once per module from the pinned geonamescache into a temp directory, so
the tests exercise the real data and never touch ``app/.cache``.
"""


import pytest

from app.utils import city_gazetteer
from app.utils.city_gazetteer import (
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


def test_exact_match_ignores_accents_and_case():
    found = search_cities("montreal", QUEBEC)
    assert found[0].name == "Montréal"
    assert found[0].match == "exact"


def test_alternate_names_match():
    """Historical and foreign spellings live in the alternate names."""
    found = search_cities("Kebek", QUEBEC)
    assert found and found[0].name == "Québec"
    assert found[0].matched_name.casefold() == "kebek"


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


# --- place names read off the map -----------------------------------------


