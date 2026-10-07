"""The legend helpers and the import inputs: validation, merging, readiness."""

import cv2
import numpy as np
import pytest

from app.services.imports import (
    apply_inputs_patch,
    missing_inputs,
    parse_import_inputs,
)
from app.utils.color_extraction import extract_colors
from app.utils.legend import (
    legend_to_entry,
    parse_legend_bounds,
    parse_legend_entry,
)

FRAME = {"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0}
SIFT = [
    {
        "source": "sift",
        "pixel": {"x": float(i), "y": float(i * 2)},
        "geo": {"lon": -75.0 + i, "lat": 45.0},
    }
    for i in range(4)
]
ZONE = {"x": 0.2, "y": 0.2, "name": "Forest", "radius": 5, "kind": "zone", "hex": "#00ff00"}


# --- legend -------------------------------------------------------------------


def test_legend_bounds_are_validated():
    assert parse_legend_bounds({"x": 1, "y": 2, "width": 3, "height": 4}) == {
        "x": 1.0,
        "y": 2.0,
        "width": 3.0,
        "height": 4.0,
    }
    with pytest.raises(ValueError):
        parse_legend_bounds({"x": 1, "y": 2, "width": 0, "height": 4})
    with pytest.raises(ValueError):
        parse_legend_bounds({"x": 1, "y": 2})


def test_legend_entry_distinguishes_no_legend_from_no_answer():
    assert parse_legend_entry(None) == (False, None)
    assert parse_legend_entry(legend_to_entry(None)) == (True, None)
    bounds = {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}
    assert parse_legend_entry(legend_to_entry(bounds)) == (True, bounds)


def test_colour_extraction_leaves_the_legend_out(tmp_path):
    """A legend swatch the same colour as a zone must not become part of it,
    even when the zone encloses the legend and hole-filling would reclaim it."""
    image = np.full((60, 60, 3), 255, dtype=np.uint8)
    image[5:55, 5:55] = (0, 160, 0)  # the zone, enclosing...
    image[35:50, 35:50] = (255, 255, 255)  # ...a white legend box...
    image[40:45, 40:45] = (0, 160, 0)  # ...holding a swatch of the zone's colour
    path = str(tmp_path / "map.png")
    cv2.imwrite(path, image)

    legend = {"x": 35.0, "y": 35.0, "width": 15.0, "height": 15.0}
    result = extract_colors(
        path,
        legend_bounds=legend,
        imposed_click_positions=[(0.2, 0.2)],
        imposed_colors_names=["Forest"],
        imposed_sampling_radii=[3],
    )

    geometry = result["pixel_features"][0]["features"][0]["geometry"]
    from shapely.geometry import Point, shape

    zone = shape(geometry)
    assert zone.contains(Point(10, 10))
    assert not zone.contains(Point(42, 42))


# --- inputs -------------------------------------------------------------------


def test_patch_validates_and_merges():
    inputs = apply_inputs_patch({}, {"frameBounds": FRAME})
    inputs = apply_inputs_patch(inputs, {"controlPoints": SIFT, "colors": [ZONE]})
    assert inputs["frameBounds"] == FRAME
    assert len(inputs["controlPoints"]) == 4
    assert inputs["colors"][0]["hex"] == "#00ff00"

    with pytest.raises(ValueError):
        apply_inputs_patch(inputs, {"somethingElse": 1})
    with pytest.raises(ValueError):
        apply_inputs_patch(inputs, {"colors": [{"x": 2, "y": 0}]})


def test_shape_clicks_are_validated_and_named():
    inputs = apply_inputs_patch(
        {}, {"shapes": [{"x": 0.4, "y": 0.6, "name": " Cercle "}, {"x": 0.1, "y": 0.2}]}
    )
    parsed = parse_import_inputs(inputs)
    assert parsed.shape_clicks == [(0.4, 0.6), (0.1, 0.2)]
    assert parsed.shape_names == ["Cercle", "Forme 2"]

    with pytest.raises(ValueError, match="normalised"):
        apply_inputs_patch({}, {"shapes": [{"x": 1.5, "y": 0.2}]})
    with pytest.raises(ValueError, match="at most"):
        apply_inputs_patch({}, {"shapes": [{"x": 0.1, "y": 0.1}] * 51})


def test_a_new_frame_clears_the_control_points():
    inputs = apply_inputs_patch({}, {"frameBounds": FRAME, "controlPoints": SIFT})
    moved = apply_inputs_patch(inputs, {"frameBounds": {**FRAME, "west": -90.0}})
    assert "controlPoints" not in moved

    same = apply_inputs_patch(inputs, {"frameBounds": dict(FRAME)})
    assert len(same["controlPoints"]) == 4


def test_a_first_frame_keeps_the_control_points():
    """No point was matched under a box that did not exist: a case made before
    the framing box gets one without losing its clicks."""
    unframed = apply_inputs_patch({}, {"controlPoints": SIFT})
    framed = apply_inputs_patch(unframed, {"frameBounds": FRAME})
    assert framed["frameBounds"] == FRAME
    assert len(framed["controlPoints"]) == 4


def test_null_clears_an_input():
    inputs = apply_inputs_patch({}, {"legend": legend_to_entry(None)})
    assert inputs["legend"] == {"present": False, "bounds": None}
    assert "legend" not in apply_inputs_patch(inputs, {"legend": None})


def test_missing_inputs_follow_the_checklist():
    assert missing_inputs(parse_import_inputs({})) == [
        "Zone sur le monde",
        "Délimiter la légende",
        "Points SIFT (au moins 3)",
        "Couleurs à extraire (au moins une zone)",
    ]

    complete = {
        "frameBounds": FRAME,
        "legend": legend_to_entry(None),
        "controlPoints": SIFT,
        "colors": [ZONE],
    }
    assert missing_inputs(parse_import_inputs(complete)) == []

    water_only = {**complete, "colors": [{**ZONE, "kind": "water"}]}
    assert missing_inputs(parse_import_inputs(water_only)) == [
        "Couleurs à extraire (au moins une zone)"
    ]
