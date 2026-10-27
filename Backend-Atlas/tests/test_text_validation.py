"""Tests for text validation categorization and georeferencing."""

from app.tasks import _categorized_text_features_from_ocr
from app.utils.cities_validation import find_nearby_candidate_city

FRAME_BOUNDS = {"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0}
LEGEND_BOUNDS = {"x": 50.0, "y": 50.0, "width": 20.0, "height": 20.0}

QUEBEC_CITY = {
    "geonameid": 6325494,
    "name": "Québec",
    "lat": 46.8139,
    "lon": -71.2080,
    "country": "CA",
    "population": 540000,
}


def _mock_match_ocr(text, frame_bounds=None):
    if "quebec" in text.lower():
        return QUEBEC_CITY
    return None


def test_categorized_text_features_separates_recognized_and_unrecognized(monkeypatch):
    monkeypatch.setattr("app.tasks.match_ocr_label", _mock_match_ocr)

    blocks = [
        # Recognized city
        [[[10, 10], [30, 10], [30, 20], [10, 20]], "Quebec", 0.95],
        # Unrecognized text
        [[[100, 100], [140, 100], [140, 120], [100, 120]], "UnkPlace", 0.88],
        # Inside legend -> ignored
        [[[55, 55], [65, 55], [65, 65], [55, 65]], "LegendLabel", 0.99],
    ]

    collections = _categorized_text_features_from_ocr(
        blocks,
        legend_bounds=LEGEND_BOUNDS,
        frame_bounds=FRAME_BOUNDS,
    )

    features = [c["features"][0] for c in collections]

    # Legend text was ignored, so we expect exactly 2 features: 1 recognized, 1 unrecognized
    assert len(features) == 2

    # Check recognized feature
    rec = next(f for f in features if f["properties"]["recognized"])
    assert rec["properties"]["name"] == "Québec"
    assert rec["properties"]["originalText"] == "Quebec"
    assert rec["properties"]["isOcrText"] is True
    assert rec["properties"]["show"] is True
    assert rec["properties"]["matchedCity"] == "Québec"
    assert rec["properties"]["country"] == "CA"
    assert rec["geometry"]["coordinates"] == [-71.2080, 46.8139]

    # Check unrecognized feature (initialized with [0.0, 0.0], georeferenced later in batch)
    unrec = next(f for f in features if not f["properties"]["recognized"])
    assert unrec["properties"]["name"] == "UnkPlace"
    assert unrec["properties"]["originalText"] == "UnkPlace"
    assert unrec["properties"]["isOcrText"] is True
    assert unrec["properties"]["show"] is False
    assert unrec["geometry"]["coordinates"] == [0.0, 0.0]


def test_categorized_text_features_deduplicates_repeated_texts(monkeypatch):
    monkeypatch.setattr("app.tasks.match_ocr_label", _mock_match_ocr)

    blocks = [
        [[[10, 10], [30, 10], [30, 20], [10, 20]], "Quebec", 0.95],
        [[[15, 15], [35, 15], [35, 25], [15, 25]], "Quebec", 0.90],
        [[[100, 100], [120, 100], [120, 110], [100, 110]], "Riviere", 0.80],
        [[[200, 200], [220, 200], [220, 210], [200, 210]], "Riviere", 0.85],
    ]

    collections = _categorized_text_features_from_ocr(
        blocks,
        legend_bounds=None,
        frame_bounds=FRAME_BOUNDS,
    )

    features = [c["features"][0] for c in collections]
    assert len(features) == 2
    names = {f["properties"]["name"] for f in features}
    assert names == {"Québec", "Riviere"}


def test_categorized_text_features_fuzzy_unrecognized(monkeypatch):
    def _mock_fuzzy(text, frame_bounds=None):
        return None

    monkeypatch.setattr("app.tasks.match_ocr_label", _mock_fuzzy)

    blocks = [
        [[[10, 10], [50, 10], [50, 20], [10, 20]], "Traité de Paris de 1783", 0.90],
    ]

    collections = _categorized_text_features_from_ocr(
        blocks,
        legend_bounds=None,
        frame_bounds=FRAME_BOUNDS,
    )

    feat = collections[0]["features"][0]
    props = feat["properties"]
    assert props["recognized"] is False
    assert props["suggestedCity"] is None
    assert props["suggestedCoords"] is None
    assert props["name"] == "Traité de Paris de 1783"
    assert props["originalText"] == "Traité de Paris de 1783"


def test_find_nearby_candidate_city():
    # Test searching for Montreal near its real coordinates [-73.5673, 45.5017]
    montreal = find_nearby_candidate_city("Montréal", [-73.56, 45.50], radius_km=50.0)
    assert montreal is not None
    assert "montr" in montreal["name"].lower()

    # Test searching with minor OCR typo near coordinates
    typo_match = find_nearby_candidate_city("Montrel", [-73.56, 45.50], radius_km=50.0)
    assert typo_match is not None
    assert "montr" in typo_match["name"].lower()

    # Test that a city too far outside radius is not matched
    far_away = find_nearby_candidate_city("Paris", [-73.56, 45.50], radius_km=50.0)
    # Even if "Paris" is queried, if it is in Canada coordinates it should either return local city or None, never Paris France
    if far_away is not None:
        assert far_away["country"] != "FR"


