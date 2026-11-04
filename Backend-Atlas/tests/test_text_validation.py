"""Tests for text validation categorization and georeferencing."""

from app.tasks import _categorized_text_features_from_ocr
from app.utils.cities_validation import (
    MATCHING_CONFIG,
    find_nearby_candidate_place,
)

FRAME_BOUNDS = {"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0}
LEGEND_BOUNDS = {"x": 50.0, "y": 50.0, "width": 20.0, "height": 20.0}

QUEBEC_CITY = {
    "geonameid": 6325494,
    "name": "Québec",
    "lat": 46.8139,
    "lon": -71.2080,
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
    assert rec["properties"]["validationStatus"] == "accepted"
    assert rec["properties"]["matchedCity"] == "Québec"
    assert rec["geometry"]["coordinates"] == [-71.2080, 46.8139]

    # Check unrecognized feature (initialized with [0.0, 0.0], georeferenced later in batch)
    unrec = next(f for f in features if not f["properties"]["recognized"])
    assert unrec["properties"]["name"] == "UnkPlace"
    assert unrec["properties"]["originalText"] == "UnkPlace"
    assert unrec["properties"]["isOcrText"] is True
    assert unrec["properties"]["show"] is False
    assert unrec["properties"]["validationStatus"] == "manual_review"
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
    assert props["suggestedPlace"] is None
    assert props["name"] == "Traité de Paris de 1783"
    assert props["originalText"] == "Traité de Paris de 1783"


def test_categorized_text_features_only_accepts_nearby_fuzzy_place(monkeypatch):
    monkeypatch.setitem(MATCHING_CONFIG, "ocr_fuzzy_threshold", 0.70)
    frame_bounds = {"west": -10.0, "south": 35.0, "east": 40.0, "north": 70.0}

    nearby = _categorized_text_features_from_ocr(
        [
            [[[242, 599], [252, 599], [252, 609], [242, 609]], "Pariss", 0.95],
        ],
        legend_bounds=None,
        frame_bounds=frame_bounds,
        image_size=(1000, 1000),
    )[0]["features"][0]
    assert nearby["properties"]["recognized"] is True
    assert nearby["properties"]["name"] == "Paris"

    distant = _categorized_text_features_from_ocr(
        [
            [[[12, 889], [22, 889], [22, 899], [12, 899]], "Pariss", 0.95],
        ],
        legend_bounds=None,
        frame_bounds=frame_bounds,
        image_size=(1000, 1000),
    )[0]["features"][0]
    assert distant["properties"]["recognized"] is False
    assert distant["properties"]["validationStatus"] == "manual_review"
    assert distant["properties"]["name"] == "Pariss"
    assert distant["properties"]["suggestedPlace"] == {
        "name": "Paris",
        "coordinates": [2.3488, 48.85341],
        "type": "city",
    }


def test_categorized_text_features_ignores_numeric_and_scale_labels():
    features = _categorized_text_features_from_ocr(
        [
            [[[10, 10], [30, 10], [30, 20], [10, 20]], "1783", 0.95],
            [[[40, 10], [60, 10], [60, 20], [40, 20]], "600 Km", 0.95],
            [[[70, 10], [90, 10], [90, 20], [70, 20]], "Québec", 0.95],
        ],
        legend_bounds=None,
        frame_bounds=None,
    )

    assert [feature["features"][0]["properties"]["originalText"] for feature in features] == [
        "Québec"
    ]


def test_distant_fuzzy_json_match_is_unrecognized_with_json_suggestion(monkeypatch):
    json_entity = {
        "found": True,
        "name": "ONTARIO",
        "type": "province",
        "lat": 50.0,
        "lon": -85.0,
        "matchMethod": "fuzzy",
    }
    monkeypatch.setattr("app.tasks.match_ocr_label", lambda *args, **kwargs: json_entity)

    feature = _categorized_text_features_from_ocr(
        [
            [[[490, 490], [510, 490], [510, 510], [490, 510]], "Ontaro", 0.95],
        ],
        legend_bounds=None,
        frame_bounds={"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0},
        image_size=(1000, 1000),
    )[0]["features"][0]

    assert feature["properties"]["recognized"] is False
    assert feature["properties"]["validationStatus"] == "manual_review"
    assert feature["properties"]["suggestedPlace"] == {
        "name": "ONTARIO",
        "coordinates": [-85.0, 50.0],
        "type": "province",
    }


def test_find_nearby_candidate_place_matches_city_and_rejects_unrelated_text():
    # Test searching for Montreal near its real coordinates [-73.5673, 45.5017]
    montreal = find_nearby_candidate_place("Montréal", [-73.56, 45.50], radius_km=50.0)
    assert montreal is not None
    assert "montr" in montreal["name"].lower()

    # Test searching with minor OCR typo near coordinates
    typo_match = find_nearby_candidate_place("Montrel", [-73.56, 45.50], radius_km=50.0)
    assert typo_match is not None
    assert "montr" in typo_match["name"].lower()

    # Reject unexploitable / map noise text
    assert find_nearby_candidate_place("Échelle 1:10000", [-73.56, 45.50], radius_km=50.0) is None
    assert find_nearby_candidate_place("Légende", [-73.56, 45.50], radius_km=50.0) is None
    assert find_nearby_candidate_place("1783", [-73.56, 45.50], radius_km=50.0) is None

    # Do not auto-assimilate non-matching text to nearest city when similarity is insufficient
    assert find_nearby_candidate_place("TotallyUnrelatedWord", [-73.56, 45.50], radius_km=50.0) is None


def test_find_nearby_candidate_place_suggests_new_orleans_from_partial_ocr():
    candidate = find_nearby_candidate_place("La Nouvel", [-90.075, 29.955])

    assert candidate is not None
    assert candidate["name_fr"] == "La Nouvelle-Orléans"


def test_find_nearby_candidate_place_suggests_quebec_province_from_ocr_typo():
    candidate = find_nearby_candidate_place("Province de Quebe", [-73.707, 46.369])

    assert candidate is not None
    assert candidate["type"] == "province"
    assert candidate["name_fr"] == "Province de Québec"


def test_categorized_text_features_when_no_unrecognized_words(monkeypatch):
    """Ensure that when all words are recognized cities, no unrecognized features exist (window will not show)."""
    monkeypatch.setattr("app.tasks.match_ocr_label", _mock_match_ocr)

    blocks = [
        [[[10, 10], [30, 10], [30, 20], [10, 20]], "Quebec", 0.95],
    ]

    collections = _categorized_text_features_from_ocr(
        blocks,
        legend_bounds=None,
        frame_bounds=FRAME_BOUNDS,
    )

    features = [c["features"][0] for c in collections]
    unrecognized = [f for f in features if not f["properties"]["recognized"]]
    assert len(unrecognized) == 0
    assert len(features) == 1
    assert features[0]["properties"]["recognized"] is True


def test_json_matched_text_uses_ocr_position_but_geonames_city_keeps_cached_position(monkeypatch):
    from unittest.mock import MagicMock
    from app.tasks import _georeference_text_features

    json_entity = {
        "name": "Province de Québec",
        "type": "province",
        "lat": 46.8,
        "lon": -71.2,
    }

    def _mock_match(text, frame_bounds=None, target_pos=None):
        if text == "Province de Québec":
            return json_entity
        return QUEBEC_CITY

    monkeypatch.setattr("app.tasks.match_ocr_label", _mock_match)
    collections = _categorized_text_features_from_ocr(
        [
            [[[430, 650], [450, 650], [450, 670], [430, 670]], "Province de Québec", 0.95],
            [[[432, 652], [452, 652], [452, 672], [432, 672]], "Québec", 0.90],
        ],
        legend_bounds=None,
        frame_bounds=FRAME_BOUNDS,
        image_size=(1000, 1000),
    )

    features = [collection["features"][0] for collection in collections]
    province = next(feature for feature in features if feature["properties"]["type"] == "province")
    city = next(feature for feature in features if feature["properties"]["type"] == "city")
    assert province["properties"]["name"] == "PROVINCE DE QUÉBEC"
    assert province["geometry"]["coordinates"] == [-71.2, 46.8]
    assert city["geometry"]["coordinates"] == [QUEBEC_CITY["lon"], QUEBEC_CITY["lat"]]

    placement = MagicMock()
    placement.georeference.return_value = MagicMock(
        collections=[
            {
                "type": "FeatureCollection",
                "features": [{"geometry": {"type": "Point", "coordinates": [-76.5, 56.5]}}],
            }
        ]
    )

    _georeference_text_features(collections, placement)

    assert placement.georeference.call_args.args[0][0]["features"][0]["properties"] == {}
    assert province["geometry"]["coordinates"] == [-76.5, 56.5]
    assert province["properties"]["name"] == "PROVINCE DE QUÉBEC"
    assert province["properties"]["lat"] == json_entity["lat"]
    assert province["properties"]["lon"] == json_entity["lon"]
    assert city["geometry"]["coordinates"] == [QUEBEC_CITY["lon"], QUEBEC_CITY["lat"]]


def test_batch_georeference_and_candidate_association(monkeypatch):
    from unittest.mock import MagicMock
    from app.tasks import _georeference_text_features

    original_find_candidate = find_nearby_candidate_place
    search_radii = []

    def _find_candidate(text, coords, radius_km):
        search_radii.append(radius_km)
        return original_find_candidate(text, coords, radius_km)

    monkeypatch.setattr("app.tasks.find_nearby_candidate_place", _find_candidate)

    collections = [
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "Montrel",
                        "originalText": "Montrel",
                        "isOcrText": True,
                        "recognized": False,
                        "quad": [[10, 10], [20, 10], [20, 20], [10, 20]],
                    },
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                }
            ],
        }
    ]

    placement = MagicMock()
    # Mock georeferencing transform placing it near Montreal coordinates
    placement.georeference.return_value = MagicMock(
        collections=[
            {
                "type": "FeatureCollection",
                "features": [
                    {"geometry": {"type": "Point", "coordinates": [-73.567, 45.501]}}
                ],
            }
        ]
    )

    _georeference_text_features(collections, placement)

    feat = collections[0]["features"][0]
    assert feat["geometry"]["coordinates"] == [-73.567, 45.501]
    # Nearby place suggestion should be discovered by the shared candidate resolver.
    suggestion = feat["properties"]["suggestedPlace"]
    assert suggestion is not None
    assert "montr" in suggestion["name"].lower()
    assert suggestion["coordinates"] is not None
    assert suggestion["type"] == "city"
    assert search_radii == [MATCHING_CONFIG["suggestion_radius_km"]]


def test_text_feature_normalization_preserves_disjoint_validation_status():
    """Verify that backend feature storage strictly preserves disjoint validation states with explicit enum."""
    from app.models.features import ValidationStatus
    from app.utils.update_feature import normalize_feature_for_storage

    accepted_feature = {
        "id": "city-1",
        "geometry": {"type": "Point", "coordinates": [-71.2080, 46.8139]},
        "properties": {
            "name": "Québec",
            "isOcrText": True,
            "recognized": True,
            "show": True,
            "validation_status": ValidationStatus.ACCEPTED.value,
        },
    }

    rejected_feature = {
        "id": "text-2",
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        "properties": {
            "name": "Légende",
            "isOcrText": True,
            "recognized": False,
            "show": False,
            "validation_status": ValidationStatus.REJECTED.value,
        },
    }

    manual_review_feature = {
        "id": "text-3",
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
        "properties": {
            "name": "Chicoutmi",
            "isOcrText": True,
            "recognized": False,
            "show": False,
            "validation_status": ValidationStatus.MANUAL_REVIEW.value,
        },
    }

    norm_acc = normalize_feature_for_storage(accepted_feature)
    assert norm_acc["properties"]["validation_status"] == ValidationStatus.ACCEPTED
    assert norm_acc["properties"]["show"] is True
    assert norm_acc["properties"]["recognized"] is True

    norm_rej = normalize_feature_for_storage(rejected_feature)
    assert norm_rej["properties"]["validation_status"] == ValidationStatus.REJECTED
    assert norm_rej["properties"]["show"] is False
    assert norm_rej["properties"]["recognized"] is False

    norm_rev = normalize_feature_for_storage(manual_review_feature)
    assert norm_rev["properties"]["validation_status"] == ValidationStatus.MANUAL_REVIEW
    assert norm_rev["properties"]["show"] is False
    assert norm_rev["properties"]["recognized"] is False


def test_text_feature_normalization_harmonizes_camel_and_snake_status():
    """Verify that normalize_feature_for_storage resolves and synchronizes validationStatus and validation_status."""
    from app.models.features import ValidationStatus
    from app.utils.update_feature import normalize_feature_for_storage

    # Frontend payload may arrive with camelCase validationStatus
    feat_camel = {
        "properties": {
            "name": "Trois-Rivières",
            "isOcrText": True,
            "validationStatus": "accepted",
        }
    }
    norm = normalize_feature_for_storage(feat_camel)
    assert norm["properties"]["validation_status"] == ValidationStatus.ACCEPTED.value
    assert norm["properties"]["validationStatus"] == ValidationStatus.ACCEPTED.value
    assert norm["properties"]["show"] is True
    assert norm["properties"]["recognized"] is True

    # When both are present but diverge, valid non-null status is resolved
    feat_both = {
        "properties": {
            "name": "Trois-Rivières",
            "isOcrText": True,
            "validationStatus": "rejected",
            "validation_status": "manual_review",
        }
    }
    norm_both = normalize_feature_for_storage(feat_both)
    assert norm_both["properties"]["validation_status"] in (
        ValidationStatus.REJECTED.value,
        ValidationStatus.MANUAL_REVIEW.value,
    )
    assert (
        norm_both["properties"]["validation_status"]
        == norm_both["properties"]["validationStatus"]
    )
    assert norm_both["properties"]["show"] is False
    assert norm_both["properties"]["recognized"] is False


def test_text_feature_normalization_enforces_show_and_recognized_consistency():
    """Verify that show and recognized are forced into consistency with validation_status."""
    from app.models.features import ValidationStatus
    from app.utils.update_feature import normalize_feature_for_storage

    # Inconsistent state: accepted but show=False, recognized=False
    inconsistent_accepted = {
        "properties": {
            "validation_status": ValidationStatus.ACCEPTED.value,
            "show": False,
            "recognized": False,
        }
    }
    norm_acc = normalize_feature_for_storage(inconsistent_accepted)
    assert norm_acc["properties"]["show"] is True
    assert norm_acc["properties"]["recognized"] is True

    # Inconsistent state: rejected but show=True, recognized=True
    inconsistent_rejected = {
        "properties": {
            "validation_status": ValidationStatus.REJECTED.value,
            "show": True,
            "recognized": True,
        }
    }
    norm_rej = normalize_feature_for_storage(inconsistent_rejected)
    assert norm_rej["properties"]["show"] is False
    assert norm_rej["properties"]["recognized"] is False


def test_feature_serialization_includes_both_validation_status_formats():
    """Verify that serialize_db_feature ensures both validation_status and validationStatus are present."""
    from uuid import uuid4
    from app.models.features import Feature, ValidationStatus
    from app.utils.update_feature import serialize_db_feature

    row = Feature(
        id=uuid4(),
        project_id=uuid4(),
        map_id=uuid4(),
        data={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "Québec",
                        "validation_status": ValidationStatus.ACCEPTED.value,
                    },
                }
            ],
        },
    )
    serialized = serialize_db_feature(row)
    assert serialized is not None
    assert serialized["properties"]["validation_status"] == ValidationStatus.ACCEPTED.value
    assert serialized["properties"]["validationStatus"] == ValidationStatus.ACCEPTED.value
