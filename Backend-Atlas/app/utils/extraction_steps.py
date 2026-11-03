"""The georeferencing steps every entry point runs."""

import logging
from dataclasses import dataclass, replace
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
from app.utils.georeferencing.quality import predict_quality
from app.utils.georeferencing.requirements import MIN_CONTROL_POINTS
from app.utils.imposed_colors import Picks

logger = logging.getLogger(__name__)


def zone_extraction_settings(config: GeorefConfig) -> Dict[str, Any]:
    """The colour-extraction arguments that come from the config."""

    return {
        "text_inpaint_dilation_px": config.text_inpaint_dilation_px,
        "text_inpaint_max_ink_ratio": config.text_inpaint_max_ink_ratio,
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
    #: The alignment evidence, kept when ``config.align_after_piecewise`` asks
    #: for a second alignment (``post_align.AlignmentContext``).
    alignment_context: Optional[Any] = None

    def georeference(
        self,
        pixel_feature_collections: list,
        check_points: Sequence[ControlPoint] = (),
        clean: bool = True,
        score_snapping: bool = False,
    ) -> GeorefResult:
        """Pixel features -> EPSG:4326, through the aligned model when the
        alignment used the coastline.

        ``check_points`` (dev-test cases only) are measured against the applied
        transform afterwards and recorded under ``errors.checkPoints``. They are
        never passed to anything that fits.

        ``clean=False`` skips the coastline snap and the land clip, for features
        that are not land zones (a shape drawn on the map can sit at sea). Such
        a call stays out of the run record, which describes the zones.

        ``score_snapping`` (dev runners) also returns the zones cleaned without
        and with snapping, whatever the config (``GeorefResult``).
        """
        alignment = self.alignment
        aligned_model = (
            alignment.model
            if alignment is not None and alignment.used_curve_evidence
            else None
        )
        refine = bend = misfit = None
        if self.alignment_context is not None:
            from app.utils.georeferencing.bend import bend_to_coast
            from app.utils.georeferencing.post_align import (
                align_after_piecewise,
                coast_misfit_px,
            )

            context, points, config = self.alignment_context, self.control_points, self.config

            def refine(model, record):
                return align_after_piecewise(model, points, context, config, record)

            def bend(model, record):
                return bend_to_coast(model, points, context, self.image_size, config, record)

            def misfit(model):
                return coast_misfit_px(model, context)

        result = georeference_features(
            pixel_feature_collections,
            self.control_points,
            frame_bounds=self.frame_bounds,
            image_size=self.image_size,
            config=(
                self.config
                if clean
                else replace(self.config, snap_to_coastline=False, clip_to_land_mask=False)
            ),
            record=self.record if clean else None,
            model=aligned_model,
            extra_properties=(
                {"alignment_method": alignment.method}
                if alignment is not None
                else None
            ),
            refine_piecewise=refine,
            bend_to_coast=bend,
            coast_misfit_px=misfit,
            score_snapping=score_snapping and clean,
        )
        if clean and result.record is not None and result.model is not None:
            # What the run expects of itself, before the check points are
            # measured: nothing it reads may know them.
            try:
                with result.record.phase("predict_quality"):
                    predicted = predict_quality(
                        result.record.to_dict(),
                        pixel_feature_collections,
                        self.control_points,
                        result.model,
                        result.baseline,
                        self.image_size,
                        context=self.alignment_context,
                    )
                result.record.set_errors(predictedQuality=predicted)
            except Exception as e:  # a diagnostic must not fail the import
                logger.warning(f"Quality prediction failed: {e}", exc_info=True)
                result.record.set_errors(predictedQuality={"failed": f"{type(e).__name__}: {e}"})
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
    """Select the control points the config uses and align the map once."""
    
    if not frame_bounds:
        raise ValueError("Georeferencing needs the framing box")
    points = select_control_points(control_points, config.gcp_sources)
    if len(points) < MIN_CONTROL_POINTS:
        raise ValueError(
            f"Georeferencing needs at least {MIN_CONTROL_POINTS} control points"
            f" from {', '.join(config.gcp_sources)}; got {len(points)}"
        )

    alignment = None
    context = None
    # The evidence is also kept for the snap's measured tolerance.
    keep_context = (
        config.align_after_piecewise or config.coast_bend or config.coastline_snap_measured
    )
    if config.enable_curve_alignment or keep_context:
        # cv2 lives behind this import.
        from app.utils.georeferencing.runner import align_map, build_alignment_inputs

        water_positions, _names, water_radii = water_picks
        # Built once: the second alignment reads the same evidence as the first.
        inputs = build_alignment_inputs(
            image_bgr,
            frame_bounds,
            text_regions,
            water_click_positions=water_positions,
            water_sampling_radii=water_radii,
            config=config,
            record=record,
            legend_bounds=legend_bounds,
        )
        if config.enable_curve_alignment:
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
                inputs=inputs,
            )
            logger.info(
                f"[GEOREF] alignment method={alignment.method}"
                + (f" skipped={alignment.skipped}" if alignment.skipped else "")
                + (f" failed={alignment.failed_checks}" if alignment.failed_checks else "")
            )
        if keep_context and inputs is not None:
            from app.utils.georeferencing.post_align import build_alignment_context

            context = build_alignment_context(*inputs, config)

    return MapPlacement(
        control_points=points,
        alignment=alignment,
        frame_bounds=frame_bounds,
        image_size=(int(image_bgr.shape[1]), int(image_bgr.shape[0])),
        config=config,
        record=record,
        alignment_context=context,
    )
