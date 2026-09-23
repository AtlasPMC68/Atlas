import json
import os
import re
import shutil
from dataclasses import dataclass
from typing import Any, Sequence
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
from app.utils.georeferencing import parse_frame_bounds_entry
from app.utils.imposed_colors import (
    KIND_WATER,
    KIND_ZONE,
    parse_imposed_colors_entries,
    split_imposed_colors_by_kind,
)


def write_test_config(
    parent_test_id: str,
    test_case_id: str,
    test_case_name: str | None,
    original_filename: str | None,
    img_pts: list | None,
    world_pts: list | None,
    imposed_colors: list | None = None,
    frame_bounds: dict | None = None,
    kind: str | None = None,
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
        # Only written when this case departs from its map's kind; absent means
        # "whatever the map says", which is what almost every case wants.
        "kind": kind,
        "georef": {
            "imagePoints": img_pts,
            "worldPoints": world_pts,
            # The world area the user framed; the working extent for every
            # reference layer, so a case has to re-run with the same one.
            "frameBounds": frame_bounds,
        },
        # Pipette selections, kept so the case can be re-run identically later.
        "colors": {
            "imposed": imposed_colors,
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


def load_test_metadata_entry(test_id: str) -> dict[str, Any]:
    """The metadata row for one map, or an empty dict."""
    entry = _load_tests_metadata().get(test_id)
    return entry if isinstance(entry, dict) else {}


def list_dev_tests() -> list[dict[str, Any]]:
    if not os.path.isdir(MAPS_DIR):
        return []

    from app.utils.dev_test_cases import normalize_kind

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
                "kind": normalize_kind(meta_entry.get("kind")),
            }
        )

    tests.sort(key=lambda t: (t.get("createdAt") or "", t["imageFilename"]))
    return tests


def upload_dev_test(
    *,
    file_bytes: bytes,
    original_filename: str | None,
    name: str,
    kind: str | None = None,
) -> dict[str, Any]:
    from app.utils.dev_test_cases import normalize_kind

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

    resolved_kind = normalize_kind(kind)

    metadata = _load_tests_metadata()
    entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}
    entry["name"] = name
    entry["kind"] = resolved_kind
    entry.setdefault("createdAt", datetime.utcnow().isoformat() + "Z")
    metadata[map_id] = entry
    _write_tests_metadata(metadata)

    return {
        "status": "ok",
        "mapId": map_id,
        "name": name,
        "imageFilename": image_filename,
        "kind": resolved_kind,
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

    # Derived artifacts are keyed on the map's image; with the image gone they
    # describe nothing, and leaving them would let a re-upload under the same id
    # inherit another map's OCR.
    from app.utils.dev_test_derived import delete_derived

    delete_derived(map_id)

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


def delete_dev_test_case(test_id: str, test_case_id: str) -> dict[str, Any]:
    """Delete a single test case folder (config, extracted zones, reports)."""
    case_dir = os.path.join(TEST_CASES_DIR, test_id, test_case_id)
    if not os.path.isdir(case_dir):
        return {"status": "not_found", "testId": test_id, "testCaseId": test_case_id}

    shutil.rmtree(case_dir)

    # Drop the parent folder too once its last case is gone, so the test stops
    # showing an empty case list.
    parent_dir = os.path.join(TEST_CASES_DIR, test_id)
    try:
        if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
            os.rmdir(parent_dir)
    except OSError:
        pass

    return {"status": "ok", "testId": test_id, "testCaseId": test_case_id}


def evaluate_and_persist_case(
    *,
    assets_root: str,
    test_id: str,
    test_case_id: str,
    min_iou: float | None,
    allow_best_promotion: bool = True,
) -> dict[str, Any]:
    """Score a case and write its report.

    ``allow_best_promotion`` is False for a run made under non-default
    switches. ``zones_best`` means "the best run so far", and a run with
    coastline snapping flipped is not measuring the same thing -- snapping
    alone moves one map 0.941 vs 0.926 -- so promoting across settings would
    make "best" a mixture of two metrics. Such a run is still written as the
    latest result; it just cannot win.
    """
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
    if (
        allow_best_promotion
        and latest_score is not None
        and (best_score is None or latest_score > best_score)
    ):
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


def load_case_config(
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


@dataclass(frozen=True)
class CaseExtractionInputs:
    """Everything a stored case needs to re-run identically."""

    filename: str
    pixel_points: list[tuple[float, float]] | None
    geo_points_lonlat: list[tuple[float, float]] | None
    frame_bounds: dict[str, float] | None
    imposed_click_positions: list[tuple[float, float]] | None
    imposed_colors_names: list[str | None] | None
    imposed_sampling_radii: list[int] | None
    water_click_positions: list[tuple[float, float]] | None
    water_colors_names: list[str | None] | None
    water_sampling_radii: list[int] | None


def parse_extraction_inputs(
    config: dict[str, Any], image_path: str
) -> CaseExtractionInputs:
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

    # Cases written before the framing box was plumbed through simply have none.
    try:
        frame_bounds = parse_frame_bounds_entry(georef.get("frameBounds"))
    except ValueError as e:
        raise ValueError(f"Invalid frame bounds in config: {e}")

    colors = config.get("colors") if isinstance(config.get("colors"), dict) else {}
    try:
        (
            all_click_positions,
            all_colors_names,
            all_sampling_radii,
            all_color_kinds,
        ) = parse_imposed_colors_entries(colors.get("imposed"))
    except ValueError as e:
        raise ValueError(f"Invalid imposed colors in config: {e}")

    zone_picks = split_imposed_colors_by_kind(
        all_click_positions,
        all_colors_names,
        all_sampling_radii,
        all_color_kinds,
        KIND_ZONE,
    )
    water_picks = split_imposed_colors_by_kind(
        all_click_positions,
        all_colors_names,
        all_sampling_radii,
        all_color_kinds,
        KIND_WATER,
    )

    filename = config.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        filename = os.path.basename(image_path)

    return CaseExtractionInputs(
        filename=filename,
        pixel_points=pixel_points_list,
        geo_points_lonlat=geo_points_list,
        frame_bounds=frame_bounds,
        imposed_click_positions=zone_picks[0],
        imposed_colors_names=zone_picks[1],
        imposed_sampling_radii=zone_picks[2],
        water_click_positions=water_picks[0],
        water_colors_names=water_picks[1],
        water_sampling_radii=water_picks[2],
    )


def inspect_case(
    *,
    assets_root: str,
    test_id: str,
    test_case_id: str,
    config: Any = None,
) -> tuple[Any, CaseExtractionInputs]:
    """Load a case and resolve it against the current algorithm's requirements.

    The one place that answers "is this case still runnable, and is it scored"
    so the task, the regression suite and the dev script cannot drift apart on
    it. Returns ``(CaseState, CaseExtractionInputs)``.
    """
    from app.utils.dev_test_cases import build_case_state

    case_config = load_case_config(assets_root, test_id, test_case_id)
    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Test image not found for test_id={test_id} under {MAPS_DIR}"
        )

    inputs = parse_extraction_inputs(case_config, image_path)
    state = build_case_state(
        test_id=test_id,
        test_case_id=test_case_id,
        inputs=inputs,
        image_path=image_path,
        config=config,
        case_config=case_config,
    )
    return state, inputs


def build_extraction_task_kwargs_for_case(
    *, assets_root: str, test_id: str, test_case_id: str
) -> dict[str, Any]:
    """Build kwargs for process_dev_test_extraction.

    Keyword arguments rather than positional ones: the task keeps gaining
    optional inputs (framing box, water picks), and a positional list silently
    misaligns when one is inserted in the middle.
    """

    config = load_case_config(assets_root, test_id, test_case_id)
    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Test image not found for test_id={test_id} under {MAPS_DIR}"
        )

    inputs = parse_extraction_inputs(config, image_path)

    try:
        with open(image_path, "rb") as f:
            file_content = f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to read test image: {e}")

    return {
        "filename": inputs.filename,
        "file_content": file_content,
        "test_id": test_id,
        "test_case": test_case_id,
        "pixel_points": inputs.pixel_points,
        "geo_points_lonlat": inputs.geo_points_lonlat,
        "imposed_click_positions": inputs.imposed_click_positions,
        "imposed_colors_names": inputs.imposed_colors_names,
        "imposed_sampling_radii": inputs.imposed_sampling_radii,
        "frame_bounds": inputs.frame_bounds,
        "water_click_positions": inputs.water_click_positions,
        "water_colors_names": inputs.water_colors_names,
        "water_sampling_radii": inputs.water_sampling_radii,
    }


def drop_control_points(kwargs: dict[str, Any], excluded: Sequence[int]) -> list[int]:
    """Remove control points by index from task kwargs, in place.

    Filtered here rather than passed to the task, because the exclusion belongs
    to the *request*, not to the case: the stored inputs stay untouched, and
    the task signature does not gain a kwarg (which would break in-flight
    messages and any caller that has not restarted alongside the worker).

    Returns the indices actually dropped. Out-of-range indices are ignored --
    a stale UI holding indices from a case that has since been re-clicked
    should not fail the run.
    """
    pixels = kwargs.get("pixel_points")
    geos = kwargs.get("geo_points_lonlat")
    if not excluded or not pixels or not geos:
        return []

    drop = {i for i in excluded if 0 <= i < len(pixels)}
    if not drop:
        return []

    if len(pixels) - len(drop) < 3:
        raise ValueError(
            f"Excluding {len(drop)} of {len(pixels)} control points leaves fewer "
            "than the 3 an affine needs"
        )

    kwargs["pixel_points"] = [p for i, p in enumerate(pixels) if i not in drop]
    kwargs["geo_points_lonlat"] = [g for i, g in enumerate(geos) if i not in drop]
    return sorted(drop)


def _start_extraction_for_case(
    *,
    assets_root: str,
    test_id: str,
    test_case_id: str,
    config_overrides: dict | None = None,
    excluded_control_points: Sequence[int] | None = None,
) -> str:
    kwargs = build_extraction_task_kwargs_for_case(
        assets_root=assets_root,
        test_id=test_id,
        test_case_id=test_case_id,
    )
    drop_control_points(kwargs, excluded_control_points or [])
    if config_overrides:
        kwargs["config_overrides"] = config_overrides

    from app.tasks import process_dev_test_extraction

    task = process_dev_test_extraction.delay(**kwargs)
    return task.id


async def run_evaluate_case_blocking(
    *,
    test_id: str,
    test_case_id: str,
    min_iou: float | None,
    assets_root: str,
    config_overrides: dict | None = None,
    excluded_control_points: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Re-run a case and, when it is scored, evaluate it. Blocks on the task."""
    task_id = _start_extraction_for_case(
        assets_root=assets_root,
        test_id=test_id,
        test_case_id=test_case_id,
        config_overrides=config_overrides,
        excluded_control_points=excluded_control_points,
    )

    async_result = celery_app.AsyncResult(task_id)
    try:
        await to_thread(async_result.get, timeout=None, propagate=True)
    except Exception as e:
        raise RuntimeError(f"Extraction task ended in state {async_result.state}: {e}")

    from app.utils.dev_test_cases import KIND_PROBE, resolve_case_kind
    from app.utils.dev_test_evaluator import build_test_case_paths

    kind = resolve_case_kind(test_id, test_case_id)

    # A probe has no expected zones by design, so there is nothing to evaluate
    # against. The task already wrote the zones; that is the whole deliverable.
    # The task already evaluated and wrote the report; re-running it here
    # would double the work and, worse, re-decide best-promotion without
    # knowing which switches the run used.
    report = None
    if kind != KIND_PROBE:
        paths = build_test_case_paths(assets_root, test_id, test_case_id)
        try:
            with open(paths.report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, ValueError):
            report = None

    return {
        "status": "ok",
        "task_id": task_id,
        "task_state": async_result.state,
        "kind": kind,
        "switches": config_overrides or None,
        "excludedControlPoints": list(excluded_control_points or []) or None,
        "report": report,
    }
