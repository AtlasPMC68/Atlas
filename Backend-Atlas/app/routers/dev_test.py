### ----------- IMPORTS ----------- ###
import json
import logging
import os

import numpy as np
import cv2

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from app.utils.auth import get_current_user_id
from ..tasks import (
    GEOREF_CONFIG,
    process_dev_test_extraction,
    warm_dev_test_text_regions,
)
from app.utils.dev_test import (
    delete_dev_test,
    delete_dev_test_case,
    find_test_image_path,
    list_dev_test_cases,
    list_dev_tests,
    load_case_config,
    parse_extraction_inputs,
    run_evaluate_case_blocking,
    slugify_test_case,
    upload_dev_test,
    write_test_config,
)
from app.utils.dev_test_derived import text_regions_if_cached
from app.utils.dev_test_pixel_zones import (
    CLASSIFIED_IMAGE_FILENAME, 
    OCR_BOX_COLOR,
    load_pixel_zones,
    pixel_zone_stats, 
    text_box_coverage,
    draw_pixel_zones,
)
from app.utils.dev_test_assets import GEOREF_ASSETS_DIR, ZONES_DIR
from app.utils.dev_test_cases import (
    VALID_KINDS,
    load_case_state,
    normalize_kind,
    resolve_case_kind,
)
from app.utils.georeferencing import (
    ControlPoint,
    fit_affine_from_control_points,
    frame_bounds_to_config_entry,
    parse_control_points_field,
    parse_frame_bounds,
)

from app.utils.georeferencing.projection import  (
    lonlat_to_webmercator,
)
from app.utils.georeferencing.config import describe_config, parse_config_overrides
from app.utils.georeferencing.diagnostics import (
    control_point_diagnostics,
    load_last_run_control_pixels,
    load_last_run_model,
    leave_one_out_models
)
from app.utils.georeferencing.records import RUN_RECORD_FILENAME
from app.utils.georeferencing.gcp_overlay import (
    draw_control_point_overlay,
    encode_png,
    side_by_side,
)
from app.utils.imposed_colors import (
    KIND_WATER,
    KIND_ZONE,
    imposed_colors_to_config_entries,
    parse_imposed_colors,
    split_imposed_colors_by_kind,
)
from app.utils.dev_test_evaluator import build_test_case_paths
from app.utils.legend import legend_to_entry, parse_legend_entry
### ----------- IMPORTS ----------- ###

router = APIRouter(prefix="/dev-test-api", tags=["Dev Test"])

logger = logging.getLogger(__name__)

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _safe_id(value: str, label: str = "id") -> str:
    """Slugify *value* and reject it if the result is empty."""
    slug = slugify_test_case(value)
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}: must contain at least one alphanumeric character",
        )
    return slug


@router.post("/upload")
async def upload_dev_test_map(
    test_id: str = Form(...),
    test_case: str = Form(...),
    control_points: str | None = Form(None),
    frame_bounds: str | None = Form(None),
    imposed_colors: str | None = Form(None),
    legend: str | None = Form(None),
    kind: str | None = Form(None),
    file: UploadFile = File(...),
    _user_id: str = Depends(get_current_user_id),
):
    """Upload a map image and start a dev-test extraction (file-only, no DB persistence)."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_test_case = _safe_id(test_case, "test_case")

    filename = (file.filename or "").lower()
    if not any(filename.endswith(ext) for ext in _ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )

    try:
        points = parse_control_points_field(control_points)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid control_points payload: {e}"
        )

    try:
        frame_bounds_dict = parse_frame_bounds(frame_bounds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid frame_bounds payload: {e}")

    # {"present": bool, "bounds": {...}}. Absent means the step was not answered,
    # which the case state reports; the route does not refuse it.
    try:
        legend_answered, legend_bounds = parse_legend_entry(
            json.loads(legend) if legend else None
        )
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid legend payload: {e}")

    # Pipette colors picked by the user; without them nothing is extracted at all,
    # so the georeferencing step would have no zones to transform.
    try:
        (
            all_click_positions,
            all_colors_names,
            all_sampling_radii,
            all_color_kinds,
        ) = parse_imposed_colors(imposed_colors)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid imposed_colors payload: {e}"
        )

    (
        imposed_click_positions,
        imposed_colors_names,
        imposed_sampling_radii,
    ) = split_imposed_colors_by_kind(
        all_click_positions, all_colors_names, all_sampling_radii, all_color_kinds, KIND_ZONE
    )
    (
        water_click_positions,
        water_colors_names,
        water_sampling_radii,
    ) = split_imposed_colors_by_kind(
        all_click_positions, all_colors_names, all_sampling_radii, all_color_kinds, KIND_WATER
    )

    if not imposed_click_positions:
        logger.warning(
            f"[DEV-TEST] No imposed colors provided for test_id={safe_test_id} "
            f"case={safe_test_case}; extraction will produce no zones"
        )

    file_content = await file.read()
    if len(file_content) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {_MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    if len(file_content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Persist anchor points immediately so the test case can be rerun from config
    # even if the async task fails. We do this synchronously before dispatching.
    write_test_config(
        parent_test_id=safe_test_id,
        test_case_id=safe_test_case,
        test_case_name=test_case,
        original_filename=file.filename,
        control_points=points,
        imposed_colors=imposed_colors_to_config_entries(
            all_click_positions,
            all_colors_names,
            all_sampling_radii,
            all_color_kinds,
        ),
        frame_bounds=frame_bounds_to_config_entry(frame_bounds_dict),
        # Only stored when this case overrides its map's kind, so the common
        # case carries no redundant flag.
        kind=normalize_kind(kind, default="") or None,
        legend=legend_to_entry(legend_bounds) if legend_answered else None,
    )

    try:
        task = process_dev_test_extraction.delay(
            filename=file.filename,
            file_content=file_content,
            test_id=safe_test_id,
            test_case=safe_test_case,
            control_points=[cp.to_dict() for cp in points],
            imposed_click_positions=imposed_click_positions,
            imposed_colors_names=imposed_colors_names,
            imposed_sampling_radii=imposed_sampling_radii,
            frame_bounds=frame_bounds_dict,
            water_click_positions=water_click_positions,
            water_colors_names=water_colors_names,
            water_sampling_radii=water_sampling_radii,
            legend_bounds=legend_bounds,
        )
        logger.info(
            f"[DEV-TEST] Started extraction task {task.id} for test_id={safe_test_id} case={safe_test_case}"
        )
        return {
            "task_id": task.id,
            "map_id": safe_test_id,
            "status": "processing_started",
        }
    except Exception as e:
        logger.error(f"[DEV-TEST] Error starting extraction: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to start dev-test processing"
        )


@router.put("/georef_zones/{map_id}")
async def save_dev_test_zones(
    map_id: str,
    payload: dict = Body(...),
    _user_id: str = Depends(get_current_user_id),
):
    """Save or overwrite the dev-test zones GeoJSON file for a given map."""
    safe_map_id = _safe_id(map_id, "map_id")

    os.makedirs(ZONES_DIR, exist_ok=True)
    zones_output_path = os.path.join(ZONES_DIR, f"{safe_map_id}_zones.geojson")

    with open(zones_output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "map_id": safe_map_id}


@router.get("/georef_zones/{map_id}")
async def get_dev_test_zones(
    map_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Return the current dev-test zones GeoJSON for a given map."""
    safe_map_id = _safe_id(map_id, "map_id")

    zones_path = os.path.join(ZONES_DIR, f"{safe_map_id}_zones.geojson")
    if not os.path.exists(zones_path):
        raise HTTPException(status_code=404, detail="Zones file not found")

    with open(zones_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


@router.get("/tests")
async def list_tests(_user_id: str = Depends(get_current_user_id)):
    """List available dev tests based on files in tests/assets/georef/maps."""

    return list_dev_tests()


@router.post("/tests/upload")
async def upload_test(
    file: UploadFile = File(...),
    name: str = Form(...),
    kind: str = Form("regression"),
    _user_id: str = Depends(get_current_user_id),
):
    """Create a dev test by saving the map image and metadata."""
    if kind not in VALID_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind: {kind}. Allowed: {', '.join(VALID_KINDS)}",
        )

    contents = await file.read()
    return upload_dev_test(
        file_bytes=contents,
        original_filename=file.filename,
        name=name,
        kind=kind,
    )


@router.post("/tests/{test_id}/warm-text-regions")
async def warm_text_regions(
    test_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Start OCR for a test map in the background if it is not cached yet."""
    safe_test_id = _safe_id(test_id, "test_id")
    if not GEOREF_CONFIG.enable_curve_alignment:
        return {"state": "disabled"}

    from app.utils.dev_test import find_test_image_path
    from app.utils.dev_test_derived import inspect_text_regions

    image_path = find_test_image_path(safe_test_id)
    if not image_path:
        raise HTTPException(status_code=404, detail="Test image not found")
    if inspect_text_regions(safe_test_id, image_path).usable:
        return {"state": "cached"}

    task = warm_dev_test_text_regions.delay(safe_test_id)
    return {"state": "started", "task_id": task.id}


@router.delete("/tests/{map_id}")
async def delete_test(
    map_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Delete a dev test: image file, zones GeoJSON, and metadata entry."""
    safe_map_id = _safe_id(map_id, "map_id")

    return delete_dev_test(safe_map_id)


@router.get("/test-cases/{test_id}")
async def list_test_cases(
    test_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """List available test cases for a given test (map) id."""
    safe_test_id = _safe_id(test_id, "test_id")

    return list_dev_test_cases(safe_test_id)


@router.delete("/test-cases/{test_id}/{test_case_id}")
async def delete_test_case(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Delete a single test case of a given test (map) id."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_test_case_id = _safe_id(test_case_id, "test_case_id")

    result = delete_dev_test_case(safe_test_id, safe_test_case_id)
    if result.get("status") == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"Test case not found: {safe_test_id}/{safe_test_case_id}",
        )

    logger.info(
        f"[DEV-TEST] Deleted test case {safe_test_id}/{safe_test_case_id}"
    )
    return result


@router.get("/georef-config")
async def get_georef_config(_user_id: str = Depends(get_current_user_id)):
    """The georeferencing config a re-run uses when nothing is overridden."""
    return describe_config(GEOREF_CONFIG)


def _last_run(test_id: str, test_case_id: str):
    """The transform this case's last run used, and the clicks it used it on."""
    paths = build_test_case_paths(GEOREF_ASSETS_DIR, test_id, test_case_id)
    record_path = os.path.join(paths.case_dir, RUN_RECORD_FILENAME)
    return (
        load_last_run_model(record_path),
        load_last_run_control_pixels(record_path),
    )


@router.get("/test-cases/{test_id}/{test_case_id}/control-points")
async def get_dev_test_control_points(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Per-control-point error for this case."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    try:
        config = load_case_config(GEOREF_ASSETS_DIR, safe_test_id, safe_case_id)
        image_path = find_test_image_path(safe_test_id)
        inputs = parse_extraction_inputs(config, image_path or "")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not inputs.pixel_points or not inputs.geo_points_lonlat:
        return {"points": [], "summary": {"count": 0, "looAvailable": False}}

    control_points = ControlPoint.from_pairs(
        inputs.pixel_points, inputs.geo_points_lonlat, source="sift"
    )
    model, pixels = _last_run(safe_test_id, safe_case_id)
    return control_point_diagnostics(
        control_points, inputs.frame_bounds, applied_model=model, applied_pixels=pixels
    )


@router.get("/test-cases/{test_id}/{test_case_id}/control-points.png")
async def get_dev_test_control_points_image(
    test_id: str,
    test_case_id: str,
    view: str = Query(
        "both",
        pattern="^(map|world|both)$",
        description=(
            "map: the points on the user's scan. world: the same points on the"
            " reference coastline, where the arrow shows where a click lands"
            " on the Earth. both: side by side."
        ),
    ),
    _user_id: str = Depends(get_current_user_id),
):
    """The control points drawn with an arrow per point."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    try:
        config = load_case_config(GEOREF_ASSETS_DIR, safe_test_id, safe_case_id)
        image_path = find_test_image_path(safe_test_id)
        inputs = parse_extraction_inputs(config, image_path or "")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not inputs.pixel_points or not inputs.geo_points_lonlat:
        raise HTTPException(status_code=404, detail="This case has no control points")

    image = cv2.imread(image_path) if image_path else None
    if image is None:
        raise HTTPException(status_code=404, detail="Test image could not be read")

    control_points = ControlPoint.from_pairs(
        inputs.pixel_points, inputs.geo_points_lonlat, source="sift"
    )
    model, applied_pixels = _last_run(safe_test_id, safe_case_id)
    if model is None:  # noqa: SIM108 - the two branches carry different captions
        # No run recorded yet: draw the GCP-only affine, and say so, rather
        # than refusing to show anything.
        model = fit_affine_from_control_points(control_points)
        caption = "aucun run enregistré - affine ajustée aux points"
    else:
        caption = f"dernier run : {model.name}"

    diagnostics = control_point_diagnostics(
        control_points,
        inputs.frame_bounds,
        applied_model=model,
        applied_pixels=applied_pixels,
    )
    errors = [p["appliedKm"] for p in diagnostics["points"]]

    suspects = diagnostics["summary"]["suspectIndices"]

    # A model that interpolates its own control points -- piecewise does, by
    # construction -- places every one of them exactly, so an arrow drawn from
    # it has zero length and tells the reader nothing. Fall back to the
    # leave-one-out placement, which is the honest arrow for any model.
    interpolates = all(
        (p["appliedKm"] or 0.0) < 1.0 for p in diagnostics["points"]
    )
    summary = diagnostics["summary"]
    if interpolates:
        # Its own RMS is 0 by construction, so reporting it would be worse
        # than saying nothing: the leave-one-out number is the real one.
        errors = [p["looKm"] for p in diagnostics["points"]]
        caption += f"   fleche = leave-one-out, RMS {summary.get('affineLooRmseKm')} km"
    elif summary.get("appliedRmseKm") is not None:
        used = summary.get("appliedPointCount") or len(control_points)
        caption += f"   RMS {summary['appliedRmseKm']} km sur {used} points"
    placed_pixels, placed_world = _placements(control_points, model, interpolates)

    overlay = None
    if view in ("map", "both"):
        overlay = draw_control_point_overlay(
            image,
            control_points,
            placed_pixels,
            errors_km=errors,
            suspect_indices=suspects,
            caption=caption,
        )

    if view in ("world", "both"):
        world = _world_panel(
            inputs.frame_bounds, control_points, placed_world, errors, suspects
        )
        if world is None and overlay is None:
            raise HTTPException(
                status_code=404,
                detail="This case has no framing box, so the world view cannot be drawn",
            )
        if world is not None:
            overlay = world if overlay is None else side_by_side(overlay, world)

    return Response(content=encode_png(overlay), media_type="image/png")


def _pixel_zones_context(test_id: str, test_case_id: str):
    """The last run's pixel-space zones, the map, its cached OCR and text-fill stats."""

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, test_id, test_case_id)
    features = load_pixel_zones(paths.case_dir)
    if features is None:
        raise HTTPException(
            status_code=404,
            detail="Aucune zone brute enregistrée pour ce cas : relancez-le.",
        )

    image_path = find_test_image_path(test_id)
    text_regions = None
    if image_path:
        try:
            text_regions = text_regions_if_cached(test_id, image_path)
        except Exception as e:
            logger.warning(f"[DEV-TEST] Could not read cached text regions: {e}")

    text_fill = None
    try:
        with open(
            os.path.join(paths.case_dir, RUN_RECORD_FILENAME), "r", encoding="utf-8"
        ) as f:
            text_fill = (json.load(f).get("errors") or {}).get("textFill")
    except (OSError, ValueError):
        pass

    return features, image_path, text_regions, text_fill


@router.get("/test-cases/{test_id}/{test_case_id}/pixel-zones")
async def get_dev_test_pixel_zones(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Per-zone hole statistics for the last run, before any transform."""

    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")
    features, _image_path, text_regions, text_fill = _pixel_zones_context(
        safe_test_id, safe_case_id
    )
    return {
        "zones": pixel_zone_stats(features, text_regions),
        "textCoverage": text_box_coverage(features, text_regions),
        "ocrBoxes": None if text_regions is None else len(text_regions),
        "textFill": text_fill,
    }


@router.get("/test-cases/{test_id}/{test_case_id}/pixel-zones.png")
async def get_dev_test_pixel_zones_image(
    test_id: str,
    test_case_id: str,
    background: str = Query("scan", pattern="^(scan|blank)$"),
    ocr: bool = Query(True, description="Draw the cached OCR boxes"),
    _user_id: str = Depends(get_current_user_id),
):
    """The last run's zones on the scan, as extracted: no transform, no clip."""

    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")
    features, image_path, text_regions, text_fill = _pixel_zones_context(
        safe_test_id, safe_case_id
    )

    image = cv2.imread(image_path) if image_path else None
    if image is None:
        raise HTTPException(status_code=404, detail="Test image could not be read")

    lines = [f"{len(features)} zone(s) brutes - trous en rouge"]
    if text_regions is None:
        lines.append("OCR absent du cache (lancez un run avec l'alignement)")
    elif ocr:
        lines.append(f"{len(text_regions)} boites OCR en magenta")
    if text_fill:
        lines.append(
            f"remplissage texte : {text_fill.get('pixelsFilled', 0)} px dans"
            f" {text_fill.get('boxesFilled', 0)}/{text_fill.get('boxesConsidered', 0)} boites"
        )
    else:
        lines.append("remplissage texte : non applique au dernier run")

    canvas = draw_pixel_zones(
        image,
        features,
        text_regions if ocr else None,
        blank_background=background == "blank",
        caption="\n".join(lines),
    )
    return Response(content=encode_png(canvas), media_type="image/png")


@router.get("/test-cases/{test_id}/{test_case_id}/classified-image.png")
async def get_dev_test_classified_image(
    test_id: str,
    test_case_id: str,
    ocr: bool = Query(True, description="Draw the cached OCR boxes"),
    _user_id: str = Depends(get_current_user_id),
):
    """The image the last run classified, labels erased by the inpaint step."""

    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")
    paths = build_test_case_paths(GEOREF_ASSETS_DIR, safe_test_id, safe_case_id)
    image = cv2.imread(os.path.join(paths.case_dir, CLASSIFIED_IMAGE_FILENAME))
    if image is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Aucune image nettoyée : le dernier run n'a pas utilisé"
                " text_fill_method = inpaint."
            ),
        )

    if ocr:
        image_path = find_test_image_path(safe_test_id)
        regions = text_regions_if_cached(safe_test_id, image_path) if image_path else None
        for region in regions or []:
            try:
                pts = np.round(np.asarray(region, dtype=np.float64)).astype(np.int32)
            except (TypeError, ValueError):
                continue
            if len(pts) >= 3:
                cv2.polylines(image, [pts], True, OCR_BOX_COLOR, 1, cv2.LINE_AA)

    return Response(content=encode_png(image), media_type="image/png")


def _placements(control_points, model, leave_one_out: bool):
    """Where each control point ends up, in both spaces."""

    per_point = (
        leave_one_out_models(control_points)
        if leave_one_out
        else [model] * len(control_points)
    )

    placed_pixels: list = []
    placed_world: list = []
    for cp, point_model in zip(control_points, per_point):
        if point_model is None:
            placed_pixels.append(None)
            placed_world.append(None)
            continue
        east, north = lonlat_to_webmercator(cp.geo[0], cp.geo[1])
        try:
            inverse = point_model.inverse()
            px, py = inverse(np.array([east]), np.array([north]))
            placed_pixels.append((float(px[0]), float(py[0])))
        except Exception:
            placed_pixels.append(None)
        try:
            wx, wy = point_model(
                np.array([cp.pixel[0]]), np.array([cp.pixel[1]])
            )
            placed_world.append((float(wx[0]), float(wy[0])))
        except Exception:
            placed_world.append(None)
    return placed_pixels, placed_world


def _world_panel(frame_bounds, control_points, placed_world, errors_km, suspects):
    
    if not frame_bounds:
        return None
    try:
        from app.utils.georeferencing.gcp_overlay import draw_world_overlay
        from app.utils.georeferencing.reference import build_reference_layers

        layers = build_reference_layers(frame_bounds)
        return draw_world_overlay(
            layers,
            control_points,
            placed_world,
            errors_km=errors_km,
            suspect_indices=suspects,
            caption="cadre de reference",
        )
    except Exception as e:
        logger.warning(f"[DEV-TEST] Could not draw the world-side overlay: {e}")
        return None


@router.post("/test-cases/{test_id}/{test_case_id}/run-evaluate")
async def run_evaluate_dev_test_case(
    test_id: str,
    test_case_id: str,
    min_iou: float | None = Query(
        None, description="Optional minimum IoU to mark pass/fail"
    ),
    snap_to_coastline: bool | None = Query(
        None,
        description=(
            "Blind coastline snapping. Turn it OFF is you want to get true result."
            "of the georef algorithm since the snapping helps after the fact"
        ),
    ),
    enable_curve_alignment: bool | None = Query(
        None, description="Step 4 chamfer + ICP alignment"
    ),
    clip_to_land_mask: bool | None = Query(
        None, description="Drop zone area falling in the ocean"
    ),
    exclude_gcp: list[int] = Query(
        default=[],
        description=(
            "Control-point indices to leave out of this run, for a hand-driven"
            " leave-one-out. The case's stored clicks are not modified."
        ),
    ),
    config_overrides: dict | None = Body(
        None,
        description=(
            "Any GeorefConfig field, for this run only -- the tuning panel."
            " See GET /georef-config for the fields and their current values."
            " The query switches above win over the same key here."
        ),
    ),
    _user_id: str = Depends(get_current_user_id),
):

    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    # Validated here as well as in the task so a mistyped value is a 400 on
    # the request, not a failure buried in the worker's log.
    try:
        overrides = parse_config_overrides(config_overrides)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    overrides.update(
        {
            key: value
            for key, value in (
                ("snap_to_coastline", snap_to_coastline),
                ("enable_curve_alignment", enable_curve_alignment),
                ("clip_to_land_mask", clip_to_land_mask),
            )
            if value is not None
        }
    )

    try:
        return await run_evaluate_case_blocking(
            test_id=safe_test_id,
            test_case_id=safe_case_id,
            min_iou=min_iou,
            assets_root=GEOREF_ASSETS_DIR,
            config_overrides=overrides or None,
            excluded_control_points=exclude_gcp,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-cases/{test_id}/{test_case_id}/report")
async def get_dev_test_case_report(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Get the latest persisted evaluation report for a test case."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, safe_test_id, safe_case_id)
    report_path = paths.report_path
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-cases/{test_id}/{test_case_id}/state")
async def get_dev_test_case_state(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    state = load_case_state(safe_test_id, safe_case_id)
    if state is not None:
        return state

    return {
        "testId": safe_test_id,
        "testCaseId": safe_case_id,
        "kind": resolve_case_kind(safe_test_id, safe_case_id),
        "scored": None,
        "requirements": None,
        "derived": [],
    }


@router.get("/test-cases/{test_id}/{test_case_id}/best-report")
async def get_dev_test_case_best_report(
    test_id: str,
    test_case_id: str,
    _user_id: str = Depends(get_current_user_id),
):
    """Get the best persisted evaluation report for a test case."""
    safe_test_id = _safe_id(test_id, "test_id")
    safe_case_id = _safe_id(test_case_id, "test_case_id")

    paths = build_test_case_paths(GEOREF_ASSETS_DIR, safe_test_id, safe_case_id)
    report_path = paths.best_report_path
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Best report not found")

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
