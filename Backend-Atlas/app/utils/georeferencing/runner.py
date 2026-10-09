import logging
import math
from typing import Any, Optional, Sequence, Tuple

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import FrameBounds
from .affine import AffineModel, fit_affine_from_control_points
from .control_points import ControlPoint
from .projection import reference_latitude
from .records import RunRecord
from .gates import AlignmentResult, align, skipped_alignment
from .reference import build_reference_layers
from .evidence import build_user_evidence


logger = logging.getLogger(__name__)


def ground_meters_per_pixel(model: AffineModel, frame_bounds: FrameBounds) -> float:
    """Ground metres per image pixel, with the WebMercator inflation removed."""
    latitude = reference_latitude(frame_bounds)
    return model.meters_per_pixel * math.cos(math.radians(latitude))


def build_alignment_inputs(
    image_bgr: Any,
    frame_bounds: FrameBounds,
    text_regions: Sequence[Any],
    water_click_positions: Optional[Sequence[Sequence[float]]] = None,
    water_sampling_radii: Optional[Sequence[int]] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    record: Optional[RunRecord] = None,
    legend_bounds: Optional[dict] = None,
) -> Optional[Tuple[Any, Any]]:
    """The reference layers and the user evidence, or None if building failed."""

    record = record or RunRecord()
    if not frame_bounds:
        raise ValueError("Alignment needs the framing box")
    if text_regions is None:
        raise ValueError("Alignment needs the OCR text regions (a list, empty if none)")

    try:
        with record.phase("reference_layers"):
            layers = build_reference_layers(frame_bounds, config)
        with record.phase("user_evidence"):
            evidence = build_user_evidence(
                image_bgr,
                text_regions=text_regions,
                water_click_positions=water_click_positions,
                water_sampling_radii=water_sampling_radii,
                config=config,
                legend_bounds=legend_bounds,
            )
    except Exception as e:
        logger.error(f"Could not build alignment inputs: {e}", exc_info=True)
        record.note(f"alignment inputs failed: {e}")
        return None

    record.set_inputs(
        referenceCoverage={k: round(v, 5) for k, v in layers.coverage().items()},
        userEvidence=evidence.stats,
        frameBounds=frame_bounds,
    )
    return layers, evidence


def align_map(
    image_bgr: Any,
    control_points: Sequence[ControlPoint],
    frame_bounds: FrameBounds,
    text_regions: Sequence[Any],
    water_click_positions: Optional[Sequence[Sequence[float]]] = None,
    water_sampling_radii: Optional[Sequence[int]] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    record: Optional[RunRecord] = None,
    debug_dir: Optional[str] = None,
    legend_bounds: Optional[dict] = None,
    inputs: Optional[Tuple[Any, Any]] = None,
) -> AlignmentResult:
    """Check the preconditions, build the evidence and reference layers, align.

    Args:
        image_bgr: the user's map as OpenCV reads it.
        control_points: the user's GCPs.
        frame_bounds: the framing box: the extent of every reference layer.
        text_regions: OCR polygons; an empty list for a map without text.
            Without them roughly half the edge pixels on a labelled map are
            place names, so they are required.
        water_click_positions: the water pipette picks. They identify the
            coastline (only edges on the water/land boundary are kept), so
            without them alignment does not run.
        legend_bounds: the legend rectangle in image pixels, or None. Its
            edges and water are dropped from the evidence.
        debug_dir: when set, every diagnostic for this run is written there.
            This is the only place that holds the reference layers, the evidence
            and the result at the same time, so the dump happens here.
        inputs: ``(layers, evidence)`` from ``build_alignment_inputs``, when the
            caller built them already; built here otherwise.
    """
    record = record or RunRecord()
    baseline = fit_affine_from_control_points(control_points)
    bounds = frame_bounds

    if not water_click_positions:
        result = skipped_alignment(baseline, "no_water_picks", record)
        _record_result(record, result)
        return result

    if inputs is None:
        inputs = build_alignment_inputs(
            image_bgr,
            frame_bounds,
            text_regions,
            water_click_positions=water_click_positions,
            water_sampling_radii=water_sampling_radii,
            config=config,
            record=record,
            legend_bounds=legend_bounds,
        )
    if inputs is None:
        result = skipped_alignment(baseline, "alignment_inputs_failed", record)
        _record_result(record, result)
        return result
    layers, evidence = inputs

    water_share = float((evidence.ocean | evidence.lakes).mean())
    if water_share < config.edge_water_min_fraction:
        result = skipped_alignment(baseline, "water_mask_too_small", record)
        _record_result(record, result)
        return result

    try:
        with record.phase("alignment"):
            result = align(
                baseline,
                control_points,
                layers,
                evidence,
                config=config,
                record=record,
                ground_meters_per_pixel=ground_meters_per_pixel(baseline, bounds),
            )
    except Exception as e:
        logger.error(f"Alignment failed: {e}", exc_info=True)
        record.note(f"alignment raised: {e}")
        return skipped_alignment(baseline, "alignment_raised", record)

    _record_result(record, result)

    if debug_dir:
        from .debug import dump_alignment_debug

        written = dump_alignment_debug(
            debug_dir,
            image_bgr,
            layers,
            evidence,
            result,
            control_points,
            baseline,
            extra={"frameBounds": bounds, "textRegions": len(text_regions or [])},
        )
        logger.info(f"[GEOREF] debug dump: {len(written)} files in {debug_dir}")

    return result


def _record_result(record: RunRecord, result: AlignmentResult) -> None:
    record.set_inputs(
        alignment={
            "method": result.method,
            "skipped": result.skipped,
            "failedChecks": result.failed_checks,
            **result.stats,
        }
    )
