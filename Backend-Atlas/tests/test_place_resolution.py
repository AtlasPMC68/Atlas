"""Unit tests for app.utils.place_resolution (Place and City Resolution).

Comprehensive test suite covering all gazetteer matching and resolution priorities:
1. Spatial bounds checking and in_bounds / out_of_bounds filtering.
2. Offline geographic entity lookups (countries, continents, oceans, lakes, rivers, provinces).
3. Candidate selection priorities:
   - Political types take priority over physical features (e.g. Ontario province vs lake).
   - Proximity to target_pos (georeferenced map coordinates).
   - Population-based disambiguation for homonymous cities (London UK vs London Canada).
4. Casing-driven resolution priorities:
   - ALL-CAPS prioritizes geographic entities (provinces, countries, ...).
   - Title / lowercase prioritizes cities from geonamescache.
5. Matching confidence stages:
   - Exact matching.
   - Fallback fuzzy matching for OCR typos with distance and bounds protection.
6. OCR multiline label extraction and nearby candidate search.
7. Geographic integrity safeguards (no ocean coordinate artifacts for Canadian provinces).
"""

import json
from pathlib import Path

from app.utils.place_resolution import (
    MATCHING_CONFIG,
    find_geo_entity,
    find_nearby_candidate_place,
    haversine_distance_km,
    is_in_bounds,
    match_ocr_label,
    resolve_best_candidate,
    resolve_place,
)

# Reference test bounding boxes
EUROPE_BOUNDS = {"south": 35.0, "north": 70.0, "west": -10.0, "east": 40.0}
CANADA_BOUNDS = {"south": 41.0, "north": 83.0, "west": -141.0, "east": -52.0}
NORTH_AMERICA_BOUNDS = {"south": 10.0, "north": 85.0, "west": -170.0, "east": -50.0}


# --- 1. Spatial Bounds Tests ---


def test_is_in_bounds():
    assert is_in_bounds(45.0, 5.0, None) is True
    # Paris in Europe
    assert is_in_bounds(48.8566, 2.3522, EUROPE_BOUNDS) is True
    # Montreal outside Europe
    assert is_in_bounds(45.5017, -73.5673, EUROPE_BOUNDS) is False

    # Alternative coordinate naming: min_lat/max_lat/min_lon/max_lon
    alt_bounds = {"min_lat": 40.0, "max_lat": 60.0, "min_lon": -10.0, "max_lon": 20.0}
    assert is_in_bounds(48.8566, 2.3522, alt_bounds) is True
    assert is_in_bounds(30.0, 2.3522, alt_bounds) is False


def test_haversine_distance():
    # Montreal (45.5017, -73.5673) to Quebec City (46.8139, -71.2080) ~ 233 km
    dist = haversine_distance_km(45.5017, -73.5673, 46.8139, -71.2080)
    assert 220 < dist < 250


# --- 2. Offline Geographic Entities Lookup Tests ---


def test_find_geo_entity_countries():
    france = find_geo_entity("France")
    assert france is not None
    assert france["type"] == "country"
    assert france["name"] == "France"

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
    ohio = find_geo_entity("Rivière Ohio")
    assert ohio is not None
    assert ohio["type"] == "river"
    assert "Rivière Ohio" in ohio["name_fr"]

    teslin = find_geo_entity("Rivière Teslin")
    assert teslin is not None
    assert teslin["type"] == "river"

    st_laurent = find_geo_entity("Fleuve Saint-Laurent")
    assert st_laurent is not None
    assert st_laurent["type"] == "fleuve"

    mississippi = find_geo_entity("Fleuve Mississippi")
    assert mississippi is not None
    assert mississippi["type"] == "fleuve"


def test_find_geo_entity_provinces_and_states():
    florida = find_geo_entity("Floride")
    assert florida is not None
    assert florida["type"] == "state"

    quebec = find_geo_entity("Province de Québec")
    assert quebec is not None
    assert quebec["type"] == "province"

    rupert = find_geo_entity("Terre de Rupert")
    assert rupert is not None
    assert rupert["type"] == "territory"


def test_find_geo_entity_non_entities():
    assert find_geo_entity("Montréal") is None
    assert find_geo_entity("Paris") is None
    assert find_geo_entity("NonExistentXYZ") is None


# --- 3. Candidate Resolution Priorities ---


def test_resolve_best_candidate_prefers_political_entity():
    candidates = [
        {"name": "Ontario", "type": "lake", "lat": 43.7, "lon": -77.9},
        {"name": "Ontario", "type": "province", "lat": 51.25, "lon": -85.32},
    ]
    winner = resolve_best_candidate(candidates, prefer_political=True)
    assert winner is not None
    assert winner["type"] == "province"


def test_resolve_best_candidate_picks_closest_to_target_pos():
    candidates = [
        {"name": "Paris", "lat": 48.85, "lon": 2.35, "population": 2100000},
        {"name": "Paris", "lat": 33.66, "lon": -95.55, "population": 25000},  # Texas
    ]
    texas_target = (33.5, -95.0)
    winner = resolve_best_candidate(candidates, target_pos=texas_target)
    assert winner is not None
    assert winner["lat"] == 33.66

    winner_pop = resolve_best_candidate(candidates, prefer_population=True)
    assert winner_pop is not None
    assert winner_pop["lat"] == 48.85


def test_resolve_best_candidate_centralized():
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


def test_population_disambiguation():
    # London, UK (pop > 7M, lat ~ 51.5) vs London, Canada (pop ~ 350k, lon ~ -81.2)
    res_uk = resolve_place("London", frame_bounds=EUROPE_BOUNDS)
    assert res_uk["found"] is True
    assert res_uk["lon"] > -5.0
    assert res_uk["lat"] > 50.0

    res_ca = resolve_place("London", frame_bounds=CANADA_BOUNDS)
    assert res_ca["found"] is True
    assert res_ca["lon"] < -80.0


# --- 4. Casing-Driven Resolution Priorities ---


def test_casing_priority_homonyms():
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

    # New York: in JSON as state, in geonamescache as city
    res_ny_caps = resolve_place("NEW YORK", frame_bounds=NORTH_AMERICA_BOUNDS)
    assert res_ny_caps["found"] is True
    assert res_ny_caps["type"] == "state"

    res_ny_title = resolve_place("New York", frame_bounds=NORTH_AMERICA_BOUNDS)
    assert res_ny_title["found"] is True
    assert res_ny_title.get("type") is None
    assert res_ny_title["population"] > 8000000


def test_json_duplicate_conflict_resolution_by_target_pos():
    r_south = resolve_place("ONTARIO", frame_bounds=CANADA_BOUNDS, target_pos=(45.5, -78.0))
    r_north = resolve_place("ONTARIO", frame_bounds=CANADA_BOUNDS, target_pos=(52.0, -88.0))
    assert r_south["found"] is True
    assert r_north["found"] is True
    assert r_south["type"] == "province"
    assert r_north["type"] == "province"
    assert r_south["lat"] < r_north["lat"]


# --- 5. Bounds Rejection and Fuzzy Matching ---


def test_country_in_bounds_matched():
    res = resolve_place("France", frame_bounds=EUROPE_BOUNDS)
    assert res["found"] is True
    assert res["name"] == "FRANCE"
    assert res["type"] == "country"


def test_country_out_of_bounds_blocked_without_fuzzy_match():
    # Canada on Europe map
    res = resolve_place("Canada", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.60)
    assert res["found"] is False

    # France on Canada map
    res_fr = resolve_place("France", frame_bounds=CANADA_BOUNDS, confidence_threshold=0.60)
    assert res_fr["found"] is False


def test_lake_and_ocean_in_and_out_of_bounds():
    res_lake_ca = resolve_place("Lac Supérieur", frame_bounds=CANADA_BOUNDS)
    assert res_lake_ca["found"] is True
    assert res_lake_ca["type"] == "lake"

    res_lake_eu = resolve_place("Lac Supérieur", frame_bounds=EUROPE_BOUNDS)
    assert res_lake_eu["found"] is False

    res_ocean = resolve_place("Océan Atlantique")
    assert res_ocean["found"] is True
    assert res_ocean["type"] == "ocean"


def test_exact_city_in_bounds():
    res = resolve_place("Paris", frame_bounds=EUROPE_BOUNDS)
    assert res["found"] is True
    assert res["name"] == "Paris"
    assert 48.0 <= res["lat"] <= 49.0


def test_city_out_of_bounds():
    res = resolve_place("Paris", frame_bounds=CANADA_BOUNDS)
    assert res["found"] is False
    assert res["out_of_bounds"] is True


def test_fuzzy_city_candidate_out_of_bounds_is_blocked(monkeypatch):
    import app.utils.place_resolution as resolution

    monkeypatch.setattr(resolution, "find_geo_entity", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        resolution,
        "_CITY_INDEX",
        {
            "paris": [
                {
                    "name": "Paris",
                    "lat": 48.8566,
                    "lon": 2.3522,
                    "population": 0,
                    "geonameid": 1,
                }
            ]
        },
    )

    result = resolve_place(
        "Pariss",
        frame_bounds=CANADA_BOUNDS,
        confidence_threshold=0.60,
    )

    assert result["found"] is False
    assert result["out_of_bounds"] is True


def test_fuzzy_match_recovers_ocr_typos():
    res = resolve_place("Pariss", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.70)
    assert res["found"] is True
    assert res["name"] == "Paris"
    assert 48.0 <= res["lat"] <= 49.0

    res_ca = resolve_place("Canade", frame_bounds=CANADA_BOUNDS, confidence_threshold=0.75)
    assert res_ca["found"] is True
    assert res_ca["name"] == "CANADA"


def test_fuzzy_match_cutoff_respected():
    res = resolve_place("Xqzjkwlf", frame_bounds=EUROPE_BOUNDS, confidence_threshold=0.80)
    assert res["found"] is False


def test_empty_or_whitespace_query():
    assert resolve_place("")["found"] is False
    assert resolve_place("   ")["found"] is False


def test_find_nearby_candidate_place():
    coords = [-73.5673, 45.5017]
    match = find_nearby_candidate_place("Montral", coords, radius_km=100.0, min_similarity=0.80)
    assert match is not None
    assert match["name"] in ("Montréal", "Montreal")


def test_find_nearby_candidate_place_geo_entity():
    coords = [-73.7073, 46.3688]
    match = find_nearby_candidate_place("Province de Quebe", coords, radius_km=150.0, min_similarity=0.80)
    assert match is not None
    all_names = [match.get("name", ""), *match.get("aliases", [])]
    assert any("quebec" in name.lower() for name in all_names)


def test_find_nearby_candidate_place_out_of_radius():
    # Montreal coords, but searching for Paris
    coords = [-73.5673, 45.5017]
    match = find_nearby_candidate_place("Paris", coords, radius_km=50.0, min_similarity=0.90)
    assert match is None


# --- 6. OCR Multiline Label Matching ---


def test_match_ocr_label_single_and_multiline():
    matched = match_ocr_label("Paris", frame_bounds=EUROPE_BOUNDS)
    assert matched is not None
    assert matched["name"] == "Paris"

    multiline = match_ocr_label("Carte de l'Est\nParis\nÉchelle 1:50000", frame_bounds=EUROPE_BOUNDS)
    assert multiline is not None
    assert multiline["name"] == "Paris"

    country_multiline = match_ocr_label("Territoire\nFrance", frame_bounds=EUROPE_BOUNDS)
    assert country_multiline is not None
    assert country_multiline["name"] == "FRANCE"

    assert match_ocr_label("") is None
    assert match_ocr_label(None) is None


# --- 7. Geographic Integrity Safeguards ---


def test_canadian_provinces_no_ocean_artifacts():
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
            assert lon <= -61.0, f"Nova Scotia entry placed in ocean at lon={lon}"
            assert 43.0 <= lat <= 48.0
        elif name_fr == "Nunavut":
            assert lat >= 60.0
        elif name_fr == "Ontario":
            assert lat >= 43.0


def test_nova_scotia_resolution_mainland():
    res = resolve_place("NOUVELLE-ÉCOSSE", frame_bounds=CANADA_BOUNDS, target_pos=(44.0, -60.5))
    assert res["found"] is True
    assert res["type"] == "province"
    assert res["lon"] <= -61.0
    assert 44.0 <= res["lat"] <= 47.0


def test_prefix_preserved_only_if_detected_in_extraction():
    res_with_prefix = resolve_place("Province de Québec", frame_bounds=CANADA_BOUNDS)
    assert res_with_prefix["found"] is True
    assert res_with_prefix["name"] == "PROVINCE DE QUÉBEC"

    res_no_prefix = resolve_place("QUÉBEC", frame_bounds=CANADA_BOUNDS)
    assert res_no_prefix["found"] is True
    assert res_no_prefix["name"] == "QUÉBEC"
