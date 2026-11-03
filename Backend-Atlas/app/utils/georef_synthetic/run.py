"""Run the unchanged pipeline on a synthetic case (georeferencing-synthetic.md §3.1)."""

import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.utils.extraction_steps import place_map
from app.utils.georeferencing import GeorefConfig, RunRecord, record_signals
from app.utils.georeferencing.control_points import ControlPoint
from app.utils.georeferencing.quality import coast_evidence, point_features

from .case import SyntheticCase
from .metrics import DenseSamples, dense_error, ground_km, zone_metrics


def place_case(
    case: SyntheticCase,
    config: GeorefConfig,
    record: RunRecord,
    debug_dir: Optional[str] = None,
    control_points: Optional[Sequence[ControlPoint]] = None,
) -> Tuple[Any, Any, float]:
    """Place the map as the import would, with the layout's control points or
    *control_points*. Returns ``(placement, result, seconds)``."""
    started = time.perf_counter()
    placement = place_map(
        case.map.image,
        list(control_points) if control_points is not None else case.layout.control_points(),
        frame_bounds=case.map.frame_bounds,
        legend_bounds=None,
        water_picks=case.water_picks(),
        text_regions=[],
        config=config,
        record=record,
        debug_dir=debug_dir,
    )
    result = placement.georeference(
        case.pixel_zones(), check_points=case.layout.check_control_points(), score_snapping=True
    )
    return placement, result, time.perf_counter() - started


def measure(case: SyntheticCase, result: Any, samples: DenseSamples) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The ``m_`` columns of a placed case, without their prefix, and its raw zones."""
    raw, zones, unsnapped, snapped = (
        {"type": "FeatureCollection", "features": [f for fc in collections for f in fc.get("features", [])]}
        for collections in (
            result.raw_collections,
            result.collections,
            result.unsnapped_collections,
            result.snapped_collections,
        )
    )
    measured = {
        **dense_error(result.model, result.baseline, samples),
        **zone_metrics(case.map, case.case_id, raw, zones, unsnapped, snapped),
    }
    return measured, raw


def run_case(
    case: SyntheticCase,
    config: GeorefConfig,
    samples: DenseSamples,
    record: Optional[RunRecord] = None,
    debug_dir: Optional[str] = None,
    points: int = 0,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Place the map as the import would, and measure it against the truth.

    Returns ``(metrics, run record, raw zones)``: the metrics as the ``m_`` and
    ``run_`` columns of results.csv, without their prefixes. With *points*,
    the first also has ``points``: that many of the dense samples, each with
    its error and what the run knew there (``point_rows``).
    """
    record = record or RunRecord(run_id=case.case_id)
    placement, result, pipeline_seconds = place_case(case, config, record, debug_dir)
    started = time.perf_counter()
    measured, raw = measure(case, result, samples)
    metric_seconds = time.perf_counter() - started

    record_dict = record.to_dict()
    out = {"metrics": measured, "run": run_columns(record_dict, pipeline_seconds, metric_seconds)}
    if points:
        out["points"] = point_rows(case, placement, result, record_dict, samples, points)
    return out, record_dict, raw


def point_rows(
    case: SyntheticCase,
    placement: Any,
    result: Any,
    record: Dict[str, Any],
    samples: DenseSamples,
    count: int,
) -> List[Dict[str, Any]]:
    """The first *count* dense samples (a uniform subsample, the same for every
    layout and variant of a map), one row each: where the map draws it
    (``pt_x``, ``pt_y``), what the run knew there (``pt_``, from
    ``quality.point_features``, as production would compute it), whether it
    is coastal (``gen_``, from the truth) and its error (``m_``)."""
    subset = samples.subset(count)
    pixels = np.column_stack([subset.px, subset.py])
    loo = ((record.get("errors") or {}).get("affineLeaveOneOut") or {}).get("residualsPx")
    features = point_features(
        pixels,
        placement.control_points,
        result.model,
        result.baseline,
        placement.image_size,
        coast=coast_evidence(result.model, placement.alignment_context),
        loo_px=loo,
    )
    error_km = ground_km(result.model, subset)
    affine_km = ground_km(result.baseline, subset)
    km_per_px = case.map.km_per_pixel
    rows = []
    for i in range(len(pixels)):
        row: Dict[str, Any] = {"pt_index": i, "pt_x": round(float(pixels[i, 0]), 2), "pt_y": round(float(pixels[i, 1]), 2)}
        row.update({f"pt_{k}": _round(v[i]) for k, v in features.items()})
        row["gen_coastal"] = bool(subset.coastal[i])
        row["m_errorKm"] = _round(error_km[i])
        row["m_errorPx"] = _round(error_km[i] / km_per_px)
        row["m_errorKmGcpAffine"] = _round(affine_km[i])
        rows.append(row)
    return rows


def _round(value: float) -> Optional[float]:
    value = float(value)
    return round(value, 4) if math.isfinite(value) else None


def run_columns(record: Dict[str, Any], pipeline_seconds: float, metric_seconds: float) -> Dict[str, Any]:
    """What the run did and what it could see: the blind side of the table."""
    return {
        "pipelineSeconds": round(pipeline_seconds, 3),
        "metricSeconds": round(metric_seconds, 3),
        **record_signals(record),
    }
