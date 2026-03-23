import os
import json
import shutil
import asyncio
import time
from uuid import uuid4
from datetime import datetime

from fastapi import FastAPI, Body, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import celery_router
from .routers import auth
from .routers import maps
from .routers import user

from .celery_app import celery_app

app = FastAPI(
    title="Maps Processing API",
    description="API pour traitement et analyse de cartes historiques",
    version="0.1.0",
)
app.include_router(celery_router.router)
app.include_router(maps.router)
app.include_router(auth.router)
app.include_router(user.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve test assets (images, GeoJSON, etc.) as static files under /dev-test
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
TEST_ASSETS_DIR = os.path.join(ROOT_DIR, "tests", "assets")
ZONES_DIR = os.path.join(TEST_ASSETS_DIR, "georef_zones")
MAPS_DIR = os.path.join(TEST_ASSETS_DIR, "maps")
TEST_CASES_DIR = os.path.join(TEST_ASSETS_DIR, "test_cases")
TESTS_METADATA_PATH = os.path.join(TEST_ASSETS_DIR, "tests_metadata.json")


def _find_test_image_path(test_id: str) -> str | None:
    if not os.path.isdir(MAPS_DIR):
        return None

    for filename in os.listdir(MAPS_DIR):
        stem, _ext = os.path.splitext(filename)
        if stem == test_id:
            return os.path.join(MAPS_DIR, filename)

    return None


def _evaluate_and_persist_case(
    test_id: str,
    test_case_id: str,
    *,
    min_iou: float | None,
) -> dict:
    from app.utils.dev_test_evaluator import (
        build_test_case_paths,
        compute_errors_geojson,
        evaluate_georef_test_case,
        evaluate_georef_zones_from_paths,
        write_geojson,
        write_report,
    )

    paths = build_test_case_paths(TEST_ASSETS_DIR, test_id, test_case_id)

    report, errors_geojson = evaluate_georef_test_case(
        TEST_ASSETS_DIR,
        test_id,
        test_case_id,
        min_iou=min_iou,
    )

    # Persist error overlay (false positive/negative areas) as a dedicated GeoJSON file.
    write_geojson(errors_geojson, paths.errors_geojson_path)

    # Keep a best-so-far snapshot (zones + report) alongside the latest.
    best_report_path = paths.best_report_path
    best_zones_path = paths.best_zones_path
    best_errors_path = paths.best_errors_geojson_path

    latest_score = None
    try:
        metrics = report.get("metrics") or {}
        latest_score = float(
            metrics.get("scoreUsed")
            or ((metrics.get("expectedBest") or {}).get("meanIou"))
            or metrics.get("primaryExpectedBestIou")
        )
    except Exception:
        latest_score = None

    def _read_best_score() -> float | None:
        if not os.path.exists(best_report_path):
            return None
        try:
            with open(best_report_path, "r", encoding="utf-8") as f:
                best = json.load(f)
            metrics = best.get("metrics") or {}
            return float(
                metrics.get("scoreUsed")
                or ((metrics.get("expectedBest") or {}).get("meanIou"))
                or metrics.get("primaryExpectedBestIou")
            )
        except Exception:
            return None

    best_score = _read_best_score()
    best_updated = False
    if latest_score is not None and (best_score is None or latest_score > best_score):
        try:
            if os.path.exists(paths.extracted_zones_path):
                shutil.copyfile(paths.extracted_zones_path, best_zones_path)
            if os.path.exists(paths.errors_geojson_path):
                shutil.copyfile(paths.errors_geojson_path, best_errors_path)
            with open(best_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            best_updated = True
        except Exception:
            best_updated = False

    def _best_report_needs_upgrade() -> bool:
        if not os.path.exists(best_report_path):
            return True
        try:
            with open(best_report_path, "r", encoding="utf-8") as f:
                best = json.load(f)
        except Exception:
            return True

        metrics = best.get("metrics") if isinstance(best, dict) else None
        if not isinstance(metrics, dict):
            return True

        expected_best = metrics.get("expectedBest")
        if not isinstance(expected_best, dict):
            return True
        for k in (
            "meanIou",
            "meanPrecision",
            "meanRecall",
            "totalFalseNegativeArea",
            "totalFalsePositiveArea",
        ):
            if k not in expected_best:
                return True

        primary_match = metrics.get("primaryMatch")
        if not isinstance(primary_match, dict):
            return True
        for k in ("precision", "recall", "falseNegativeArea", "falsePositiveArea"):
            if k not in primary_match:
                return True

        matches = best.get("matches") if isinstance(best, dict) else None
        if isinstance(matches, list) and matches:
            bm = (
                (matches[0] or {}).get("bestMatch")
                if isinstance(matches[0], dict)
                else None
            )
            if not isinstance(bm, dict):
                return True
            for k in ("precision", "recall", "falseNegativeArea", "falsePositiveArea"):
                if k not in bm:
                    return True

        return False

    # Backfill/upgrade: if best zones exist but best report is missing or in an older
    # schema (missing precision/recall etc.), recompute the best report from best zones.
    if os.path.exists(best_zones_path) and _best_report_needs_upgrade():
        try:
            best_report, best_errors_geojson = evaluate_georef_zones_from_paths(
                test_id=test_id,
                test_case_id=test_case_id,
                expected_zones_path=paths.expected_zones_path,
                extracted_zones_path=best_zones_path,
                config_path=paths.config_path
                if os.path.exists(paths.config_path)
                else None,
                report_path=best_report_path,
                errors_geojson_path=best_errors_path,
                min_iou=min_iou,
            )
            with open(best_report_path, "w", encoding="utf-8") as f:
                json.dump(best_report, f, indent=2, ensure_ascii=False)
            write_geojson(best_errors_geojson, best_errors_path)
        except Exception:
            pass

    # Backfill: if best report/zones exist but best errors are missing (e.g. created
    # before we started snapshotting errors), compute best errors from best zones.
    if (
        os.path.exists(best_report_path)
        and os.path.exists(best_zones_path)
        and not os.path.exists(best_errors_path)
    ):
        try:
            best_errors_geojson = compute_errors_geojson(
                expected_zones_path=paths.expected_zones_path,
                extracted_zones_path=best_zones_path,
            )
            write_geojson(best_errors_geojson, best_errors_path)
        except Exception:
            pass

    report.setdefault("artifacts", {})
    report["artifacts"].update(
        {
            "latestZones": paths.extracted_zones_path,
            "latestErrors": paths.errors_geojson_path,
            "latestReport": paths.report_path,
            "bestZones": best_zones_path if os.path.exists(best_zones_path) else None,
            "bestErrors": best_errors_path
            if os.path.exists(best_errors_path)
            else None,
            "bestReport": best_report_path
            if os.path.exists(best_report_path)
            else None,
            "bestUpdated": best_updated,
        }
    )

    # Persist the final enriched report.
    write_report(report, paths.report_path)

    return report


if os.path.isdir(TEST_ASSETS_DIR):
    app.mount("/dev-test", StaticFiles(directory=TEST_ASSETS_DIR), name="dev-test")


@app.put("/dev-test-api/georef_zones/{map_id}")
async def save_dev_test_zones(map_id: str, payload: dict = Body(...)):
    """Save or overwrite the dev-test zones GeoJSON file for a given map.

    This is used only by the internal test editor UI.
    """

    os.makedirs(ZONES_DIR, exist_ok=True)
    zones_output_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")

    with open(zones_output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "map_id": map_id}


@app.get("/dev-test-api/georef_zones/{map_id}")
async def get_dev_test_zones(map_id: str):
    """Return the current dev-test zones GeoJSON for a given map.

    This mirrors the static file under /dev-test/georef_zones but avoids any
    browser caching issues by serving it via the API layer.
    """

    zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
    if not os.path.exists(zones_path):
        raise HTTPException(status_code=404, detail="Zones file not found")

    with open(zones_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


@app.get("/dev-test-api/tests")
async def list_dev_tests():
    """List available dev tests based on files in tests/assets/maps.

    Each test corresponds to an image file whose stem is the map_id.
    If metadata exists in tests_metadata.json, use it to enrich the response.
    """

    if not os.path.isdir(MAPS_DIR):
        return []

    # Load optional metadata file
    metadata: dict[str, dict] = {}
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                if isinstance(meta_data, dict):
                    metadata = meta_data
        except Exception:
            # Ignore corrupted metadata in dev-only context
            metadata = {}

    tests = []
    for filename in os.listdir(MAPS_DIR):
        # Basic filter for image files
        if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            continue

        map_id, _ext = os.path.splitext(filename)
        meta_entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}

        zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
        has_zones = os.path.exists(zones_path)

        tests.append(
            {
                "mapId": map_id,
                "name": meta_entry.get("name") or map_id,
                "imageFilename": filename,
                "hasZones": has_zones,
                "createdAt": meta_entry.get("createdAt"),
            }
        )

    # Sort by creation time if available, otherwise by filename
    tests.sort(key=lambda t: (t.get("createdAt") or "", t["imageFilename"]))
    return tests


@app.post("/dev-test-api/tests")
async def register_dev_test(payload: dict = Body(...)):
    """Register or update metadata for a dev test.

    Expects a JSON body with at least {"mapId": str, "name": str}.
    """

    map_id = payload.get("mapId")
    name = payload.get("name")
    if not map_id or not isinstance(map_id, str):
        raise HTTPException(status_code=400, detail="mapId is required")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="name is required")

    # Load existing metadata
    metadata: dict[str, dict] = {}
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                if isinstance(meta_data, dict):
                    metadata = meta_data
        except Exception:
            metadata = {}

    entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}
    entry["name"] = name
    entry.setdefault("createdAt", datetime.utcnow().isoformat() + "Z")
    metadata[map_id] = entry

    os.makedirs(os.path.dirname(TESTS_METADATA_PATH), exist_ok=True)
    with open(TESTS_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "mapId": map_id, "name": name}


@app.post("/dev-test-api/tests/upload")
async def upload_dev_test(
    file: UploadFile = File(...),
    name: str = Form(...),
):
    """Create a dev test by saving the map image and metadata.

    - Saves the uploaded image into tests/assets/maps.
    - Generates a mapId (UUID).
    - Registers the test name in tests_metadata.json.
    """

    os.makedirs(MAPS_DIR, exist_ok=True)

    original_filename = file.filename or "map"
    _base, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ".jpg"

    map_id = str(uuid4())
    image_filename = f"{map_id}{ext}"
    dest_path = os.path.join(MAPS_DIR, image_filename)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    # Update metadata (reuse same format as register_dev_test)
    metadata: dict[str, dict] = {}
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                if isinstance(meta_data, dict):
                    metadata = meta_data
        except Exception:
            metadata = {}

    entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}
    entry["name"] = name
    entry.setdefault("createdAt", datetime.utcnow().isoformat() + "Z")
    metadata[map_id] = entry

    os.makedirs(os.path.dirname(TESTS_METADATA_PATH), exist_ok=True)
    with open(TESTS_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return {
        "status": "ok",
        "mapId": map_id,
        "name": name,
        "imageFilename": image_filename,
    }


@app.delete("/dev-test-api/tests/{map_id}")
async def delete_dev_test(map_id: str):
    """Delete a dev test: image file, zones GeoJSON, and metadata entry.

    This is a best-effort operation for the internal test browser.
    """

    # Delete image file matching the map_id stem
    if os.path.isdir(MAPS_DIR):
        for filename in os.listdir(MAPS_DIR):
            stem, _ext = os.path.splitext(filename)
            if stem == map_id:
                try:
                    os.remove(os.path.join(MAPS_DIR, filename))
                except OSError:
                    pass
                break

    # Delete zones file if it exists
    zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
    if os.path.exists(zones_path):
        try:
            os.remove(zones_path)
        except OSError:
            pass

    # Delete test cases directory if it exists
    cases_dir = os.path.join(TEST_CASES_DIR, map_id)
    if os.path.isdir(cases_dir):
        try:
            shutil.rmtree(cases_dir)
        except OSError:
            pass

    # Remove metadata entry
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                metadata: dict[str, dict] = (
                    meta_data if isinstance(meta_data, dict) else {}
                )
        except Exception:
            metadata = {}

        if map_id in metadata:
            del metadata[map_id]
            try:
                with open(TESTS_METADATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    return {"status": "ok", "mapId": map_id}


@app.get("/dev-test-api/test-cases/{test_id}")
async def list_dev_test_cases(test_id: str):
    """List available test cases for a given test (map) id.

    A test case exists if we have a case directory under:
    tests/assets/test_cases/<test_id>/<test_case_id>/
    (backward compatible with legacy flat files).
    """

    case_dir = os.path.join(TEST_CASES_DIR, test_id)
    if not os.path.isdir(case_dir):
        return []

    cases: set[str] = set()

    # New layout: directories
    for name in os.listdir(case_dir):
        p = os.path.join(case_dir, name)
        if os.path.isdir(p):
            cases.add(name)

    # Legacy layout: flat files (keep listing them until fully migrated)
    for fn in os.listdir(case_dir):
        if fn.endswith("_config.json"):
            cases.add(fn[: -len("_config.json")])
        elif fn.endswith("_zones.geojson"):
            cases.add(fn[: -len("_zones.geojson")])

    return sorted(cases)


@app.post("/dev-test-api/test-cases/{test_id}/{test_case_id}/run")
async def run_dev_test_case(test_id: str, test_case_id: str):
    """Rerun extraction for a saved dev-test case using its anchor config.

    This endpoint is the missing link between a persisted test case config
    (anchor points + options) and evaluation:

    - Reads config: tests/assets/test_cases/<test_id>/<test_case_id>/config.json
    - Reads image:  tests/assets/maps/<test_id>.(png|jpg|jpeg)
    - Starts celery task which overwrites the latest extracted zones:
        tests/assets/test_cases/<test_id>/<test_case_id>/zones.geojson
    """

    if not os.path.isdir(TEST_ASSETS_DIR):
        raise HTTPException(status_code=500, detail="Test assets directory missing")

    from app.utils.dev_test_evaluator import build_test_case_paths

    paths = build_test_case_paths(TEST_ASSETS_DIR, test_id, test_case_id)
    config_path = paths.config_path
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail=f"Config not found: {config_path}")

    image_path = _find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Test image not found for test_id={test_id} under {MAPS_DIR}",
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {e}")

    georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}
    options = config.get("options") if isinstance(config.get("options"), dict) else {}

    enable_georeferencing = bool(options.get("enableGeoreferencing", True))
    enable_color_extraction = bool(options.get("enableColorExtraction", True))
    enable_shapes_extraction = bool(options.get("enableShapesExtraction", False))
    enable_text_extraction = bool(options.get("enableTextExtraction", False))

    pixel_points_list = None
    geo_points_list = None

    if enable_georeferencing:
        img_pts = georef.get("imagePoints")
        world_pts = georef.get("worldPoints")
        if (
            isinstance(img_pts, list)
            and isinstance(world_pts, list)
            and len(img_pts) == len(world_pts)
        ):
            try:
                pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
                geo_points_list = [
                    (float(p["lng"]), float(p["lat"])) for p in world_pts
                ]
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid georef points in config: {e}",
                )

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read test image: {e}")

    # Use original filename when present (helps preserve extension), otherwise use the on-disk name.
    filename = config.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = os.path.basename(image_path)

    try:
        from app.tasks import process_map_extraction

        task = process_map_extraction.delay(
            filename,
            file_content,
            test_id,
            pixel_points_list,
            geo_points_list,
            enable_color_extraction,
            enable_shapes_extraction,
            enable_text_extraction,
            True,
            test_case_id,
        )
        return {
            "status": "processing_started",
            "task_id": task.id,
            "map_id": test_id,
            "test_id": test_id,
            "test_case_id": test_case_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start extraction: {e}")


@app.post("/dev-test-api/test-cases/{test_id}/{test_case_id}/evaluate")
async def evaluate_dev_test_case(
    test_id: str,
    test_case_id: str,
    min_iou: float | None = Query(
        None, description="Optional minimum IoU to mark pass/fail"
    ),
):
    """Evaluate one dev test case and persist a report JSON.

    Compares:
    - expected: tests/assets/georef_zones/<test_id>_zones.geojson
    - extracted: tests/assets/test_cases/<test_id>/<test_case_id>/zones.geojson
    Writes:
    - report: tests/assets/test_cases/<test_id>/<test_case_id>/report.json

        Scoring:
        - Uses per-expected best-match metrics and aggregates them (mean IoU/precision/
          recall). A union-vs-union metric is included only for debugging.
    """

    if not os.path.isdir(TEST_ASSETS_DIR):
        raise HTTPException(status_code=500, detail="Test assets directory missing")

    try:
        return _evaluate_and_persist_case(test_id, test_case_id, min_iou=min_iou)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dev-test-api/test-cases/{test_id}/{test_case_id}/run-evaluate")
async def run_evaluate_dev_test_case(
    test_id: str,
    test_case_id: str,
    min_iou: float | None = Query(
        None, description="Optional minimum IoU to mark pass/fail"
    ),
    timeout_s: float = Query(
        300.0,
        ge=1.0,
        le=3600.0,
        description="Max seconds to wait for the extraction task before returning 202",
    ),
    poll_interval_s: float = Query(
        1.0,
        ge=0.1,
        le=10.0,
        description="Polling interval while waiting for the extraction task",
    ),
):
    """Run extraction from saved anchors *and then* evaluate.

    This ensures the evaluation always targets the current algorithm output.

    Behavior:
    - Starts Celery extraction (same as /run)
    - Waits up to timeout_s
    - If finished: evaluates and returns report
    - If not finished: returns 202 with task_id (caller can poll /maps/status)
    """

    from fastapi.responses import JSONResponse

    if not os.path.isdir(TEST_ASSETS_DIR):
        raise HTTPException(status_code=500, detail="Test assets directory missing")

    from app.utils.dev_test_evaluator import build_test_case_paths

    paths = build_test_case_paths(TEST_ASSETS_DIR, test_id, test_case_id)
    config_path = paths.config_path
    if not os.path.exists(config_path):
        raise HTTPException(status_code=404, detail=f"Config not found: {config_path}")

    image_path = _find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Test image not found for test_id={test_id} under {MAPS_DIR}",
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {e}")

    georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}
    options = config.get("options") if isinstance(config.get("options"), dict) else {}

    enable_georeferencing = bool(options.get("enableGeoreferencing", True))
    enable_color_extraction = bool(options.get("enableColorExtraction", True))
    enable_shapes_extraction = bool(options.get("enableShapesExtraction", False))
    enable_text_extraction = bool(options.get("enableTextExtraction", False))

    pixel_points_list = None
    geo_points_list = None

    if enable_georeferencing:
        img_pts = georef.get("imagePoints")
        world_pts = georef.get("worldPoints")
        if (
            isinstance(img_pts, list)
            and isinstance(world_pts, list)
            and len(img_pts) == len(world_pts)
        ):
            try:
                pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
                geo_points_list = [
                    (float(p["lng"]), float(p["lat"])) for p in world_pts
                ]
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid georef points in config: {e}"
                )

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read test image: {e}")

    filename = config.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = os.path.basename(image_path)

    try:
        from app.tasks import process_map_extraction

        task = process_map_extraction.delay(
            filename,
            file_content,
            test_id,
            pixel_points_list,
            geo_points_list,
            enable_color_extraction,
            enable_shapes_extraction,
            enable_text_extraction,
            True,
            test_case_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start extraction: {e}")

    async_result = celery_app.AsyncResult(task.id)
    deadline = time.monotonic() + float(timeout_s)
    while not async_result.ready():
        if time.monotonic() >= deadline:
            return JSONResponse(
                status_code=202,
                content={
                    "status": "processing_started",
                    "task_id": task.id,
                    "test_id": test_id,
                    "test_case_id": test_case_id,
                    "message": "Extraction still running; poll /maps/status/{task_id} then call /evaluate",
                },
            )
        await asyncio.sleep(float(poll_interval_s))

    if async_result.state != "SUCCESS":
        raise HTTPException(
            status_code=500,
            detail=f"Extraction task ended in state {async_result.state}: {async_result.info}",
        )

    # Extraction finished (SUCCESS or other terminal state). Evaluate latest zones.
    try:
        report = _evaluate_and_persist_case(test_id, test_case_id, min_iou=min_iou)
        return {
            "status": "ok",
            "task_id": task.id,
            "task_state": async_result.state,
            "report": report,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dev-test-api/test-cases/{test_id}/{test_case_id}/report")
async def get_dev_test_case_report(test_id: str, test_case_id: str):
    """Get the latest persisted evaluation report for a test case."""

    from app.utils.dev_test_evaluator import build_test_case_paths

    paths = build_test_case_paths(TEST_ASSETS_DIR, test_id, test_case_id)
    report_path = paths.report_path
    if not os.path.exists(report_path):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def read_root():
    return {"message": "Maps Processing API", "status": "running"}


@app.get("/ping")
def ping():
    return {"message": "pong"}
