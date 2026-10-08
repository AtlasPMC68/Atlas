"""One entry point from a map image to a gated alignment.

This is the only module besides `evidence.py` that needs cv2, because it reads
the image. Everything it calls afterwards -- reference layers, the chamfer, ICP,
the gates, the ladder -- is cv2-free.

The Celery task and the dev script both come through here, so the production
path and the measurement path cannot drift apart.
"""

import logging
import math
from typing import Any, Optional, Sequence, Tuple

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import FrameBounds
from .models import AffineModel, ControlPoint, fit_affine_from_control_points
from .projection import reference_latitude
from .records import RunRecord
from .recovery import AlignmentResult, align
from .reference import build_reference_layers

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
    """The reference layers and the user evidence, or None if building failed.

    Missing inputs are a caller error and raise; a failure while building is
    logged, recorded and returned as None, for the caller to fall back.
    """
    from .evidence import build_user_evidence  # cv2 lives behind this import

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
    """Build the evidence and reference layers, then align and gate.

    A failure while building the layers or aligning falls back to the GCP-only
    affine, so a caller can use ``result.model`` unconditionally; every such
    path is recorded. Missing inputs are a caller error and raise.

    Args:
        image_bgr: the user's map as OpenCV reads it.
        control_points: the user's GCPs.
        frame_bounds: the framing box: the extent of every reference layer.
        text_regions: OCR polygons; an empty list for a map without text.
            Without them roughly half the edge pixels on a labelled map are
            place names, so they are required.
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
        return AlignmentResult(model=baseline, method="gcp_only", rung=7)
    layers, evidence = inputs

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
        return AlignmentResult(model=baseline, method="gcp_only", rung=7)

    record.set_inputs(
        alignment={
            "method": result.method,
            "rung": result.rung,
            "failedChecks": result.failed_checks,
            "probeAgreementPx": result.probe_agreement_px,
            **result.stats,
        }
    )

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
