# region Imports
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence
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
from app.utils.dev_test_derived import delete_derived

from app.utils.georeferencing import (
    ControlPoint,
    parse_control_points,
    parse_frame_bounds_entry,
    select_control_points,
)
from app.utils.georeferencing.checkpoints import validate_check_points
from app.utils.georeferencing.requirements import MIN_CONTROL_POINTS
from app.utils.imposed_colors import (
    KIND_WATER,
    KIND_ZONE,
    Picks,
    parse_imposed_colors_entries,
    split_imposed_colors_by_kind,
)
from app.utils.legend import parse_legend_entry

if TYPE_CHECKING:
    from app.utils.dev_test_evaluator import DevTestPaths

from app.utils.dev_test_evaluator import build_test_case_paths
from app.utils.georeferencing.records import RUN_RECORD_FILENAME
from app.utils.dev_test_cases import KIND_PROBE, resolve_case_kind
from app.utils.georeferencing.config import ambient_georef_config
# endregion

logger = logging.getLogger(__name__)


def write_test_config(
    parent_test_id: str,
    test_case_id: str,
    test_case_name: str | None,
    control_points: list[ControlPoint],
    check_points: list[ControlPoint],
    imposed_colors: list | None = None,
    frame_bounds: dict | None = None,
    kind: str | None = None,
    legend: dict | None = None,
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
        "kind": kind,
        "georef": {
            "controlPoints": [cp.to_dict() for cp in control_points],
            # Held out of every fit; only the evaluation reads them.
            "checkPoints": [cp.to_dict() for cp in check_points],
            "frameBounds": frame_bounds,
            "legend": legend,
        },
        "colors": {
            "imposed": imposed_colors,
        },
    }

    _drop_best_if_inputs_changed(case_dir, config_path, config_payload)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_payload, f, indent=2, ensure_ascii=False)


#: A case's "best run" artifacts. Only comparable to runs on the same inputs.
BEST_ARTIFACTS = (
    "best_report.json",
    "zones_best.geojson",
    "zones_raw_best.geojson",
)


def _drop_best_if_inputs_changed(
    case_dir: str, config_path: str, new_config: dict[str, Any]
) -> None:
    """Forget a case's best run when its clicks change."""

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            old_config = json.load(f)
    except (OSError, ValueError):
        return

    def _inputs(config: dict[str, Any]) -> tuple:
        georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}
        colors = config.get("colors") if isinstance(config.get("colors"), dict) else {}
        return (
            georef.get("controlPoints"),
            georef.get("checkPoints") or [],
            georef.get("frameBounds"),
            georef.get("legend"),
            colors.get("imposed"),
        )

    if _inputs(old_config) == _inputs(new_config):
        return
    for name in BEST_ARTIFACTS:
        try:
            os.remove(os.path.join(case_dir, name))
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"[DEV-TEST] Could not remove stale {name} in {case_dir}: {e}")


RAW_ZONES_FILENAME = "zones_raw.geojson"


def write_raw_zones(case_dir: str, collections: list | None) -> None:
    """The run's zones before snapping and the clip, beside ``zones.geojson``."""

    path = os.path.join(case_dir, RAW_ZONES_FILENAME)
    if collections is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    features = [f for fc in collections for f in fc.get("features", [])]
    os.makedirs(case_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2, ensure_ascii=False)


def slugify_test_case(value: str) -> str:
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

    from app.utils.dev_test_expected import delete_expected_zones

    delete_expected_zones(map_id)

    cases_dir = os.path.join(TEST_CASES_DIR, map_id)
    if os.path.isdir(cases_dir):
        try:
            shutil.rmtree(cases_dir)
        except OSError:
            pass

    # Derived artifacts are keyed on the map's image; with the image gone they
    # describe nothing, and leaving them would let a re-upload under the same id
    # inherit another map's OCR.
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
    """Score a case and write its report. """
    
    from app.utils.dev_test_evaluator import (
        build_test_case_paths,
        evaluate_georef_test_case,
        write_report,
    )

    paths = build_test_case_paths(assets_root, test_id, test_case_id)

    # The error overlays are derived on demand (``error_overlay``), not stored.
    report, _errors, _raw_errors = evaluate_georef_test_case(
        assets_root,
        test_id,
        test_case_id,
        min_iou=min_iou,
    )

    best_report_path = paths.best_report_path

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
            _copy_latest_to_best(paths, report)
        except Exception:
            pass

    write_report(report, paths.report_path)
    return report


def _copy_latest_to_best(paths: "DevTestPaths", report: dict[str, Any]) -> None:
    """Make the last run the case's best: its zones and report."""
    for latest, best in (
        (paths.extracted_zones_path, paths.best_zones_path),
        # The raw view of the same run, so Best can be looked at both ways.
        (paths.raw_zones_path, paths.best_raw_zones_path),
    ):
        if os.path.exists(latest):
            shutil.copyfile(latest, best)
    with open(paths.best_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def force_promote_latest_to_best(
    assets_root: str, test_id: str, test_case_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Make a case's last run its best, whatever the two scores."""

    label = f"{test_id}/{test_case_id}"
    paths = build_test_case_paths(assets_root, test_id, test_case_id)

    if not os.path.exists(paths.report_path):
        raise ValueError(f"{label} has no scored last run ({paths.report_path}): run it first")
    with open(paths.report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    if report.get("testId") != test_id or report.get("testCaseId") != test_case_id:
        raise ValueError(
            f"{paths.report_path} belongs to "
            f"{report.get('testId')}/{report.get('testCaseId')}, not {label}"
        )

    record_path = os.path.join(paths.case_dir, RUN_RECORD_FILENAME)
    if not os.path.exists(record_path):
        raise ValueError(f"{label} has no {RUN_RECORD_FILENAME}: cannot tell which settings the run used")
    with open(record_path, "r", encoding="utf-8") as f:
        inputs = json.load(f).get("inputs") or {}
    if inputs.get("runSwitches") or inputs.get("excludedControlPoints"):
        raise ValueError(
            f"{label}'s last run used non-default settings"
            f" (runSwitches={inputs.get('runSwitches')},"
            f" excludedControlPoints={inputs.get('excludedControlPoints')}):"
            " re-run it on the default settings first"
        )

    previous = None
    if os.path.exists(paths.best_report_path):
        with open(paths.best_report_path, "r", encoding="utf-8") as f:
            previous = json.load(f)

    _copy_latest_to_best(paths, report)
    return previous, report


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

    control_points: list[ControlPoint]
    #: Held out of every fit, measured against the applied transform.
    check_points: list[ControlPoint]
    frame_bounds: dict[str, float] | None
    zone_picks: Picks
    water_picks: Picks
    #: Whether the case answered the legend step, and the rectangle if any.
    legend_answered: bool = False
    legend_bounds: dict[str, float] | None = None


def parse_extraction_inputs(config: dict[str, Any]) -> CaseExtractionInputs:
    georef = config.get("georef") if isinstance(config.get("georef"), dict) else {}

    try:
        control_points = parse_control_points(georef.get("controlPoints") or [])
    except ValueError as e:
        raise ValueError(f"Invalid control points in config: {e}")

    try:
        check_points = parse_control_points(georef.get("checkPoints") or [])
        validate_check_points(control_points, check_points)
    except ValueError as e:
        raise ValueError(f"Invalid check points in config: {e}")

    # Missing here is reported by the requirements, not refused while reading.
    try:
        frame_bounds = parse_frame_bounds_entry(georef.get("frameBounds"))
    except ValueError as e:
        raise ValueError(f"Invalid frame bounds in config: {e}")

    try:
        legend_answered, legend_bounds = parse_legend_entry(georef.get("legend"))
    except ValueError as e:
        raise ValueError(f"Invalid legend in config: {e}")

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

    picks = (all_click_positions, all_colors_names, all_sampling_radii, all_color_kinds)
    return CaseExtractionInputs(
        control_points=control_points,
        check_points=check_points,
        frame_bounds=frame_bounds,
        zone_picks=split_imposed_colors_by_kind(*picks, KIND_ZONE),
        water_picks=split_imposed_colors_by_kind(*picks, KIND_WATER),
        legend_answered=legend_answered,
        legend_bounds=legend_bounds,
    )


def case_inputs_for_editing(
    assets_root: str, test_id: str, test_case_id: str
) -> dict[str, Any]:
    """A stored case's inputs, in the shape the import flow edits.

    What the dev tool needs to reopen a case's "Saisie utilisateur" steps --
    to supply an input the current algorithm requires and the case predates
    (a framing box, a legend answer) while keeping every click it already has.
    Each pipette pick carries ``hex``, sampled from the map like the import
    flow does, so the colour step shows real swatches.

    Raises:
        FileNotFoundError: no such case, or its map image is gone.
        ValueError: the stored config is malformed.
    """
    import cv2

    from app.utils.color_sampling import sample_color_at

    config = load_case_config(assets_root, test_id, test_case_id)
    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Test image not found for test_id={test_id} under {MAPS_DIR}"
        )
    inputs = parse_extraction_inputs(config)

    image_bgr = cv2.imread(image_path)
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB) if image_bgr is not None else None
    colors_section = config.get("colors") if isinstance(config.get("colors"), dict) else {}
    positions, names, radii, kinds = parse_imposed_colors_entries(
        colors_section.get("imposed")
    )
    colors = []
    for (x, y), name, radius, kind in zip(positions or [], names or [], radii or [], kinds or []):
        sampled = (
            sample_color_at(image_rgb, x, y, radius_px=int(radius))
            if image_rgb is not None
            else None
        )
        colors.append(
            {
                "x": x,
                "y": y,
                "name": name or "",
                "radius": int(radius),
                "kind": kind,
                "hex": (sampled or {}).get("hex") or "#888888",
            }
        )

    editable: dict[str, Any] = {
        "controlPoints": [cp.to_dict() for cp in inputs.control_points],
        "checkPoints": [cp.to_dict() for cp in inputs.check_points],
        "colors": colors,
    }
    if inputs.frame_bounds:
        editable["frameBounds"] = inputs.frame_bounds
    if inputs.legend_answered:
        editable["legend"] = {
            "present": inputs.legend_bounds is not None,
            "bounds": inputs.legend_bounds,
        }

    return {
        "testId": test_id,
        "testCaseId": test_case_id,
        "testCase": config.get("testCase") or test_case_id,
        "kind": config.get("kind") or None,
        "imageUrl": f"/dev-test/maps/{os.path.basename(image_path)}",
        "imageFilename": os.path.basename(image_path),
        "inputs": editable,
    }


def inspect_case(
    *,
    assets_root: str,
    test_id: str,
    test_case_id: str,
    config: Any = None,
) -> tuple[Any, CaseExtractionInputs]:
    """Load a case and resolve it against the current algorithm's requirements."""
    from app.utils.dev_test_cases import build_case_state

    case_config = load_case_config(assets_root, test_id, test_case_id)
    image_path = find_test_image_path(test_id)
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(
            f"Test image not found for test_id={test_id} under {MAPS_DIR}"
        )

    inputs = parse_extraction_inputs(case_config)
    state = build_case_state(
        test_id=test_id,
        test_case_id=test_case_id,
        inputs=inputs,
        image_path=image_path,
        config=config,
        case_config=case_config,
    )
    return state, inputs


def drop_control_points(
    control_points: Sequence[ControlPoint], excluded: Sequence[int]
) -> tuple[list[ControlPoint], list[int]]:
    """The points left once the *excluded* indices are removed, and those indices.

    Indices are positions in the case's stored list (``georef.controlPoints``),
    which is the order the dev tool lists the points in, whatever their source.

    Raises:
        ValueError: on an index that is not a stored point. Ignoring it would
            run the case on points the caller did not ask for.
    """
    drop = sorted({int(i) for i in excluded or []})
    bad = [i for i in drop if not 0 <= i < len(control_points)]
    if bad:
        raise ValueError(
            f"Control point index out of range: {bad}"
            f" (this case has {len(control_points)} points)"
        )
    dropped = set(drop)
    kept = [cp for i, cp in enumerate(control_points) if i not in dropped]
    return kept, drop


def _start_extraction_for_case(
    *,
    assets_root: str,
    test_id: str,
    test_case_id: str,
    config_overrides: dict | None = None,
    excluded_control_points: Sequence[int] | None = None,
) -> str:
    # Refuse up front what the task could only fail on: a case missing a user
    # input, or a source selection leaving fewer than 3 points ("cities only"
    # on a case with two cities).
    run_config = ambient_georef_config().with_overrides(**(config_overrides or {}))
    state, inputs = inspect_case(
        assets_root=assets_root,
        test_id=test_id,
        test_case_id=test_case_id,
        config=run_config,
    )
    if state.requirements.blocked:
        raise ValueError(
            "Cannot run this case: "
            + "; ".join(
                f"{s.key}: {s.detail or s.requirement.summary}"
                for s in state.requirements.blocked
            )
        )

    # Excluding points can leave too few among the selected sources, which the
    # requirements above (checked on every stored point) cannot see.
    kept, dropped = drop_control_points(
        inputs.control_points, excluded_control_points or []
    )
    selected = select_control_points(kept, run_config.gcp_sources)
    if dropped and len(selected) < MIN_CONTROL_POINTS:
        raise ValueError(
            f"Excluding points {dropped} leaves {len(selected)} control point(s)"
            f" from {', '.join(run_config.gcp_sources)}; at least"
            f" {MIN_CONTROL_POINTS} are needed"
        )

    from app.tasks import process_dev_test_extraction

    task = process_dev_test_extraction.delay(
        test_id=test_id,
        test_case=test_case_id,
        config_overrides=config_overrides or None,
        excluded_control_points=dropped or None,
    )
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

    kind = resolve_case_kind(test_id, test_case_id)

    # A probe has no expected zones by design, so there is nothing to evaluate against. 
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
