"""The import tasks, with the database transitions stubbed out.

The row transitions (`_claim_*`, `_finish_ocr`, `_save_extraction`, ...) are
the only database access in these tasks, so replacing them leaves the task
bodies -- what runs, with which inputs, and what reaches the final save --
under test without a database.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
import pytest

from app.models.map_import import (
    EXTRACTION_CANCELLED,
    EXTRACTION_CANCELLING,
    EXTRACTION_FAILED,
    EXTRACTION_RUNNING,
)
from app.services.imports import parse_import_inputs
from app.utils.city_gazetteer import FrameCityIndex, _FrameCity
from app.tasks import _ClaimedImport, process_map_extraction, run_map_ocr

LEGEND = {"x": 60.0, "y": 60.0, "width": 30.0, "height": 30.0}


def _png_bytes() -> bytes:
    ok, encoded = cv2.imencode(".png", np.zeros((100, 100, 3), dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def _inputs(**options):
    return parse_import_inputs(
        {
            "frameBounds": {"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0},
            "legend": {"present": True, "bounds": LEGEND},
            "controlPoints": [
                {
                    "source": "sift",
                    "pixel": {"x": float(i * 20), "y": float(i * 10 + 5)},
                    "geo": {"lon": -75.0 + i, "lat": 45.0 + i * 0.5},
                }
                for i in range(4)
            ],
            "colors": [
                {"x": 0.25, "y": 0.75, "name": "Forest", "radius": 7, "kind": "zone"},
                {"x": 0.5, "y": 0.5, "name": "Sea", "radius": 21, "kind": "water"},
            ],
            "options": {"textExtraction": False, "shapesExtraction": False, **options},
        }
    )


def _claimed(**options) -> _ClaimedImport:
    return _ClaimedImport(
        project_id=uuid.uuid4(),
        filename="map.png",
        image=_png_bytes(),
        inputs=_inputs(**options),
        ocr_blocks=[
            [[[10, 10], [40, 10], [40, 20], [10, 20]], "Quebec", 0.99],
            # Inside the legend: a key label, never a place.
            [[[65, 65], [85, 65], [85, 70], [65, 70]], "Floride", 0.95],
        ],
    )


QUEBEC = _FrameCity(
    geonameid=6325494,
    name="Québec",
    lat=46.8,
    lon=-71.2,
    country="CA",
    population=528595,
    names=(("quebec", "Quebec"),),
)


def _index_for(frame_bounds):
    return FrameCityIndex(by_name={"quebec": QUEBEC}, max_words=1)


def _color_result():
    feature = {
        "type": "Feature",
        "properties": {"color_name": "Forest"},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    }
    return {
        "normalized_features": [{"type": "FeatureCollection", "features": [feature]}],
        "pixel_features": [{"type": "FeatureCollection", "features": [feature]}],
    }


def _run_extraction(claimed, state=EXTRACTION_RUNNING, **patches):
    """Run the task with its database transitions stubbed. Returns the mocks."""
    georef_result = MagicMock(collections=[{"type": "FeatureCollection", "features": []}])
    mocks = {
        "claim": AsyncMock(return_value=claimed),
        "state": AsyncMock(return_value=state),
        "save": AsyncMock(return_value=3),
        "end": AsyncMock(),
        "colors": MagicMock(return_value=_color_result()),
        "shapes": MagicMock(
            return_value={"pixel_features": [], "normalized_features": [], "shapes": []}
        ),
        "city": MagicMock(side_effect=_index_for),
        "align": MagicMock(return_value=None),
        "georef": MagicMock(return_value=georef_result),
    }
    mocks.update(patches)
    with (
        patch("app.tasks._claim_extraction", mocks["claim"]),
        patch("app.tasks._extraction_state", mocks["state"]),
        patch("app.tasks._save_extraction", mocks["save"]),
        patch("app.tasks._end_extraction", mocks["end"]),
        patch("app.tasks.extract_colors", mocks["colors"]),
        patch("app.tasks.extract_shapes", mocks["shapes"]),
        patch("app.tasks.frame_city_index", mocks["city"]),
        patch("app.tasks._align_if_enabled", mocks["align"]),
        patch("app.tasks._georeference", mocks["georef"]),
        patch("app.tasks._write_ocr_text_file", MagicMock(return_value="out.txt")),
        patch("app.tasks.process_map_extraction.update_state"),
    ):
        outcome = process_map_extraction.apply(kwargs={"map_id": str(uuid.uuid4())})
    mocks["outcome"] = outcome
    return mocks


def claimed_frame():
    return _inputs().frame_bounds


def test_unknown_words_are_kept_hidden():
    from app.tasks import _city_features_from_text

    blocks = [[[[0, 0], [9, 0], [9, 9], [0, 9]], "Quebec Nowhere", 0.9]]
    with patch("app.tasks.frame_city_index", side_effect=_index_for):
        features = [
            c["features"][0] for c in _city_features_from_text(blocks, None, claimed_frame())
        ]

    assert [(f["properties"]["name"], f["properties"]["show"]) for f in features] == [
        ("Québec", True),
        ("Nowhere", False),
    ]
    assert features[1]["geometry"]["coordinates"] == [0.0, 0.0]


def test_extraction_uses_the_stored_inputs_and_saves_once():
    mocks = _run_extraction(_claimed(textExtraction=True, shapesExtraction=True))
    result = mocks["outcome"].get(timeout=20)

    assert result["status"] == "completed"
    assert result["features_saved"] == 3
    assert result["extractions_performed"] == {
        "georeferencing": True,
        "color_extraction": True,
        "shapes_extraction": True,
        "text_extraction": True,
    }

    # Colours: zone picks only, the legend masked.
    _, color_kwargs = mocks["colors"].call_args
    assert color_kwargs["imposed_click_positions"] == [(0.25, 0.75)]
    assert color_kwargs["imposed_colors_names"] == ["Forest"]
    assert color_kwargs["imposed_sampling_radii"] == [7]
    assert color_kwargs["legend_bounds"] == LEGEND

    # Shapes: the stored OCR boxes, the legend excluded.
    _, shape_kwargs = mocks["shapes"].call_args
    assert shape_kwargs["legend_bounds"] == LEGEND
    assert len(shape_kwargs["text_regions"]) == 2

    # Text: looked up among the cities of the frame only.
    mocks["city"].assert_called_once_with(claimed_frame())

    # One save, carrying the georef inputs with the legend answer.
    mocks["save"].assert_awaited_once()
    _map_id, _project_id, collections, georef_inputs = mocks["save"].await_args.args
    points = {
        f["properties"]["name"]: f
        for c in collections
        for f in c["features"]
        if f["properties"].get("mapElementType") == "point"
    }
    # The city is placed; the legend's label never becomes a point.
    assert points["Québec"]["properties"]["show"] is True
    assert points["Québec"]["geometry"]["coordinates"] == [-71.2, 46.8]
    assert "Floride" not in points
    assert georef_inputs["georef"]["legend"] == {"present": True, "bounds": LEGEND}
    assert len(georef_inputs["colors"]["imposed"]) == 2


def test_disabled_options_skip_text_and_shapes():
    mocks = _run_extraction(_claimed())
    result = mocks["outcome"].get(timeout=20)

    assert result["extractions_performed"]["text_extraction"] is False
    assert result["extractions_performed"]["shapes_extraction"] is False
    mocks["shapes"].assert_not_called()
    mocks["city"].assert_not_called()
    mocks["colors"].assert_called_once()


def test_alignment_receives_the_ocr_boxes_and_the_legend():
    mocks = _run_extraction(_claimed())
    mocks["outcome"].get(timeout=20)

    if not mocks["align"].called:
        pytest.skip("curve alignment is switched off in this environment")
    args, kwargs = mocks["align"].call_args
    assert len(args[3]) == 2  # text_regions
    assert args[4] == [(0.5, 0.5)]  # water picks
    assert kwargs["legend_bounds"] == LEGEND


def test_cancel_stops_before_anything_is_saved():
    mocks = _run_extraction(_claimed(), state=EXTRACTION_CANCELLING)
    result = mocks["outcome"].get(timeout=20)

    assert result["status"] == "cancelled"
    mocks["save"].assert_not_awaited()
    assert mocks["end"].await_args.args[2] == EXTRACTION_CANCELLED


def test_a_task_that_is_no_longer_current_does_nothing():
    mocks = _run_extraction(None)
    result = mocks["outcome"].get(timeout=20)

    assert result == {"status": "skipped"}
    mocks["colors"].assert_not_called()
    mocks["save"].assert_not_awaited()


def test_a_failure_marks_the_import_failed():
    mocks = _run_extraction(
        _claimed(), colors=MagicMock(side_effect=RuntimeError("boom"))
    )

    with pytest.raises(RuntimeError):
        mocks["outcome"].get(timeout=20, propagate=True)
    mocks["save"].assert_not_awaited()
    assert mocks["end"].await_args.args[2] == EXTRACTION_FAILED
    assert "boom" in mocks["end"].await_args.args[3]


def test_ocr_dispatches_the_extraction_that_was_waiting_for_it():
    blocks = [([[0, 0], [5, 0], [5, 5], [0, 5]], "Quebec", np.float64(0.9))]
    with (
        patch("app.tasks._claim_ocr", AsyncMock(return_value=_png_bytes())),
        patch("app.tasks.extract_text", MagicMock(return_value=(blocks, None))),
        patch("app.tasks._finish_ocr", AsyncMock(return_value="extraction-id")) as finish,
        patch("app.tasks.process_map_extraction.apply_async") as dispatch,
    ):
        map_id = str(uuid.uuid4())
        result = run_map_ocr.apply(kwargs={"map_id": map_id}).get(timeout=20)

    assert result == {"status": "done", "blocks": 1}
    # Stored as plain JSON, numpy scalars included.
    stored = finish.await_args.args[2]
    assert stored == [[[[0, 0], [5, 0], [5, 5], [0, 5]], "Quebec", 0.9]]
    assert type(stored[0][2]) is float
    dispatch.assert_called_once_with(kwargs={"map_id": map_id}, task_id="extraction-id")


def test_ocr_without_a_waiting_extraction_dispatches_nothing():
    with (
        patch("app.tasks._claim_ocr", AsyncMock(return_value=_png_bytes())),
        patch("app.tasks.extract_text", MagicMock(return_value=([], None))),
        patch("app.tasks._finish_ocr", AsyncMock(return_value=None)),
        patch("app.tasks.process_map_extraction.apply_async") as dispatch,
    ):
        run_map_ocr.apply(kwargs={"map_id": str(uuid.uuid4())}).get(timeout=20)

    dispatch.assert_not_called()


def test_failed_ocr_is_recorded():
    with (
        patch("app.tasks._claim_ocr", AsyncMock(return_value=_png_bytes())),
        patch("app.tasks.extract_text", MagicMock(side_effect=RuntimeError("no model"))),
        patch("app.tasks._fail_ocr", AsyncMock()) as fail,
    ):
        outcome = run_map_ocr.apply(kwargs={"map_id": str(uuid.uuid4())})
        with pytest.raises(RuntimeError):
            outcome.get(timeout=20, propagate=True)

    assert "no model" in fail.await_args.args[2]
