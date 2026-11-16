"""Run the unchanged pipeline on a synthetic case (georeferencing-synthetic.md §3.1)."""

import time
from typing import Any, Dict, Optional, Sequence, Tuple

from app.utils.extraction_steps import place_map
from app.utils.georeferencing import GeorefConfig, RunRecord, record_signals
from app.utils.georeferencing.control_points import ControlPoint

from .case import SyntheticCase
from .metrics import DenseSamples, dense_error, zone_metrics


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
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Place the map as the import would, and measure it against the truth.

    Returns ``(metrics, run record, raw zones)``: the metrics as the ``m_`` and
    ``run_`` columns of results.csv, without their prefixes.
    """
    record = record or RunRecord(run_id=case.case_id)
    placement, result, pipeline_seconds = place_case(case, config, record, debug_dir)
    started = time.perf_counter()
    measured, raw = measure(case, result, samples)
    metric_seconds = time.perf_counter() - started

    record_dict = record.to_dict()
    out = {"metrics": measured, "run": run_columns(record_dict, pipeline_seconds, metric_seconds)}
    return out, record_dict, raw


def run_columns(record: Dict[str, Any], pipeline_seconds: float, metric_seconds: float) -> Dict[str, Any]:
    """What the run did and what it could see: the blind side of the table."""
    return {
        "pipelineSeconds": round(pipeline_seconds, 3),
        "metricSeconds": round(metric_seconds, 3),
        **record_signals(record),
    }
