"""The legend helpers and the import inputs: validation, merging, readiness."""

import asyncio
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.models.features import Feature
from app.models.map import Map
from app.routers import imports as imports_router, projects as projects_router
from app.schemas.mapImportRequest import MapImportRequest
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
    point_in_any_bounds,
    polygon_center_in_ignored_areas,
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


def test_ignored_areas_validation_and_merging():
    """Ignored areas (exclusion zones) must be validated and stored independently."""
    rect1 = {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0}
    rect2 = {"x": 50.0, "y": 60.0, "width": 70.0, "height": 80.0}
    inputs = apply_inputs_patch({}, {"ignoredAreas": [rect1, rect2]})
    assert len(inputs["ignoredAreas"]) == 2
    assert inputs["ignoredAreas"][0] == rect1
    assert inputs["ignoredAreas"][1] == rect2

    # exclusionZones is an alias
    inputs_alias = apply_inputs_patch({}, {"exclusionZones": [rect1]})
    assert inputs_alias["ignoredAreas"] == [rect1]

    # Malformed entries are rejected
    with pytest.raises(ValueError):
        apply_inputs_patch({}, {"ignoredAreas": "not a list"})
    with pytest.raises(ValueError):
        apply_inputs_patch({}, {"ignoredAreas": [{"x": 10, "y": 20, "width": -5, "height": 10}]})


def test_independent_legend_and_exclusion_zones():
    """Legend and exclusion zones must remain fully independent when saving and updating."""
    legend = {"x": 10.0, "y": 10.0, "width": 50.0, "height": 50.0}
    rect1 = {"x": 100.0, "y": 100.0, "width": 30.0, "height": 30.0}

    # 1. Save legend first
    inputs = apply_inputs_patch({}, {"legend": legend_to_entry(legend)})
    assert inputs["legend"] == {"present": True, "bounds": legend}
    assert "ignoredAreas" not in inputs

    # 2. Add exclusion zones - legend remains intact
    inputs = apply_inputs_patch(inputs, {"ignoredAreas": [rect1]})
    assert inputs["legend"] == {"present": True, "bounds": legend}
    assert inputs["ignoredAreas"] == [rect1]

    # 3. Update exclusion zones - legend remains intact
    rect2 = {"x": 200.0, "y": 200.0, "width": 40.0, "height": 40.0}
    inputs = apply_inputs_patch(inputs, {"ignoredAreas": [rect1, rect2]})
    assert inputs["legend"] == {"present": True, "bounds": legend}
    assert len(inputs["ignoredAreas"]) == 2

    # 4. Modify legend (or set to no legend) - exclusion zones remain intact
    inputs = apply_inputs_patch(inputs, {"legend": legend_to_entry(None)})
    assert inputs["legend"] == {"present": False, "bounds": None}
    assert len(inputs["ignoredAreas"]) == 2

    # 5. Parsing preserves both
    parsed = parse_import_inputs(inputs)
    assert parsed.legend_answered is True
    assert parsed.legend_bounds is None
    assert len(parsed.ignored_areas) == 2


def test_polygon_center_in_ignored_areas():
    """Points inside exclusion zones are detected, while points outside are not."""
    zones = [
        {"x": 10.0, "y": 10.0, "width": 50.0, "height": 50.0},
        {"x": 100.0, "y": 100.0, "width": 40.0, "height": 40.0},
    ]
    # Inside zone 1
    assert polygon_center_in_ignored_areas([[20, 20], [30, 20], [30, 30], [20, 30]], zones) is True
    # Inside zone 2
    assert polygon_center_in_ignored_areas([[110, 110], [120, 110], [120, 120], [110, 120]], zones) is True
    # Outside all zones
    assert polygon_center_in_ignored_areas([[70, 70], [80, 70], [80, 80], [70, 80]], zones) is False
    # None or empty zones
    assert polygon_center_in_ignored_areas([[20, 20]], None) is False
    assert polygon_center_in_ignored_areas([[20, 20]], []) is False


def test_categorized_text_features_from_ocr_filters_ignored_areas(monkeypatch):
    """OCR text within ignored areas (scale, compass, title) must be rejected."""
    from app.tasks import _categorized_text_features_from_ocr

    monkeypatch.setattr("app.tasks.match_ocr_label", lambda text, *args, **kwargs: None)

    legend = {"x": 10.0, "y": 10.0, "width": 50.0, "height": 50.0}
    scale_zone = {"x": 200.0, "y": 200.0, "width": 80.0, "height": 30.0}
    compass_zone = {"x": 300.0, "y": 300.0, "width": 40.0, "height": 40.0}

    # Blocks:
    # 1: Inside legend -> rejected
    # 2: Inside scale_zone (ignored area) -> rejected
    # 3: Inside compass_zone (ignored area) -> rejected
    # 4: Outside (geographical text) -> accepted as unrecognized feature for validation
    blocks = [
        [[[20, 20], [40, 20], [40, 30], [20, 30]], "LegendLabel", 0.99],
        [[[220, 210], [250, 210], [250, 220], [220, 220]], "ScaleLabel", 0.95],
        [[[310, 310], [330, 310], [330, 330], [310, 330]], "CompassLabel", 0.90],
        [[[500, 500], [550, 500], [550, 520], [500, 520]], "UnkPlace", 0.88],
    ]

    frame = {"west": -75.0, "south": 45.0, "east": -70.0, "north": 50.0}
    result = _categorized_text_features_from_ocr(
        blocks,
        legend_bounds=legend,
        frame_bounds=frame,
        image_size=(1000, 1000),
        ignored_areas=[scale_zone, compass_zone],
    )

    # Only UnkPlace should survive (not legend, not scale, not compass)
    names = [c["features"][0]["properties"]["name"] for c in result]
    assert "UnkPlace" in names
    assert "LegendLabel" not in names
    assert "ScaleLabel" not in names
    assert "CompassLabel" not in names
    assert len(result) == 1


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
    assert missing_inputs(parse_import_inputs(water_only)) == ["Couleurs à extraire (au moins une zone)"]


def test_reference_images_are_saved_and_retrieved_per_map(monkeypatch):
    map_ids = [uuid4(), uuid4()]
    map_objects = {map_id: Map(id=map_id) for map_id in map_ids}

    async def require_owned_map(_session, map_id, _user_id):
        return map_objects[map_id]

    monkeypatch.setattr(imports_router, "_require_owned_map", require_owned_map)
    session = SimpleNamespace(commit=AsyncMock())
    images = [b"first map image", b"second map image"]

    for map_id, image in zip(map_ids, images):
        upload = UploadFile(
            filename="reference.png",
            file=BytesIO(image),
            headers=Headers({"content-type": "image/png"}),
        )
        asyncio.run(imports_router.save_reference_image(map_id, upload, str(uuid4()), session))

    for map_id, expected_image in zip(map_ids, images):
        response = asyncio.run(imports_router.get_reference_image(map_id, str(uuid4()), session))
        with open(response.path, "rb") as f:
            assert f.read() == expected_image
        assert response.media_type == "image/png"

    asyncio.run(imports_router.delete_reference_image(map_ids[0], str(uuid4()), session))
    with pytest.raises(HTTPException) as error:
        asyncio.run(imports_router.get_reference_image(map_ids[0], str(uuid4()), session))
    assert error.value.status_code == 404
    resp1 = asyncio.run(imports_router.get_reference_image(map_ids[1], str(uuid4()), session))
    with open(resp1.path, "rb") as f:
        assert f.read() == images[1]


def test_reference_image_rejects_non_image_upload(monkeypatch):
    map_id = uuid4()
    map_obj = Map(id=map_id)

    async def require_owned_map(_session, _map_id, _user_id):
        return map_obj

    monkeypatch.setattr(imports_router, "_require_owned_map", require_owned_map)
    upload = UploadFile(
        filename="not-an-image.txt",
        file=BytesIO(b"not an image"),
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(imports_router.save_reference_image(map_id, upload, str(uuid4()), SimpleNamespace()))
    assert error.value.status_code == 400


def test_update_map_metadata_saves_title_and_complete_period():
    project_id = uuid4()
    map_obj = Map(id=uuid4(), project_id=project_id)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: map_obj)),
        commit=AsyncMock(),
    )
    request = MapImportRequest(
        title="  Carte de Québec  ",
        start_date="1850-02-01",
        end_date="1860-11-30",
        exact_date=True,
    )

    response = asyncio.run(
        projects_router.update_map_metadata(
            project_id,
            map_obj.id,
            request,
            str(uuid4()),
            session,
        )
    )

    assert response == {"map_id": str(map_obj.id)}
    assert map_obj.title == "Carte de Québec"
    assert map_obj.start_date.isoformat() == "1850-02-01"
    assert map_obj.end_date.isoformat() == "1860-11-30"
    assert map_obj.exact_date is True
    session.commit.assert_awaited_once()


def test_update_map_metadata_rejects_reversed_period_before_querying():
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    request = MapImportRequest(
        title="Carte",
        start_date="1860-01-01",
        end_date="1850-12-31",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            projects_router.update_map_metadata(
                uuid4(),
                uuid4(),
                request,
                str(uuid4()),
                session,
            )
        )

    assert error.value.status_code == 400
    session.execute.assert_not_awaited()


def test_project_timeline_excludes_maps_with_an_unfinished_import():
    project_id = uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: project_id),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])),
    ]
        )
    )

    response = asyncio.run(
        projects_router.get_project_maps(
            str(project_id),
            str(uuid4()),
            session,
        )
    )

    map_query = session.execute.await_args_list[1].args[0]
    query_sql = str(map_query).lower()
    assert response == []
    assert "map_imports" in query_sql
    assert "not in" in query_sql


def test_delete_reference_image_clears_field_and_commits():
    map_id = uuid4()
    map_obj = Map(id=map_id, reference_image_path="reference_images/test.png")
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: map_obj)),
        commit=AsyncMock(),
    )

    response = asyncio.run(
        imports_router.delete_reference_image(map_id, str(uuid4()), session)
    )

    assert response == {"detail": "Reference image deleted"}
    assert map_obj.reference_image_path is None
    session.commit.assert_awaited_once()


def test_update_map_metadata_rejects_non_owner():
    project_id = uuid4()
    map_id = uuid4()
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        commit=AsyncMock(),
    )
    request = MapImportRequest(
        title="Carte",
        start_date="1850-01-01",
        end_date="1860-01-01",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            projects_router.update_map_metadata(
                project_id,
                map_id,
                request,
                str(uuid4()),
                session,
            )
        )

    assert error.value.status_code == 404


def test_update_project_label_styles_persists_point_options():
    from app.models.project import Project
    from app.schemas.label_styles import LabelStyle, LabelStylesRequest

    project_id = uuid4()
    user_id = uuid4()
    mock_project = Project(id=project_id, user_id=user_id, label_styles=[])

    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: mock_project)),
        commit=AsyncMock(),
    )
    request = LabelStylesRequest(
        styles=[
            LabelStyle(
                id="style-with-point",
                name="Point Style",
                size_px=14,
                font_style="normal",
                text_transform="none",
                color="#000000",
                has_point=True,
                point_color="#ff5500",
                point_stroke_color="#000000",
                point_fill_opacity=0.8,
                point_stroke_opacity=1.0,
                point_stroke_width=2.0,
            ),
        ]
    )

    result = asyncio.run(
        projects_router.update_project_label_styles(
            project_id,
            request,
            str(user_id),
            session,
        )
    )

    session.commit.assert_awaited_once()
    assert len(result) == 1
    assert result[0]["id"] == "style-with-point"
    assert result[0]["has_point"] is True
    assert result[0]["point_color"] == "#ff5500"
    assert result[0]["point_fill_opacity"] == 0.8


def test_update_project_label_styles_rejects_duplicate_ids():
    from app.schemas.label_styles import LabelStyle, LabelStylesRequest

    project_id = uuid4()
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    request = LabelStylesRequest(
        styles=[
            LabelStyle(
                id="style-duplicate",
                name="Style 1",
                size_px=14,
                font_style="normal",
                text_transform="none",
                color="#ff0000",
            ),
            LabelStyle(
                id="style-duplicate",
                name="Style 2",
                size_px=16,
                font_style="italic",
                text_transform="uppercase",
                color="#00ff00",
            ),
        ]
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            projects_router.update_project_label_styles(
                project_id,
                request,
                str(uuid4()),
                session,
            )
        )

    assert error.value.status_code == 400
    assert "unique" in error.value.detail.lower()
    session.execute.assert_not_awaited()


def test_get_project_label_styles_returns_empty_list_when_column_is_null():
    project_id = uuid4()
    project_obj = SimpleNamespace(id=project_id, label_styles=None)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: project_obj))
    )

    result = asyncio.run(
        projects_router.get_project_label_styles(
            project_id,
            str(uuid4()),
            session,
        )
    )

    assert result == []


def test_require_owned_map_rejects_invalid_user_uuid():
    map_id = uuid4()
    session = SimpleNamespace()

    with pytest.raises(HTTPException) as error:
        asyncio.run(imports_router._require_owned_map(session, map_id, "invalid-user-uuid"))

    assert error.value.status_code == 401


def test_reference_image_rejects_empty_upload(monkeypatch):
    map_id = uuid4()
    map_obj = Map(id=map_id, reference_image_path=None)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: map_obj)),
        commit=AsyncMock(),
    )
    monkeypatch.setattr(imports_router, "_require_owned_map", AsyncMock(return_value=map_obj))

    upload = UploadFile(
        file=BytesIO(b""),
        filename="empty.png",
        headers=Headers({"content-type": "image/png"}),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(imports_router.save_reference_image(map_id, upload, str(uuid4()), session))

    assert error.value.status_code == 400
    assert "empty" in error.value.detail.lower()


def test_get_reference_image_raises_404_when_no_image(monkeypatch):
    map_id = uuid4()
    map_obj = Map(id=map_id, reference_image_path=None)
    monkeypatch.setattr(imports_router, "_require_owned_map", AsyncMock(return_value=map_obj))

    with pytest.raises(HTTPException) as error:
        asyncio.run(imports_router.get_reference_image(map_id, str(uuid4()), SimpleNamespace()))

    assert error.value.status_code == 404
    assert "no reference image" in error.value.detail.lower()


def test_update_features_supports_map_id_and_camelcase_mapId():
    project_id = uuid4()
    target_map_id = uuid4()

    # Feature using camelCase mapId
    payload = [
        {
            "id": str(uuid4()),
            "mapId": str(target_map_id),
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {"name": "Test Feature"},
        }
    ]

    added_features = []
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                # Project lookup
                SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=project_id)),
                # Existing features lookup
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])),
                # Project maps lookup
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [target_map_id])),
                # Refreshed features lookup
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: added_features)),
            ]
        ),
        add=lambda feat: added_features.append(feat),
        commit=AsyncMock(),
    )

    response = asyncio.run(
        projects_router.update_features(
            project_id=project_id,
            features=payload,
            user_id=str(uuid4()),
            session=session,
        )
    )

    assert isinstance(response, list)
    assert len(added_features) == 1
    assert added_features[0].map_id == target_map_id


def test_update_features_ignores_map_id_from_another_project():
    project_id = uuid4()
    own_map_id = uuid4()
    foreign_map_id = uuid4()

    payload = [
        {
            "type": "Feature",
            "map_id": str(foreign_map_id),
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {"name": "Foreign"},
        }
    ]

    added_features = []
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(id=project_id)),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [])),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [own_map_id])),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: added_features)),
            ]
        ),
        add=lambda feat: added_features.append(feat),
        commit=AsyncMock(),
    )

    asyncio.run(
        projects_router.update_features(
            project_id=project_id,
            features=payload,
            user_id=str(uuid4()),
            session=session,
        )
    )

    assert len(added_features) == 1
    assert added_features[0].map_id is None


def test_duplicate_map_rejects_empty_title():
    project_id = uuid4()
    map_id = uuid4()
    session = SimpleNamespace()
    request = MapImportRequest(
        title="   ",
        start_date="1850-01-01",
        end_date="1860-01-01",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            projects_router.duplicate_map_for_project(
                project_id,
                map_id,
                request,
                str(uuid4()),
                session,
            )
        )
    assert error.value.status_code == 400
    assert "title must not be empty" in error.value.detail


def test_duplicate_map_rejects_reversed_period():
    project_id = uuid4()
    map_id = uuid4()
    session = SimpleNamespace()
    request = MapImportRequest(
        title="Carte Copie",
        start_date="1870-01-01",
        end_date="1850-01-01",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            projects_router.duplicate_map_for_project(
                project_id,
                map_id,
                request,
                str(uuid4()),
                session,
            )
        )
    assert error.value.status_code == 400
    assert "start_date must be before or equal to end_date" in error.value.detail


def test_duplicate_map_for_project_success(monkeypatch):
    project_id = uuid4()
    map_id = uuid4()
    new_id = uuid4()
    session = SimpleNamespace()
    request = MapImportRequest(
        title="Carte Copie",
        start_date="1850-01-01",
        end_date="1860-01-01",
    )

    duplicate_mock = AsyncMock(return_value=new_id)
    monkeypatch.setattr("app.routers.projects.duplicate_map_in_project", duplicate_mock)

    user_uuid = uuid4()
    res = asyncio.run(
        projects_router.duplicate_map_for_project(
            project_id,
            map_id,
            request,
            str(user_uuid),
            session,
        )
    )
    assert res == {"map_id": str(new_id)}
    duplicate_mock.assert_awaited_once_with(
        db=session,
        project_id=project_id,
        source_map_id=map_id,
        user_id=user_uuid,
        new_title="Carte Copie",
        start_date=date(1850, 1, 1),
        end_date=date(1860, 1, 1),
        exact_date=False,
    )


def test_duplicate_map_in_project_service(tmp_path, monkeypatch):
    from app.services.maps import duplicate_map_in_project
    from app.models.project import Project

    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    user_id = uuid4()
    project_id = uuid4()
    source_map_id = uuid4()

    # Create dummy source reference image
    ref_dir = tmp_path / "reference_images"
    ref_dir.mkdir(parents=True)
    source_img = ref_dir / f"{source_map_id}.png"
    source_img.write_bytes(b"PNG_DATA")

    project = Project(id=project_id, user_id=user_id)
    source_map = Map(
        id=source_map_id,
        project_id=project_id,
        title="Source",
        start_date=date(1800, 1, 1),
        end_date=date(1850, 1, 1),
        reference_image_path=f"reference_images/{source_map_id}.png",
        reference_image_content_type="image/png",
    )
    source_feature = Feature(
        id=uuid4(),
        project_id=project_id,
        map_id=source_map_id,
        data={"type": "Feature", "properties": {"name": "Ville", "mapId": str(source_map_id)}},
    )

    added = []
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: project),
                SimpleNamespace(scalar_one_or_none=lambda: source_map),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [source_feature])),
            ]
        ),
        add=lambda obj: added.append(obj),
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    new_map_id = asyncio.run(
        duplicate_map_in_project(
            db=session,
            project_id=project_id,
            source_map_id=source_map_id,
            user_id=user_id,
            new_title="Nouvelle Carte",
        )
    )

    assert new_map_id is not None
    duplicated_map = next(o for o in added if isinstance(o, Map))
    assert duplicated_map.title == "Nouvelle Carte"
    # Ensure independent image copy was created on disk
    expected_new_img = ref_dir / f"{duplicated_map.id}.png"
    assert expected_new_img.exists()
    assert expected_new_img.read_bytes() == b"PNG_DATA"
    assert duplicated_map.reference_image_path == f"reference_images/{duplicated_map.id}.png"

    # Ensure feature was copied with new uuid and new mapId
    duplicated_feat = next(o for o in added if isinstance(o, Feature))
    assert duplicated_feat.map_id == duplicated_map.id
    assert duplicated_feat.data["mapId"] == str(duplicated_map.id)
    assert duplicated_feat.data["properties"]["mapId"] == str(duplicated_map.id)


def test_duplicate_map_in_project_feature_collection(tmp_path, monkeypatch):
    from app.services.maps import duplicate_map_in_project
    from app.models.project import Project

    monkeypatch.setenv("MEDIA_ROOT", str(tmp_path))
    user_id = uuid4()
    project_id = uuid4()
    source_map_id = uuid4()

    project = Project(id=project_id, user_id=user_id)
    source_map = Map(
        id=source_map_id,
        project_id=project_id,
        title="Source",
        start_date=date(1500, 1, 1),
        end_date=date(1501, 1, 1),
    )
    source_feature = Feature(
        id=uuid4(),
        project_id=project_id,
        map_id=source_map_id,
        data={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": str(uuid4()),
                    "properties": {
                        "name": "Zone 1",
                        "mapElementType": "zone",
                        "mapId": str(source_map_id),
                        "startYear": 1500,
                        "endYear": 1501,
                    },
                }
            ],
        },
    )

    added = []
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: project),
                SimpleNamespace(scalar_one_or_none=lambda: source_map),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [source_feature])),
            ]
        ),
        add=lambda obj: added.append(obj),
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    new_map_id = asyncio.run(
        duplicate_map_in_project(
            db=session,
            project_id=project_id,
            source_map_id=source_map_id,
            user_id=user_id,
            new_title="Carte Dupliquée",
            start_date=date(1509, 1, 1),
            end_date=date(1509, 1, 1),
        )
    )

    assert new_map_id is not None
    duplicated_feat = next(o for o in added if isinstance(o, Feature))
    inner = duplicated_feat.data["features"][0]
    assert inner["mapId"] == str(new_map_id)
    assert inner["properties"]["mapId"] == str(new_map_id)
    # Check that the dates adapted to the new map's period so elements are visible
    assert inner["properties"]["startYear"] == 1509
    assert inner["properties"]["endYear"] == 1509


def test_duplicate_map_adapts_relative_feature_years():
    """Features with internal/relative years within a period must scale proportionally."""
    from app.services.maps import duplicate_map_in_project
    from app.models.project import Project

    project_id = uuid4()
    user_id = uuid4()
    source_map_id = uuid4()

    project = Project(id=project_id, user_id=user_id, title="Test Project")
    source_map = Map(
        id=source_map_id,
        project_id=project_id,
        title="Source Map",
        start_date=date(1600, 1, 1),
        end_date=date(1700, 1, 1),
    )
    source_feature = Feature(
        id=uuid4(),
        project_id=project_id,
        map_id=source_map_id,
        data={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": str(uuid4()),
                    "properties": {
                        "name": "Bataille des Plaines",
                        "mapElementType": "point",
                        "mapId": str(source_map_id),
                        "startYear": 1620,
                        "endYear": 1650,
                    },
                }
            ],
        },
    )

    added = []
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: project),
                SimpleNamespace(scalar_one_or_none=lambda: source_map),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [source_feature])),
            ]
        ),
        add=lambda obj: added.append(obj),
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    # 1. Duplication to a shifted period of identical length (1800-1900)
    new_map_id = asyncio.run(
        duplicate_map_in_project(
            db=session,
            project_id=project_id,
            source_map_id=source_map_id,
            user_id=user_id,
            new_title="Carte Dupliquée Décalée",
            start_date=date(1800, 1, 1),
            end_date=date(1900, 1, 1),
        )
    )

    assert new_map_id is not None
    duplicated_feat = next(o for o in added if isinstance(o, Feature))
    inner = duplicated_feat.data["features"][0]
    assert inner["properties"]["startYear"] == 1820
    assert inner["properties"]["endYear"] == 1850

    # 2. Duplication to a scaled period of 50 years (1800-1850)
    added2 = []
    session2 = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(scalar_one_or_none=lambda: project),
                SimpleNamespace(scalar_one_or_none=lambda: source_map),
                SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [source_feature])),
            ]
        ),
        add=lambda obj: added2.append(obj),
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    new_map_id2 = asyncio.run(
        duplicate_map_in_project(
            db=session2,
            project_id=project_id,
            source_map_id=source_map_id,
            user_id=user_id,
            new_title="Carte Dupliquée Echelle",
            start_date=date(1800, 1, 1),
            end_date=date(1850, 1, 1),
        )
    )

    assert new_map_id2 is not None
    duplicated_feat2 = next(o for o in added2 if isinstance(o, Feature))
    inner2 = duplicated_feat2.data["features"][0]
    # Ratio 20% of 50 = 10 -> 1810; Ratio 50% of 50 = 25 -> 1825
    assert inner2["properties"]["startYear"] == 1810
    assert inner2["properties"]["endYear"] == 1825





