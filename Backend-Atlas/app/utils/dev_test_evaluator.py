import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid


@dataclass(frozen=True)
class DevTestPaths:
    assets_root: str
    case_dir: str
    expected_zones_path: str
    extracted_zones_path: str
    config_path: str
    report_path: str
    errors_geojson_path: str
    best_report_path: str
    best_zones_path: str
    best_errors_geojson_path: str


def write_geojson(feature_collection: dict[str, Any], geojson_path: str) -> None:
    os.makedirs(os.path.dirname(geojson_path), exist_ok=True)
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, indent=2, ensure_ascii=False)


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON root in {path}")
    return data


def _feature_collection_geoms(fc: dict[str, Any]) -> list[BaseGeometry]:
    features = fc.get("features")
    if not isinstance(features, list):
        return []

    geoms: list[BaseGeometry] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry")
        if not isinstance(geom, dict):
            continue
        try:
            g = shape(geom)
            if g.is_empty:
                continue
            g = make_valid(g)
            if g.is_empty:
                continue
            geoms.append(g)
        except Exception:
            # Ignore malformed geometries in dev-test context
            continue

    return geoms


def _feature_collection_geoms_with_meta(fc: dict[str, Any]) -> list[dict[str, Any]]:
    features = fc.get("features")
    if not isinstance(features, list):
        return []

    out: list[dict[str, Any]] = []
    for idx, feat in enumerate(features):
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry")
        if not isinstance(geom, dict):
            continue

        props = (
            feat.get("properties") if isinstance(feat.get("properties"), dict) else {}
        )
        name = None
        if isinstance(props, dict):
            name = props.get("name")
        if not isinstance(name, str) or not name.strip():
            name = None

        feat_id = feat.get("id")
        if not isinstance(feat_id, str) or not feat_id.strip():
            feat_id = None

        try:
            g = shape(geom)
            if g.is_empty:
                continue
            g = make_valid(g)
            if g.is_empty:
                continue
        except Exception:
            continue

        out.append(
            {
                "index": idx,
                "id": feat_id,
                "name": name,
                "geometry": g,
            }
        )

    return out


def _safe_iou(a: BaseGeometry, b: BaseGeometry) -> tuple[float, float, float]:
    """Return (iou, intersection_area, union_area) with best-effort safety."""
    if a.is_empty and b.is_empty:
        return 0.0, 0.0, 0.0

    try:
        inter = a.intersection(b)
        uni = a.union(b)
        intersection_area = float(inter.area) if not inter.is_empty else 0.0
        union_area = float(uni.area) if not uni.is_empty else 0.0
        if union_area <= 0:
            return 0.0, intersection_area, union_area
        return intersection_area / union_area, intersection_area, union_area
    except Exception:
        return 0.0, 0.0, 0.0


def _safe_ratio(numer: float, denom: float) -> float:
    try:
        if denom <= 0:
            return 0.0
        return float(numer) / float(denom)
    except Exception:
        return 0.0


def _safe_make_valid(g: BaseGeometry) -> BaseGeometry:
    try:
        if g.is_empty:
            return g
        return make_valid(g)
    except Exception:
        return g


def _errors_feature_collection(*, matches: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a GeoJSON FeatureCollection for FP/FN areas per expected feature.

    For each expected feature, we find its best-match extracted feature (already
    computed in `matches`). FP/FN are then computed *only on that pair*:

    - false negative: expected \ extracted_best
    - false positive: extracted_best \ expected
    """

    features: list[dict[str, Any]] = []

    for m in matches:
        exp = m.get("expected") if isinstance(m.get("expected"), dict) else None
        bm = m.get("bestMatch") if isinstance(m.get("bestMatch"), dict) else None

        exp_geom = exp.get("geometry") if isinstance(exp, dict) else None
        ext_geom = bm.get("geometry") if isinstance(bm, dict) else None

        if not isinstance(exp_geom, BaseGeometry):
            continue

        expected_name = exp.get("name") if isinstance(exp, dict) else None
        expected_label = (
            f"expected_positive_{expected_name}"
            if isinstance(expected_name, str) and expected_name.strip()
            else f"expected_positive_{exp.get('index')}"
        )

        expected_index = exp.get("index") if isinstance(exp, dict) else None

        extracted_meta = bm.get("extracted") if isinstance(bm, dict) else None
        extracted_index = (
            extracted_meta.get("index") if isinstance(extracted_meta, dict) else None
        )
        extracted_id = (
            extracted_meta.get("id") if isinstance(extracted_meta, dict) else None
        )
        extracted_name = (
            extracted_meta.get("name") if isinstance(extracted_meta, dict) else None
        )

        # If there is no extracted match, FN is the whole expected geom and FP is empty.
        if not isinstance(ext_geom, BaseGeometry):
            fn = _safe_make_valid(exp_geom)
            fp = _safe_make_valid(unary_union([]))
        else:
            fn = _safe_make_valid(exp_geom.difference(ext_geom))
            fp = _safe_make_valid(ext_geom.difference(exp_geom))

        if not fn.is_empty and float(fn.area) > 0.0:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "kind": "false_negative",
                        "suggestedColor": "red",
                        "name": expected_label,
                        "expectedIndex": expected_index,
                        "expectedName": expected_name,
                        "extractedIndex": extracted_index,
                        "extractedId": extracted_id,
                        "extractedName": extracted_name,
                    },
                    "geometry": mapping(fn),
                }
            )

        if not fp.is_empty and float(fp.area) > 0.0:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "kind": "false_positive",
                        "suggestedColor": "red",
                        "name": expected_label,
                        "expectedIndex": expected_index,
                        "expectedName": expected_name,
                        "extractedIndex": extracted_index,
                        "extractedId": extracted_id,
                        "extractedName": extracted_name,
                    },
                    "geometry": mapping(fp),
                }
            )

    return {"type": "FeatureCollection", "features": features}


def _union_or_empty(geoms: list[BaseGeometry]) -> BaseGeometry:
    if not geoms:
        return unary_union([])
    try:
        return unary_union(geoms)
    except Exception:
        # Fallback: union iteratively
        u = geoms[0]
        for g in geoms[1:]:
            try:
                u = u.union(g)
            except Exception:
                continue
        return u


def build_test_case_paths(
    assets_root: str, test_id: str, test_case_id: str
) -> DevTestPaths:
    expected_zones_path = os.path.join(
        assets_root, "georef_zones", f"{test_id}_zones.geojson"
    )
    case_dir = os.path.join(assets_root, "test_cases", test_id, test_case_id)

    # New nested layout
    extracted_zones_path = os.path.join(case_dir, "zones.geojson")
    config_path = os.path.join(case_dir, "config.json")
    report_path = os.path.join(case_dir, "report.json")
    errors_geojson_path = os.path.join(case_dir, "errors.geojson")
    best_report_path = os.path.join(case_dir, "best_report.json")
    best_zones_path = os.path.join(case_dir, "zones_best.geojson")
    best_errors_geojson_path = os.path.join(case_dir, "errors_best.geojson")

    return DevTestPaths(
        assets_root=assets_root,
        case_dir=case_dir,
        expected_zones_path=expected_zones_path,
        extracted_zones_path=extracted_zones_path,
        config_path=config_path,
        report_path=report_path,
        errors_geojson_path=errors_geojson_path,
        best_report_path=best_report_path,
        best_zones_path=best_zones_path,
        best_errors_geojson_path=best_errors_geojson_path,
    )


def evaluate_georef_zones_from_paths(
    *,
    test_id: str,
    test_case_id: str,
    expected_zones_path: str,
    extracted_zones_path: str,
    config_path: str | None = None,
    report_path: str | None = None,
    errors_geojson_path: str | None = None,
    min_iou: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Evaluate expected vs extracted zones given explicit file paths.

    This is used for generating/backfilling artifacts (e.g. best snapshots)
    without relying on the conventional on-disk naming.
    """

    if not os.path.exists(expected_zones_path):
        raise FileNotFoundError(f"Expected zones not found: {expected_zones_path}")
    if not os.path.exists(extracted_zones_path):
        raise FileNotFoundError(f"Extracted zones not found: {extracted_zones_path}")

    expected_fc = _load_json(expected_zones_path)
    extracted_fc = _load_json(extracted_zones_path)

    expected_features = _feature_collection_geoms_with_meta(expected_fc)
    extracted_features = _feature_collection_geoms_with_meta(extracted_fc)

    expected_geoms = [f["geometry"] for f in expected_features]
    extracted_geoms = [f["geometry"] for f in extracted_features]

    # Debug metrics (previous behavior): union vs union IoU
    expected_union = _union_or_empty(expected_geoms)
    extracted_union = _union_or_empty(extracted_geoms)
    union_iou, union_intersection_area, union_union_area = _safe_iou(
        expected_union, extracted_union
    )

    expected_union_area = (
        float(expected_union.area) if not expected_union.is_empty else 0.0
    )
    extracted_union_area = (
        float(extracted_union.area) if not extracted_union.is_empty else 0.0
    )

    union_precision = _safe_ratio(union_intersection_area, extracted_union_area)
    union_recall = _safe_ratio(union_intersection_area, expected_union_area)

    # Best-match IoU per expected feature (compare each expected to all extracted)
    matches: list[dict[str, Any]] = []
    for exp in expected_features:
        best: dict[str, Any] | None = None
        exp_geom: BaseGeometry = exp["geometry"]

        exp_area = float(exp_geom.area) if not exp_geom.is_empty else 0.0

        for ext in extracted_features:
            ext_geom: BaseGeometry = ext["geometry"]
            iou, inter_area, uni_area = _safe_iou(exp_geom, ext_geom)
            if best is None or iou > float(best.get("iou", 0.0)):
                ext_area = float(ext_geom.area) if not ext_geom.is_empty else 0.0
                precision = _safe_ratio(inter_area, ext_area)
                recall = _safe_ratio(inter_area, exp_area)
                fn = _safe_make_valid(exp_geom.difference(ext_geom))
                fp = _safe_make_valid(ext_geom.difference(exp_geom))
                fn_area = float(fn.area) if not fn.is_empty else 0.0
                fp_area = float(fp.area) if not fp.is_empty else 0.0
                best = {
                    "iou": iou,
                    "intersectionArea": inter_area,
                    "unionArea": uni_area,
                    "precision": precision,
                    "recall": recall,
                    "falseNegativeArea": fn_area,
                    "falsePositiveArea": fp_area,
                    "extracted": {
                        "index": ext.get("index"),
                        "id": ext.get("id"),
                        "name": ext.get("name"),
                        "area": float(ext_geom.area) if not ext_geom.is_empty else 0.0,
                    },
                    # Keep geometry only for producing error overlays (not persisted in report JSON).
                    "geometry": ext_geom,
                }

        if best is None:
            best = {
                "iou": 0.0,
                "intersectionArea": 0.0,
                "unionArea": exp_area,
                "precision": 0.0,
                "recall": 0.0,
                "falseNegativeArea": exp_area,
                "falsePositiveArea": 0.0,
                "extracted": None,
                "geometry": None,
            }

        matches.append(
            {
                "expected": {
                    "index": exp.get("index"),
                    "id": exp.get("id"),
                    "name": exp.get("name"),
                    "area": float(exp_geom.area) if not exp_geom.is_empty else 0.0,
                    "geometry": exp_geom,
                },
                "bestMatch": best,
            }
        )

    errors_geojson = _errors_feature_collection(matches=matches)

    for m in matches:
        exp = m.get("expected")
        if isinstance(exp, dict) and "geometry" in exp:
            exp.pop("geometry", None)
        bm = m.get("bestMatch")
        if isinstance(bm, dict) and "geometry" in bm:
            bm.pop("geometry", None)

    primary_best_iou = 0.0
    primary_match = None
    if matches:
        primary_match = matches[0]
        bm = primary_match.get("bestMatch")
        if isinstance(bm, dict):
            primary_best_iou = float(bm.get("iou", 0.0))

    # Aggregate metrics across expected features using their best matches.
    # These are the primary "meaningful" metrics (no dependence on unused extracted zones).
    ious: list[float] = []
    precisions: list[float] = []
    recalls: list[float] = []
    fn_areas: list[float] = []
    fp_areas: list[float] = []
    for m in matches:
        bm = m.get("bestMatch") if isinstance(m, dict) else None
        if not isinstance(bm, dict):
            continue
        try:
            ious.append(float(bm.get("iou", 0.0)))
        except Exception:
            ious.append(0.0)
        try:
            precisions.append(float(bm.get("precision", 0.0)))
        except Exception:
            precisions.append(0.0)
        try:
            recalls.append(float(bm.get("recall", 0.0)))
        except Exception:
            recalls.append(0.0)
        try:
            fn_areas.append(float(bm.get("falseNegativeArea", 0.0)))
        except Exception:
            fn_areas.append(0.0)
        try:
            fp_areas.append(float(bm.get("falsePositiveArea", 0.0)))
        except Exception:
            fp_areas.append(0.0)

    mean_iou = _safe_ratio(sum(ious), float(len(ious))) if ious else 0.0
    mean_precision = (
        _safe_ratio(sum(precisions), float(len(precisions))) if precisions else 0.0
    )
    mean_recall = _safe_ratio(sum(recalls), float(len(recalls))) if recalls else 0.0
    total_fn_area = float(sum(fn_areas)) if fn_areas else 0.0
    total_fp_area = float(sum(fp_areas)) if fp_areas else 0.0

    config: dict[str, Any] | None = None
    if config_path and os.path.exists(config_path):
        try:
            config = _load_json(config_path)
        except Exception:
            config = None

    image_points_count = None
    world_points_count = None
    if config and isinstance(config.get("georef"), dict):
        img = config["georef"].get("imagePoints")
        w = config["georef"].get("worldPoints")
        if isinstance(img, list):
            image_points_count = len(img)
        if isinstance(w, list):
            world_points_count = len(w)

    report: dict[str, Any] = {
        "testId": test_id,
        "testCaseId": test_case_id,
        "evaluatedAt": datetime.utcnow().isoformat() + "Z",
        "thresholds": {
            "minIou": min_iou,
            "scoreKey": "metrics.expectedBest.meanIou",
        },
        "paths": {
            "expectedZones": expected_zones_path,
            "extractedZones": extracted_zones_path,
            "config": config_path
            if (config_path and os.path.exists(config_path))
            else None,
            "report": report_path,
            "errorsGeojson": errors_geojson_path,
        },
        "counts": {
            "expectedFeatures": len(expected_fc.get("features") or [])
            if isinstance(expected_fc.get("features"), list)
            else 0,
            "extractedFeatures": len(extracted_fc.get("features") or [])
            if isinstance(extracted_fc.get("features"), list)
            else 0,
            "expectedGeometries": len(expected_features),
            "extractedGeometries": len(extracted_features),
            "anchorImagePoints": image_points_count,
            "anchorWorldPoints": world_points_count,
        },
        "metrics": {
            "primaryExpectedBestIou": primary_best_iou,
            "primaryExpected": primary_match.get("expected")
            if isinstance(primary_match, dict)
            else None,
            "primaryMatch": primary_match.get("bestMatch")
            if isinstance(primary_match, dict)
            else None,
            "expectedBest": {
                "meanIou": mean_iou,
                "meanPrecision": mean_precision,
                "meanRecall": mean_recall,
                "totalFalseNegativeArea": total_fn_area,
                "totalFalsePositiveArea": total_fp_area,
            },
            "scoreUsed": mean_iou,
            "scoreUsedKey": "expectedBest.meanIou",
        },
        "debug": {
            "union": {
                "expectedArea": expected_union_area,
                "extractedArea": extracted_union_area,
                "intersectionArea": union_intersection_area,
                "unionArea": union_union_area,
                "iou": union_iou,
                "precision": union_precision,
                "recall": union_recall,
            }
        },
        "matches": matches,
    }

    if min_iou is not None:
        report["pass"] = bool(mean_iou >= min_iou)

    return report, errors_geojson


def evaluate_georef_test_case(
    assets_root: str,
    test_id: str,
    test_case_id: str,
    *,
    min_iou: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compare expected zones vs extracted zones for a given test case.

    Coordinates are assumed to be in lon/lat, so areas are in degrees^2. We mostly
    use area ratios (IoU / precision / recall) for scoring and debugging.
    """

    paths = build_test_case_paths(assets_root, test_id, test_case_id)
    return evaluate_georef_zones_from_paths(
        test_id=test_id,
        test_case_id=test_case_id,
        expected_zones_path=paths.expected_zones_path,
        extracted_zones_path=paths.extracted_zones_path,
        config_path=paths.config_path,
        report_path=paths.report_path,
        errors_geojson_path=paths.errors_geojson_path,
        min_iou=min_iou,
    )


def write_report(report: dict[str, Any], report_path: str) -> None:
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def compute_errors_geojson(
    *, expected_zones_path: str, extracted_zones_path: str
) -> dict[str, Any]:
    """Compute FP/FN overlay FeatureCollection for a given expected/extracted pair.

    This is used for artifact generation/backfill (e.g. best snapshot) without
    having to run a full evaluation report.
    """

    expected_fc = _load_json(expected_zones_path)
    extracted_fc = _load_json(extracted_zones_path)

    expected_features = _feature_collection_geoms_with_meta(expected_fc)
    extracted_features = _feature_collection_geoms_with_meta(extracted_fc)

    matches: list[dict[str, Any]] = []
    for exp in expected_features:
        exp_geom: BaseGeometry = exp["geometry"]
        best: dict[str, Any] | None = None

        for ext in extracted_features:
            ext_geom: BaseGeometry = ext["geometry"]
            iou, _inter_area, _uni_area = _safe_iou(exp_geom, ext_geom)
            if best is None or iou > float(best.get("iou", 0.0)):
                best = {
                    "iou": iou,
                    "extracted": {
                        "index": ext.get("index"),
                        "id": ext.get("id"),
                        "name": ext.get("name"),
                    },
                    "geometry": ext_geom,
                }

        if best is None:
            best = {"iou": 0.0, "extracted": None, "geometry": None}

        matches.append(
            {
                "expected": {
                    "index": exp.get("index"),
                    "id": exp.get("id"),
                    "name": exp.get("name"),
                    "geometry": exp_geom,
                },
                "bestMatch": best,
            }
        )

    errors_geojson = _errors_feature_collection(matches=matches)
    return errors_geojson
