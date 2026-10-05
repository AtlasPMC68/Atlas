"""The georeferencing steps every entry point runs, in one place.

Three callers -- the import task, the dev-test task and the dev scripts
(``run_georef_alignment.py``, ``run_georef_variants.py``) -- run the same
pipeline and differ only in where the inputs come from and where the results
go:

    extract_zone_colors   pixel zones from the pipette picks
    place_map             the control points, aligned once: the transform
                          every feature producer of the map shares
    MapPlacement.georeference
                          pixel features -> EPSG:4326, cleaned, with the raw
                          (uncleaned) copy and the check-point errors

They used to assemble these steps themselves and drifted apart (the script
stopped passing the text-fill settings and the image size, so its numbers no
longer matched a re-run from the dev tool).
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from app.utils.color_extraction import extract_colors
from app.utils.georeferencing import (
    AlignmentResult,
    ControlPoint,
    GeorefConfig,
    GeorefResult,
    RunRecord,
    georeference_features,
    select_control_points,
)
from app.utils.georeferencing.checkpoints import measure_check_points
from app.utils.georeferencing.requirements import MIN_CONTROL_POINTS
from app.utils.imposed_colors import Picks

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
    zone_picks: Picks,
    legend_bounds: Optional[dict],
    text_regions: Optional[list],
    config: GeorefConfig,
) -> Dict[str, Any]:
    """Pixel-space zones from the zone pipette picks."""
    positions, names, radii = zone_picks
    return extract_colors(
        image_path,
        debug=False,
        legend_bounds=legend_bounds,
        imposed_click_positions=[tuple(c) for c in positions or []] or None,
        imposed_colors_names=list(names) if names else None,
        imposed_sampling_radii=[int(r) for r in radii] if radii else None,
        text_regions=text_regions if config.text_aware_zone_fill else None,
        **zone_extraction_settings(config),
    )


@dataclass(frozen=True)
class MapPlacement:
    """Where one map sits on Earth: the transform its features all share."""

    control_points: List[ControlPoint]
    alignment: Optional[AlignmentResult]
    frame_bounds: dict
    image_size: tuple
    config: GeorefConfig
    record: Optional[RunRecord] = None

    def georeference(
        self,
        pixel_feature_collections: list,
        check_points: Sequence[ControlPoint] = (),
    ) -> GeorefResult:
        """Pixel features -> EPSG:4326, through the aligned model when the
        alignment used the coastline.

        ``check_points`` (dev-test cases only) are measured against the applied
        transform afterwards and recorded under ``errors.checkPoints``. They are
        never passed to anything that fits.
        """
        alignment = self.alignment
        aligned_model = (
            alignment.model
            if alignment is not None and alignment.used_curve_evidence
            else None
        )
        result = georeference_features(
            pixel_feature_collections,
            self.control_points,
            frame_bounds=self.frame_bounds,
            image_size=self.image_size,
            config=self.config,
            record=self.record,
            model=aligned_model,
            extra_properties=(
                {"alignment_method": alignment.method, "alignment_rung": alignment.rung}
                if alignment is not None
                else None
            ),
        )
        if check_points and result.record is not None:
            result.record.set_errors(
                checkPoints=measure_check_points(
                    check_points,
                    result.model,
                    frame_bounds=self.frame_bounds,
                    baseline_model=result.baseline,
                    control_points=self.control_points,
                )
            )
        return result


def place_map(
    image_bgr: Any,
    control_points: Sequence[ControlPoint],
    *,
    frame_bounds: Optional[dict],
    legend_bounds: Optional[dict],
    water_picks: Picks,
    text_regions: Optional[list],
    config: GeorefConfig,
    record: Optional[RunRecord] = None,
    debug_dir: Optional[str] = None,
) -> MapPlacement:
    """Select the control points the config uses and align the map once.

    Raises:
        ValueError: without a framing box or enough control points, which every
            entry point requires before getting here.
    """
    if not frame_bounds:
        raise ValueError("Georeferencing needs the framing box")
    points = select_control_points(control_points, config.gcp_sources)
    if len(points) < MIN_CONTROL_POINTS:
        raise ValueError(
            f"Georeferencing needs at least {MIN_CONTROL_POINTS} control points"
            f" from {', '.join(config.gcp_sources)}; got {len(points)}"
        )

    alignment = None
    if config.enable_curve_alignment:
        from app.utils.georeferencing.runner import align_map  # cv2 lives behind this

        water_positions, _names, water_radii = water_picks
        alignment = align_map(
            image_bgr,
            points,
            frame_bounds=frame_bounds,
            text_regions=text_regions,
            water_click_positions=water_positions,
            water_sampling_radii=water_radii,
            config=config,
            record=record,
            debug_dir=debug_dir,
            legend_bounds=legend_bounds,
        )
        logger.info(
            f"[GEOREF] alignment method={alignment.method} rung={alignment.rung}"
            + (f" failed={alignment.failed_checks}" if alignment.failed_checks else "")
        )

    return MapPlacement(
        control_points=points,
        alignment=alignment,
        frame_bounds=frame_bounds,
        image_size=(int(image_bgr.shape[1]), int(image_bgr.shape[0])),
        config=config,
        record=record,
    )
