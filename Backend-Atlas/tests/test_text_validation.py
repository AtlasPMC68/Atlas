"""Tests for text validation categorization and georeferencing."""

import uuid
from unittest.mock import MagicMock

from app.tasks import _categorized_text_features_from_ocr

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

    # Mock placement for georeferencing unrecognized text
    mock_placement = MagicMock()
    mock_georef_result = MagicMock()
    mock_georef_result.collections = [
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-73.5, 45.5]},
                }
            ],
        }
    ]
    mock_placement.georeference.return_value = mock_georef_result

    collections = _categorized_text_features_from_ocr(
        blocks,
        legend_bounds=LEGEND_BOUNDS,
        frame_bounds=FRAME_BOUNDS,
        placement=mock_placement,
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

    # Check unrecognized feature
    unrec = next(f for f in features if not f["properties"]["recognized"])
    assert unrec["properties"]["name"] == "UnkPlace"
    assert unrec["properties"]["originalText"] == "UnkPlace"
    assert unrec["properties"]["isOcrText"] is True
    assert unrec["properties"]["show"] is False
    assert unrec["geometry"]["coordinates"] == [-73.5, 45.5]

    # Verify placement.georeference was called with centroid of quad (120, 110)
    mock_placement.georeference.assert_called_once()
    called_fc = mock_placement.georeference.call_args[0][0][0]
    called_pt = called_fc["features"][0]["geometry"]["coordinates"]
    assert called_pt == [120.0, 110.0]


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
        placement=None,
    )

    features = [c["features"][0] for c in collections]
    assert len(features) == 2
    names = {f["properties"]["name"] for f in features}
    assert names == {"Québec", "Riviere"}

