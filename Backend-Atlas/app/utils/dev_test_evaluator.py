import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid


@dataclass(frozen=True)
class DevTestPaths:
    assets_root: str
    expected_zones_path: str
    extracted_zones_path: str
    config_path: str
    report_path: str


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
    extracted_zones_path = os.path.join(
        assets_root, "test_cases", test_id, f"{test_case_id}_zones.geojson"
    )
    config_path = os.path.join(
        assets_root, "test_cases", test_id, f"{test_case_id}_config.json"
    )
    report_path = os.path.join(
        assets_root, "test_cases", test_id, f"{test_case_id}_report.json"
    )

    return DevTestPaths(
        assets_root=assets_root,
        expected_zones_path=expected_zones_path,
        extracted_zones_path=extracted_zones_path,
        config_path=config_path,
        report_path=report_path,
    )


def evaluate_georef_test_case(
    assets_root: str,
    test_id: str,
    test_case_id: str,
    *,
    min_iou: float | None = None,
) -> dict[str, Any]:
    """Compare expected zones vs extracted zones for a given test case.

    This uses union-geometry IoU (intersection over union). Coordinates are assumed
    to be in lon/lat, so areas are in degrees^2; we only use them for ratios.
    """

    paths = build_test_case_paths(assets_root, test_id, test_case_id)

    if not os.path.exists(paths.expected_zones_path):
        raise FileNotFoundError(
            f"Expected zones not found: {paths.expected_zones_path}"
        )

    if not os.path.exists(paths.extracted_zones_path):
        raise FileNotFoundError(
            f"Extracted zones not found: {paths.extracted_zones_path}"
        )

    expected_fc = _load_json(paths.expected_zones_path)
    extracted_fc = _load_json(paths.extracted_zones_path)

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

    # New behavior: best-match IoU per expected feature (compare each expected to all extracted)
    matches: list[dict[str, Any]] = []
    for exp in expected_features:
        best: dict[str, Any] | None = None
        exp_geom: BaseGeometry = exp["geometry"]

        for ext in extracted_features:
            ext_geom: BaseGeometry = ext["geometry"]
            iou, inter_area, uni_area = _safe_iou(exp_geom, ext_geom)
            if best is None or iou > float(best.get("iou", 0.0)):
                best = {
                    "iou": iou,
                    "intersectionArea": inter_area,
                    "unionArea": uni_area,
                    "extracted": {
                        "index": ext.get("index"),
                        "id": ext.get("id"),
                        "name": ext.get("name"),
                        "area": float(ext_geom.area) if not ext_geom.is_empty else 0.0,
                    },
                }

        matches.append(
            {
                "expected": {
                    "index": exp.get("index"),
                    "id": exp.get("id"),
                    "name": exp.get("name"),
                    "area": float(exp_geom.area) if not exp_geom.is_empty else 0.0,
                },
                "bestMatch": best,
            }
        )

    # Primary score: first expected feature best-match IoU
    primary_best_iou = 0.0
    primary_match = None
    if matches:
        primary_match = matches[0]
        bm = primary_match.get("bestMatch")
        if isinstance(bm, dict):
            primary_best_iou = float(bm.get("iou", 0.0))

    # Optional config enrichment (anchor point counts)
    config: dict[str, Any] | None = None
    if os.path.exists(paths.config_path):
        try:
            config = _load_json(paths.config_path)
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
        },
        "paths": {
            "expectedZones": paths.expected_zones_path,
            "extractedZones": paths.extracted_zones_path,
            "config": paths.config_path if os.path.exists(paths.config_path) else None,
            "report": paths.report_path,
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
            "union": {
                "expectedArea": expected_union_area,
                "extractedArea": extracted_union_area,
                "intersectionArea": union_intersection_area,
                "unionArea": union_union_area,
                "iou": union_iou,
            },
        },
        "matches": matches,
    }

    if min_iou is not None:
        report["pass"] = bool(primary_best_iou >= min_iou)

    return report


def write_report(report: dict[str, Any], report_path: str) -> None:
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
