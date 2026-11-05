"""The legend helpers and the import inputs: validation, merging, readiness."""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

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

    assert response == {"detail": "Features updated successfully"}
    assert len(added_features) == 1
    assert added_features[0].map_id == target_map_id



