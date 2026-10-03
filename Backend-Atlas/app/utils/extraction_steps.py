"""The steps every entry point runs: zones from the pipette, the gated
alignment, and the transform.

Three callers -- the import task, the dev-test task and
``scripts/run_georef_alignment.py`` -- used to pass their own arguments to
these, and drifted: the script stopped passing the text-fill settings and the
image size, so its numbers no longer matched a re-run from the dev tool. They
now call these functions with the same config, and differ only in where the
inputs come from and where the results go.
"""

import logging
from typing import Any, Dict, Optional, Sequence

from app.utils.color_extraction import extract_colors
from app.utils.georeferencing import (
    AlignmentResult,
    ControlPoint,
    GeorefConfig,
    GeorefResult,
    RunRecord,
    georeference_features,
)

logger = logging.getLogger(__name__)


def zone_extraction_settings(config: GeorefConfig) -> Dict[str, Any]:
    """The colour-extraction arguments that come from the config.

    Also part of the dev script's colour cache key, so a setting added here
    invalidates cached zones by construction.
    """
    return {
        "text_fill_min_context": config.text_fill_min_context,
        "text_fill_max_distance_px": config.text_fill_max_distance_px,
        "text_fill_method": config.text_fill_method,
        "text_inpaint_dilation_px": config.text_inpaint_dilation_px,
        "text_inpaint_radius_px": config.text_inpaint_radius_px,
        "text_inpaint_max_ink_ratio": config.text_inpaint_max_ink_ratio,
        "text_inpaint_algo": config.text_inpaint_algo,
        "text_inpaint_ink_deltaE": config.text_inpaint_ink_deltaE,
        "zone_gap_fill": config.zone_gap_fill,
        "zone_gap_max_ratio_of_diagonal": config.zone_gap_max_ratio_of_diagonal,
    }


def extract_zone_colors(
    image_path: str,
    *,
    legend_bounds: Optional[dict],
    click_positions: Optional[Sequence[Sequence[float]]],
    names: Optional[Sequence[Optional[str]]],
    radii: Optional[Sequence[int]],
    text_regions: Optional[list],
    config: GeorefConfig,
) -> Dict[str, Any]:
    """Pixel-space zones from the zone pipette picks."""
    return extract_colors(
        image_path,
        debug=False,
        legend_bounds=legend_bounds,
        imposed_click_positions=[tuple(c) for c in click_positions or []] or None,
        imposed_colors_names=list(names) if names else None,
        imposed_sampling_radii=[int(r) for r in radii] if radii else None,
        text_regions=text_regions if config.text_aware_zone_fill else None,
        **zone_extraction_settings(config),
    )


def align_if_enabled(
    image_bgr: Any,
    control_points: Sequence[ControlPoint],
    *,
    frame_bounds: Optional[dict],
    text_regions: Optional[list],
    water_click_positions: Optional[list],
    water_sampling_radii: Optional[list],
    legend_bounds: Optional[dict],
    config: GeorefConfig,
    record: Optional[RunRecord] = None,
    debug_dir: Optional[str] = None,
) -> Optional[AlignmentResult]:
    """Curve alignment, or None when it is switched off or cannot run."""
    if not config.enable_curve_alignment or image_bgr is None or not control_points:
        return None

    from app.utils.georeferencing.runner import align_map  # cv2 lives behind this

    result = align_map(
        image_bgr,
        control_points,
        frame_bounds=frame_bounds,
        text_regions=text_regions,
        water_click_positions=water_click_positions,
        water_sampling_radii=water_sampling_radii,
        config=config,
        record=record,
        debug_dir=debug_dir,
        legend_bounds=legend_bounds,
    )
    logger.info(
        f"[GEOREF] alignment method={result.method} rung={result.rung}"
        + (f" failed={result.failed_checks}" if result.failed_checks else "")
    )
    return result


def georeference_zones(
    pixel_feature_collections: list,
    control_points: Sequence[ControlPoint],
    *,
    frame_bounds: Optional[dict],
    image_bgr: Any,
    alignment: Optional[AlignmentResult],
    config: GeorefConfig,
    record: Optional[RunRecord] = None,
) -> GeorefResult:
    """Pixel -> EPSG:4326, with the aligned model when alignment used the curves.

    The image size is what the snap tolerance is a share of; without it the
    zones' own extent stands in and the tolerance changes with where the zones
    happen to be.
    """
    aligned_model = (
        alignment.model
        if alignment is not None and alignment.used_curve_evidence
        else None
    )
    extra_properties = (
        {"alignment_method": alignment.method, "alignment_rung": alignment.rung}
        if alignment is not None
        else None
    )
    image_size = (
        (int(image_bgr.shape[1]), int(image_bgr.shape[0]))
        if image_bgr is not None
        else None
    )
    return georeference_features(
        pixel_feature_collections,
        control_points,
        frame_bounds=frame_bounds,
        config=config,
        record=record,
        model=aligned_model,
        extra_properties=extra_properties,
        image_size=image_size,
    )
