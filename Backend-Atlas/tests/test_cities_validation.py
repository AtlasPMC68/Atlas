"""Unit tests for app.utils.cities_validation.

Tests:
- String normalization and bounds checking helpers.
- Offline geographic entity detection (countries, continents, lakes, oceans/seas).
- In-bounds vs out-of-bounds geographic feature filtering.
- Rejection of out-of-bounds countries without false fuzzy city matches.
- City candidate resolution, population-based disambiguation, and frame bounds.
- Last-resort fuzzy matching for OCR typos.
- Line-by-line OCR label matching (match_ocr_label).
"""

import json
from pathlib import Path

from app.utils.cities_validation import (
    _normalize,
    find_geo_entity,
    format_place_result,
    is_in_bounds,
    match_ocr_label,
    resolve_place,
)

# Reference test bounding boxes
EUROPE_BOUNDS = {"south": 35.0, "north": 70.0, "west": -10.0, "east": 40.0}
CANADA_BOUNDS = {"south": 41.0, "north": 83.0, "west": -141.0, "east": -52.0}
NORTH_AMERICA_BOUNDS = {"south": 10.0, "north": 85.0, "west": -170.0, "east": -50.0}


# Normalization & Bounds Helper Tests


def test_normalize():
    assert _normalize("Montréal") == "montreal"
    assert _normalize("  États-Unis  ") == "etats unis"
    assert _normalize("Océan Atlantique!!!") == "ocean atlantique"
    assert _normalize("") == ""


def test_is_in_bounds():
    # None bounds should always allow
    assert is_in_bounds(45.0, 5.0, None) is True

    # Inside Europe
    assert is_in_bounds(48.8566, 2.3522, EUROPE_BOUNDS) is True  # Paris

    # Outside Europe
    assert is_in_bounds(45.5017, -73.5673, EUROPE_BOUNDS) is False  # Montreal

    # Alternative coordinate naming: min_lat/max_lat/min_lon/max_lon
    alt_bounds = {"min_lat": 40.0, "max_lat": 60.0, "min_lon": -10.0, "max_lon": 20.0}
    assert is_in_bounds(48.8566, 2.3522, alt_bounds) is True
    assert is_in_bounds(30.0, 2.3522, alt_bounds) is False


# Offline Geographic Entities Lookup Tests
def test_find_geo_entity_countries():
    france = find_geo_entity("France")
    assert france is not None
    assert france["type"] == "country"
    assert france["name"] == "France"

    # French and English aliases
    spain_fr = find_geo_entity("Espagne")
    spain_en = find_geo_entity("Spain")
    assert spain_fr is not None
    assert spain_en is not None
    assert spain_fr["name"] == spain_en["name"]



def test_find_geo_entity_continents():
    africa_fr = find_geo_entity("Afrique")
    africa_en = find_geo_entity("Africa")
    assert africa_fr is not None
    assert africa_en is not None
    assert africa_fr["type"] == "continent"


def test_find_geo_entity_oceans_and_seas():
    ocean = find_geo_entity("Océan Atlantique")
    assert ocean is not None
    assert ocean["type"] == "ocean"

    sea = find_geo_entity("Mer Méditerranée")
    assert sea is not None
    assert sea["type"] == "sea"


def test_find_geo_entity_lakes():
    lake = find_geo_entity("Lac Supérieur")
    assert lake is not None
    assert lake["type"] == "lake"
    assert "Lac" in lake["name_fr"]


def test_find_geo_entity_rivers_and_fleuves():
    # Rivières
    ohio = find_geo_entity("Rivière Ohio")
    assert ohio is not None
    assert ohio["type"] == "river"
    assert "Rivière Ohio" in ohio["name_fr"]

    teslin = find_geo_entity("Rivière Teslin")
    assert teslin is not None
    assert teslin["type"] == "river"

    # Fleuves
    st_laurent = find_geo_entity("Fleuve Saint-Laurent")
    assert st_laurent is not None
    assert st_laurent["type"] == "fleuve"

    mississippi = find_geo_entity("Fleuve Mississippi")
    assert mississippi is not None
    assert mississippi["type"] == "fleuve"


def test_find_geo_entity_provinces_and_states():
    # Florida
    florida = find_geo_entity("Floride")
    assert florida is not None
    assert florida["type"] == "state"

    # Quebec
    quebec = find_geo_entity("Province de Québec")
    assert quebec is not None
    assert quebec["type"] == "province"

    # Historical territory
    rupert = find_geo_entity("Terre de Rupert")
    assert rupert is not None
    assert rupert["type"] == "territory"


def test_find_geo_entity_non_entities():
    # Cities or random strings must return None
    assert find_geo_entity("Montréal") is None
    assert find_geo_entity("Paris") is None
    assert find_geo_entity("NonExistentXYZ") is None


# resolve_place with Geographic Entities
def test_country_in_bounds_matched():
    res = resolve_place("France", frame_bounds=EUROPE_BOUNDS)
    assert res["found"] is True
    assert res["name"] == "FRANCE"
    assert res["type"] == "country"
    assert res["lat"] != 0.0
    assert res["lon"] != 0.0


def test_country_out_of_bounds_blocked_without_fuzzy_match():
    """Ensure countries out of bounds are blocked and NOT matched to random cities via fuzzy matching."""
    # Canada on Europe map
    res = resolve_place("Canada", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.60)
    assert res["found"] is False
    assert res["matched_text"] is None

    # France on Canada map
    res_fr = resolve_place("France", frame_bounds=CANADA_BOUNDS, confidence_threshold=0.60)
    assert res_fr["found"] is False


def test_lake_and_ocean_in_and_out_of_bounds():
    # Lake Superior in Canada bounds
    res_lake_ca = resolve_place("Lac Supérieur", frame_bounds=CANADA_BOUNDS)
    assert res_lake_ca["found"] is True
    assert res_lake_ca["type"] == "lake"

    # Lake Superior in Europe bounds -> blocked
    res_lake_eu = resolve_place("Lac Supérieur", frame_bounds=EUROPE_BOUNDS)
    assert res_lake_eu["found"] is False

    # Ocean without bounds -> found
    res_ocean = resolve_place("Océan Atlantique")
    assert res_ocean["found"] is True
    assert res_ocean["type"] == "ocean"


def test_fuzzy_match_geographic_entities():
    """Ensure OCR typos on countries/lakes are recovered and match the country, not random cities."""
    # "Canade" -> Canada
    res_ca = resolve_place("Canade", frame_bounds=CANADA_BOUNDS, confidence_threshold=0.75)
    assert res_ca["found"] is True
    assert res_ca["name"] == "CANADA"
    assert res_ca["type"] == "country"

    # "Eats-Unis" -> États-Unis
    res_us = resolve_place("Eats-Unis", frame_bounds=NORTH_AMERICA_BOUNDS, confidence_threshold=0.75)
    assert res_us["found"] is True
    assert res_us["name"] == "ÉTATS-UNIS"
    assert res_us["type"] == "country"

    # "Frannce" -> France in Europe
    res_fr = resolve_place("Frannce", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.75)
    assert res_fr["found"] is True
    assert res_fr["name"] == "FRANCE"
    assert res_fr["type"] == "country"

    # "Canade" on Europe map must be rejected as out of bounds, NOT matched to a random city
    res_ca_eu = resolve_place("Canade", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.75)
    assert res_ca_eu["found"] is False

    # "Lac Superinla" -> Lac Supérieur (water body: capitalized first letter, not all uppercase)
    res_lake = resolve_place("Lac Superinla", frame_bounds=NORTH_AMERICA_BOUNDS, confidence_threshold=0.70)
    assert res_lake["found"] is True
    assert res_lake["name"] == "Lac Supérieur"
    assert res_lake["type"] == "lake"

    # "Florise" (typo for Floride) -> Floride (state: uppercase)
    res_fl = resolve_place("Florise", frame_bounds=NORTH_AMERICA_BOUNDS, confidence_threshold=0.75)
    assert res_fl["found"] is True
    assert res_fl["name"] == "FLORIDE"
    assert res_fl["type"] == "state"


# resolve_place with Cities
def test_exact_city_in_bounds():
    res = resolve_place("Paris", frame_bounds=EUROPE_BOUNDS)
    assert res["found"] is True
    assert res["name"] == "Paris"
    assert 48.0 <= res["lat"] <= 49.0
    assert res["geonameid"] is not None


def test_city_out_of_bounds():
    # Paris on Canada map -> not found
    res = resolve_place("Paris", frame_bounds=CANADA_BOUNDS)
    assert res["found"] is False


def test_population_disambiguation():
    """When a city name exists in multiple locations, highest population candidate in bounds wins."""
    # London, UK (pop > 7M, lat ~ 51.5) vs London, Canada (pop ~ 350k, lon ~ -81.2)
    res_uk = resolve_place("London", frame_bounds=EUROPE_BOUNDS)
    assert res_uk["found"] is True
    assert res_uk["lon"] > -5.0
    assert res_uk["lat"] > 50.0

    res_ca = resolve_place("London", frame_bounds=CANADA_BOUNDS)
    assert res_ca["found"] is True
    assert res_ca["lon"] < -80.0


# Fuzzy Matching Fallback (Last Resort)
def test_fuzzy_match_recovers_ocr_typos():
    # "Pariss" typo for Paris in Europe
    res = resolve_place("Pariss", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.70)
    assert res["found"] is True
    assert res["name"] == "Paris"
    assert 48.0 <= res["lat"] <= 49.0


def test_fuzzy_match_cutoff_respected():
    # Complete gibberish should not match
    res = resolve_place("Xqzjkwlf", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.80)
    assert res["found"] is False


def test_empty_or_whitespace_query():
    assert resolve_place("")["found"] is False
    assert resolve_place("   ")["found"] is False


# match_ocr_label Function
def test_match_ocr_label_single_and_multiline():
    # Single label
    matched = match_ocr_label("Paris", frame_bounds=EUROPE_BOUNDS)
    assert matched is not None
    assert matched["name"] == "Paris"

    # Multi-line label where one line contains a place
    multiline = match_ocr_label("Carte de l'Est\nParis\nÉchelle 1:50000", frame_bounds=EUROPE_BOUNDS)
    assert multiline is not None
    assert multiline["name"] == "Paris"

    # Multi-line country (formatted uppercase)
    country_multiline = match_ocr_label("Territoire\nFrance", frame_bounds=EUROPE_BOUNDS)
    assert country_multiline is not None
    assert country_multiline["name"] == "FRANCE"

    # None / empty
    assert match_ocr_label("") is None
    assert match_ocr_label(None) is None


# Casing Priority Tests (ALL-CAPS -> JSON entity, Title Case/lowercase -> City)
def test_casing_priority_homonyms():
    """Ensure ALL-CAPS text prioritizes JSON geographic entities (provinces/states),
    while Title Case / lowercase text prioritizes geonamescache cities when present in both."""
    # Québec: in JSON as province, in geonamescache as city
    res_caps = resolve_place("QUÉBEC", frame_bounds=CANADA_BOUNDS)
    assert res_caps["found"] is True
    assert res_caps["type"] == "province"
    assert res_caps["geonameid"] == "province:Québec"
    assert res_caps["name"] == "QUÉBEC"

    res_title = resolve_place("Québec", frame_bounds=CANADA_BOUNDS)
    assert res_title["found"] is True
    assert res_title.get("type") is None  # standard city
    assert res_title["name"] == "Québec"
    assert res_title["geonameid"] == 6325494

    res_lower = resolve_place("quebec", frame_bounds=CANADA_BOUNDS)
    assert res_lower["found"] is True
    assert res_lower.get("type") is None
    assert res_lower["name"] == "Québec"
    assert res_lower["geonameid"] == 6325494

    # New York: in JSON as state, in geonamescache as city
    res_ny_caps = resolve_place("NEW YORK", frame_bounds=NORTH_AMERICA_BOUNDS)
    assert res_ny_caps["found"] is True
    assert res_ny_caps["type"] == "state"

    res_ny_title = resolve_place("New York", frame_bounds=NORTH_AMERICA_BOUNDS)
    assert res_ny_title["found"] is True
    assert res_ny_title.get("type") is None  # city
    assert res_ny_title["population"] > 8000000


def test_json_duplicate_conflict_resolution_by_target_pos():
    """Ensure that when a geographic entity appears multiple times in the JSON (e.g. Ontario across eras),
    the one closest to target_pos (OCR text position on the map) is selected."""
    r_south = resolve_place("ONTARIO", frame_bounds=CANADA_BOUNDS, target_pos=(45.5, -78.0))
    r_north = resolve_place("ONTARIO", frame_bounds=CANADA_BOUNDS, target_pos=(52.0, -88.0))
    assert r_south["found"] is True
    assert r_north["found"] is True
    assert r_south["type"] == "province"
    assert r_north["type"] == "province"
    assert r_south["lat"] < r_north["lat"]


def test_canadian_provinces_no_ocean_artifacts():
    """Safeguard: verify that no Canadian province in geographic_entities.json
    has corrupt coordinates from isolated offshore islands or boundary adjustment slivers."""
    data_path = Path(__file__).resolve().parent.parent / "app" / "data" / "geographic_entities.json"
    with open(data_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    for e in entities:
        name_fr = e.get("name_fr")
        lat = e.get("lat")
        lon = e.get("lon")
        if lat is None or lon is None:
            continue

        if name_fr == "Nouvelle-Écosse":
            # Must be on mainland Nova Scotia, never out in the Atlantic ocean (Sable Island: lon > -61.0)
            assert lon <= -61.0, f"Nova Scotia entry ({e.get('start_year')}) placed in ocean at lon={lon}"
            assert 43.0 <= lat <= 48.0, f"Nova Scotia entry ({e.get('start_year')}) invalid lat={lat}"

        elif name_fr == "Nunavut":
            # Must be in Arctic / Northern Canada, never in James Bay (lat ~ 51.7)
            assert lat >= 60.0, f"Nunavut entry ({e.get('start_year')}) placed in James Bay at lat={lat}"

        elif name_fr == "Ontario":
            # Must not be collapsed to southernmost tip in Lake Erie (lat < 43.0)
            assert lat >= 43.0, f"Ontario entry ({e.get('start_year')}) placed too far south at lat={lat}"


def test_nova_scotia_resolution_mainland():
    """Ensure that resolving NOUVELLE-ÉCOSSE even with an offshore OCR text box
    always selects the valid mainland coordinates and never offshore ocean artifacts."""
    res = resolve_place("NOUVELLE-ÉCOSSE", frame_bounds=CANADA_BOUNDS, target_pos=(44.0, -60.5))
    assert res["found"] is True
    assert res["type"] == "province"
    assert res["lon"] <= -61.0
    assert 44.0 <= res["lat"] <= 47.0


def test_ocean_styling_is_uppercase_label_without_point():
    """Ensure oceans are rendered as italic uppercase labels without a point marker."""
    res = resolve_place("Océan Atlantique")
    assert res["found"] is True
    assert res["type"] == "ocean"
    assert res["mapElementType"] == "label"
    assert res["fontStyle"] == "italic uppercase"
    assert res["name"] == "OCÉAN ATLANTIQUE"


def test_capitalize_words_multi_term_and_particles():
    from app.utils.cities_validation import capitalize_words
    assert capitalize_words("new york city") == "New York City"
    assert capitalize_words("saint-pierre") == "Saint-Pierre"
    assert capitalize_words("golfe du mexique") == "Golfe du Mexique"
    assert capitalize_words("mer du labrador") == "Mer du Labrador"
    assert capitalize_words("lac supérieur") == "Lac Supérieur"
    assert capitalize_words("baie d'hudson") == "Baie d'Hudson"


def test_prefix_preserved_only_if_detected_in_extraction():
    """Ensure geographic prefix (e.g. 'Province de ...') is preserved if detected in query,
    and NOT added if the query did not contain it."""
    # Prefix present in query -> preserved
    res_with_prefix = resolve_place("Province de Québec", frame_bounds=CANADA_BOUNDS)
    assert res_with_prefix["found"] is True
    assert res_with_prefix["name"] == "PROVINCE DE QUÉBEC"

    # Prefix NOT present in query -> NOT added
    res_no_prefix = resolve_place("QUÉBEC", frame_bounds=CANADA_BOUNDS)
    assert res_no_prefix["found"] is True
    assert res_no_prefix["name"] == "QUÉBEC"


def test_format_place_result_unified_city_and_geo():
    """Verify that format_place_result correctly handles both cities and geographic entities."""
    # City input
    city_data = {
        "geonameid": 6325494,
        "name": "Québec",
        "lat": 46.8123,
        "lon": -71.2145,
        "population": 540000,
    }
    res_city = format_place_result(city_data, "quebec")
    assert res_city["found"] is True
    assert res_city["name"] == "Québec"
    assert res_city["mapElementType"] == "point"
    assert res_city["sizePx"] == 12
    assert res_city["fontStyle"] == "normal"
    assert res_city["population"] == 540000
    assert res_city.get("type") is None

    # Province input
    province_data = {
        "name": "Quebec",
        "name_fr": "Québec",
        "type": "province",
        "lat": 52.0,
        "lon": -70.0,
    }
    res_province = format_place_result(province_data, "QUÉBEC", default_type="country")
    assert res_province["found"] is True
    assert res_province["name"] == "QUÉBEC"
    assert res_province["type"] == "province"
    assert res_province["mapElementType"] == "label"
    assert res_province["sizePx"] == 14
    assert res_province["fontStyle"] == "uppercase"
    assert res_province["geonameid"] == "province:Quebec"


def test_resolve_best_candidate_centralized():
    from app.utils.cities_validation import resolve_best_candidate

    c1 = {"name": "Candidate A", "type": "lake", "lat": 45.0, "lon": -73.0, "population": 0}
    c2 = {"name": "Candidate B", "type": "province", "lat": 46.0, "lon": -74.0, "population": 1000}
    c3 = {"name": "Candidate C", "type": "city", "lat": 80.0, "lon": 0.0, "population": 500000}

    # Bounds filter: c3 is out of CANADA_BOUNDS
    best = resolve_best_candidate([c1, c2, c3], bounds=CANADA_BOUNDS, prefer_political=True)
    assert best == c2  # Political preference selects province over lake

    # Target position selection
    best_target = resolve_best_candidate([c1, c2], target_pos=(45.1, -73.1), prefer_political=False)
    assert best_target == c1

    # Population preference
    best_pop = resolve_best_candidate([c1, c2], prefer_political=False, prefer_population=True)
    assert best_pop == c2
