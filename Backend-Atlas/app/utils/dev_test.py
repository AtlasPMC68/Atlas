import json
import os
import re
import shutil
from typing import Any
from uuid import uuid4
from datetime import datetime
from asyncio import to_thread

from app.celery_app import celery_app

from app.utils.dev_test_assets import (
    MAPS_DIR,
    TESTS_METADATA_PATH,
    TEST_CASES_DIR,
    ZONES_DIR,
)


def write_test_config(
    parent_test_id: str,
    test_case_id: str,
    test_case_name: str | None,
    original_filename: str | None,
    img_pts: list | None,
    world_pts: list | None,
) -> None:
    # tests/assets/georef/test_cases/<test_id>/<test_case_id>/config.json
    case_dir = os.path.join(TEST_CASES_DIR, parent_test_id, test_case_id)
    os.makedirs(case_dir, exist_ok=True)

    config_path = os.path.join(case_dir, "config.json")
    config_payload = {
        "testId": parent_test_id,
        "testCase": test_case_name or test_case_id,
        "testCaseId": test_case_id,
        "updatedAt": datetime.utcnow().isoformat() + "Z",
        "filename": original_filename,
        "georef": {
            "imagePoints": img_pts,
            "worldPoints": world_pts,
        },
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_payload, f, indent=2, ensure_ascii=False)


def slugify_test_case(value: str) -> str:
    # Keep this conservative: only allow simple filename-safe tokens.
    slug = value.strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9_-]", "", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-_")
    return slug[:80]


def find_test_image_path(test_id: str) -> str | None:
    if not os.path.isdir(MAPS_DIR):
        return None

    for filename in os.listdir(MAPS_DIR):
        stem, _ext = os.path.splitext(filename)
        if stem == test_id:
            return os.path.join(MAPS_DIR, filename)

    return None


def _load_tests_metadata() -> dict[str, dict[str, Any]]:
    if not os.path.exists(TESTS_METADATA_PATH):
        return {}
    try:
        with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_tests_metadata(metadata: dict[str, dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(TESTS_METADATA_PATH), exist_ok=True)
    with open(TESTS_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def list_dev_tests() -> list[dict[str, Any]]:
    if not os.path.isdir(MAPS_DIR):
        return []

    metadata = _load_tests_metadata()

    tests: list[dict[str, Any]] = []
    for filename in os.listdir(MAPS_DIR):
        if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            continue

        map_id = os.path.splitext(filename)[0]
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

    tests.sort(key=lambda t: (t.get("createdAt") or "", t["imageFilename"]))
    return tests


def upload_dev_test(
    *, file_bytes: bytes, original_filename: str | None, name: str
) -> dict[str, Any]:
    os.makedirs(MAPS_DIR, exist_ok=True)

    original_filename = original_filename or "map"
    _base, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ".jpg"

    map_id = str(uuid4())
    image_filename = f"{map_id}{ext}"
    dest_path = os.path.join(MAPS_DIR, image_filename)

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    metadata = _load_tests_metadata()
    entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}
    entry["name"] = name
    entry.setdefault("createdAt", datetime.utcnow().isoformat() + "Z")
    metadata[map_id] = entry
    _write_tests_metadata(metadata)

    return {
        "status": "ok",
        "mapId": map_id,
        "name": name,
        "imageFilename": image_filename,
    }


def delete_dev_test(map_id: str) -> dict[str, Any]:
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

    zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
    if os.path.exists(zones_path):
        try:
            os.remove(zones_path)
        except OSError:
            pass

    cases_dir = os.path.join(TEST_CASES_DIR, map_id)
    if os.path.isdir(cases_dir):
        try:
            shutil.rmtree(cases_dir)
        except OSError:
            pass

    metadata = _load_tests_metadata()
    if map_id in metadata:
        del metadata[map_id]
        try:
            _write_tests_metadata(metadata)
        except Exception:
            pass

    return {"status": "ok", "mapId": map_id}


def list_dev_test_cases(test_id: str) -> list[str]:
    case_dir = os.path.join(TEST_CASES_DIR, test_id)
    if not os.path.isdir(case_dir):
        return []

    cases: set[str] = set()
    for name in os.listdir(case_dir):
        p = os.path.join(case_dir, name)
        if os.path.isdir(p):
            cases.add(name)

    return sorted(cases)


def evaluate_and_persist_case(
    *, assets_root: str, test_id: str, test_case_id: str, min_iou: float | None
) -> dict[str, Any]:
    from app.utils.dev_test_evaluator import (
        build_test_case_paths,
        evaluate_georef_test_case,
        write_geojson,
        write_report,
    )

    paths = build_test_case_paths(assets_root, test_id, test_case_id)

    report, errors_geojson = evaluate_georef_test_case(
        assets_root,
        test_id,
        test_case_id,
        min_iou=min_iou,
    )

    write_geojson(errors_geojson, paths.errors_geojson_path)

    best_report_path = paths.best_report_path
    best_zones_path = paths.best_zones_path
    best_errors_path = paths.best_errors_geojson_path

    latest_score: float | None
    try:
        metrics = report.get("metrics") or {}
        latest_score = float(
            metrics.get("scoreUsed") or ((metrics.get("mean") or {}).get("meanIou"))
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
                metrics.get("scoreUsed") or ((metrics.get("mean") or {}).get("meanIou"))
            )
        except Exception:
            return None

    best_score = _read_best_score()
    if latest_score is not None and (best_score is None or latest_score > best_score):
        try:
            if os.path.exists(paths.extracted_zones_path):
                shutil.copyfile(paths.extracted_zones_path, best_zones_path)
            if os.path.exists(paths.errors_geojson_path):
                shutil.copyfile(paths.errors_geojson_path, best_errors_path)
            with open(best_report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    write_report(report, paths.report_path)
    return report


def _load_case_config(
    assets_root: str, test_id: str, test_case_id: str
) -> dict[str, Any]:
    from app.utils.dev_test_evaluator import build_test_case_paths

    paths = build_test_case_paths(assets_root, test_id, test_case_id)
    if not os.path.exists(paths.config_path):
        raise FileNotFoundError(f"Config not found: {paths.config_path}")

    try:
        with open(paths.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        raise ValueError(f"Invalid config JSON: {e}")

    if not isinstance(config, dict):
        raise ValueError("Invalid config JSON: expected object")
    return config


def _parse_extraction_inputs(
    config: dict[str, Any], image_path: str
) -> tuple[
    str,
    list[tuple[float, float]] | None,
    list[tuple[float, float]] | None,
]:
    georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}

    pixel_points_list = None
    geo_points_list = None
    img_pts = georef.get("imagePoints")
    world_pts = georef.get("worldPoints")
    if (
        isinstance(img_pts, list)
        and isinstance(world_pts, list)
        and len(img_pts) == len(world_pts)
    ):
        try:
            pixel_points_list = [(float(p["x"]), float(p["y"])) for p in img_pts]
            geo_points_list = [(float(p["lng"]), float(p["lat"])) for p in world_pts]
        except Exception as e:
            raise ValueError(f"Invalid georef points in config: {e}")

    filename = config.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = os.path.basename(image_path)

    return (
        filename,
        pixel_points_list,
        geo_points_list,
    )


def build_extraction_task_args_for_case(
    *, assets_root: str, test_id: str, test_case_id: str
) -> list[Any]:
    """Build positional args for process_dev_test_extraction.apply(args=...)."""

    config = _load_case_config(assets_root, test_id, test_case_id)
    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Test image not found for test_id={test_id} under {MAPS_DIR}"
        )

    (
        filename,
        pixel_points_list,
        geo_points_list,
    ) = _parse_extraction_inputs(config, image_path)

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to read test image: {e}")

    return [
        filename,
        file_content,
        test_id,
        test_case_id,
        pixel_points_list,
        geo_points_list,
    ]


def _start_extraction_for_case(
    *, assets_root: str, test_id: str, test_case_id: str
) -> str:
    args = build_extraction_task_args_for_case(
        assets_root=assets_root,
        test_id=test_id,
        test_case_id=test_case_id,
    )

    from app.tasks import process_dev_test_extraction

    task = process_dev_test_extraction.delay(*args)
    return task.id


async def run_evaluate_case_blocking(
    *,
    test_id: str,
    test_case_id: str,
    min_iou: float | None,
    assets_root: str,
) -> dict[str, Any]:
    task_id = _start_extraction_for_case(
        assets_root=assets_root,
        test_id=test_id,
        test_case_id=test_case_id,
    )

    async_result = celery_app.AsyncResult(task_id)
    try:
        await to_thread(async_result.get, timeout=None, propagate=True)
    except Exception as e:
        raise RuntimeError(f"Extraction task ended in state {async_result.state}: {e}")

    report = evaluate_and_persist_case(
        assets_root=assets_root,
        test_id=test_id,
        test_case_id=test_case_id,
        min_iou=min_iou,
    )

    return {
        "status": "ok",
        "task_id": task_id,
        "task_state": async_result.state,
        "report": report,
    }
