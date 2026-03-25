import json
import os
import shutil
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.utils.dev_test_assets import (
    MAPS_DIR,
    TESTS_METADATA_PATH,
    TEST_CASES_DIR,
    ZONES_DIR,
)


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

    tests.sort(key=lambda t: (t.get("createdAt") or "", t["imageFilename"]))
    return tests


def register_dev_test(*, map_id: str, name: str) -> dict[str, Any]:
    metadata = _load_tests_metadata()

    entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}
    entry["name"] = name
    entry.setdefault("createdAt", datetime.utcnow().isoformat() + "Z")
    metadata[map_id] = entry

    _write_tests_metadata(metadata)
    return {"status": "ok", "mapId": map_id, "name": name}


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
        compute_errors_geojson,
        evaluate_georef_test_case,
        evaluate_georef_zones_from_paths,
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

    write_report(report, paths.report_path)
    return report
