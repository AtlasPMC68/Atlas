"""One entry point from a map image to a gated alignment.

This is the only module besides `evidence.py` that needs cv2, because it reads
the image. Everything it calls afterwards -- reference layers, the chamfer, ICP,
the gates, the ladder -- is cv2-free.

The Celery task and the dev script both come through here, so the production
path and the measurement path cannot drift apart.
"""

import logging
import math
from typing import Any, Optional, Sequence

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import FrameBounds, frame_bounds_from_geo_points
from .models import AffineModel, ControlPoint, fit_affine_from_control_points
from .projection import reference_latitude
from .records import RunRecord
from .recovery import AlignmentResult, align
from .reference import build_reference_layers

logger = logging.getLogger(__name__)


def ground_meters_per_pixel(
    model: AffineModel, frame_bounds: Optional[FrameBounds], control_points
) -> Optional[float]:
    """Ground metres per image pixel, with the WebMercator inflation removed."""
    latitude = reference_latitude(frame_bounds, [cp.geo for cp in control_points])
    if latitude is None:
        return None
    return model.meters_per_pixel * math.cos(math.radians(latitude))


def align_map(
    image_bgr: Any,
    control_points: Sequence[ControlPoint],
    frame_bounds: Optional[FrameBounds] = None,
    text_regions: Optional[Any] = None,
    water_click_positions: Optional[Sequence[Sequence[float]]] = None,
    water_sampling_radii: Optional[Sequence[int]] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    record: Optional[RunRecord] = None,
    debug_dir: Optional[str] = None,
) -> AlignmentResult:
    """Build the evidence and reference layers, then align and gate.

    Falls back to the GCP-only affine -- never raises -- so a caller can use
    ``result.model`` unconditionally. Every failure path is recorded.

    Args:
        image_bgr: the user's map as OpenCV reads it.
        control_points: the user's GCPs.
        frame_bounds: the framing box. Derived from the control points when the
            map predates the field.
        text_regions: OCR polygons. Strongly recommended: without them roughly
            half the edge pixels on a labelled map are place names.
        debug_dir: when set, every diagnostic for this run is written there.
            This is the only place that holds the reference layers, the evidence
            and the result at the same time, so the dump happens here.
    """
    from .evidence import build_user_evidence  # cv2 lives behind this import

    record = record or RunRecord()
    baseline = fit_affine_from_control_points(control_points)

    bounds = frame_bounds or frame_bounds_from_geo_points(
        [cp.geo for cp in control_points]
    )
    if not bounds:
        record.note("no framing box and too few control points; alignment skipped")
        return AlignmentResult(model=baseline, method="gcp_only", rung=7)

    if text_regions is None:
        record.note(
            "aligning without a text mask: about half the edge map may be labels"
        )

    try:
        with record.phase("reference_layers"):
            layers = build_reference_layers(bounds, config)
        with record.phase("user_evidence"):
            evidence = build_user_evidence(
                image_bgr,
                text_regions=text_regions,
                water_click_positions=water_click_positions,
                water_sampling_radii=water_sampling_radii,
                config=config,
            )
    except Exception as e:
        logger.error(f"Could not build alignment inputs: {e}", exc_info=True)
        record.note(f"alignment inputs failed: {e}")
        return AlignmentResult(model=baseline, method="gcp_only", rung=7)

    record.set_inputs(
        referenceCoverage={k: round(v, 5) for k, v in layers.coverage().items()},
        userEvidence=evidence.stats,
        frameBounds=bounds,
    )

    try:
        with record.phase("alignment"):
            result = align(
                baseline,
                control_points,
                layers,
                evidence,
                config=config,
                record=record,
                ground_meters_per_pixel=ground_meters_per_pixel(
                    baseline, bounds, control_points
                ),
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
