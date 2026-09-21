"""Frozen hyperparameters for the georeferencing pipeline.

Every tunable constant lives here as one versioned dataclass rather than as a
default scattered across a function signature. This deliberately deviates from
the surrounding style (``extract_colors`` carries ~10 inline defaults): the
offline tuning track needs to tune and ablate these *as a set*, which is
impossible when they are spread across call sites.

Bump ``CONFIG_VERSION`` whenever a field is added, removed or its default
changes, so run records made under different settings stay comparable.
"""

from dataclasses import dataclass, replace
from typing import Any, Dict

CONFIG_VERSION = "4"


@dataclass(frozen=True)
class GeorefConfig:
    """All georeferencing hyperparameters, in one place."""

    version: str = CONFIG_VERSION

    # --- Coastline snapping (current §7) -------------------------------------
    # Kept as-is for now. Roadmap §4.3 turns this off once chamfer alignment
    # lands, because blind snapping fights the alignment.
    snap_to_coastline: bool = True
    coastline_snap_ratio_of_diagonal: float = 0.01
    coastline_snap_fallback_px: float = 8.0
    coastline_snap_min_px: float = 3.0
    coastline_snap_max_px: float = 40.0
    coastline_snap_min_m: float = 200.0
    coastline_snap_max_m: float = 50_000.0

    # --- Land clipping (current §8) ------------------------------------------
    clip_to_land_mask: bool = True
    land_coverage_threshold: float = 0.01

    # --- Reference rasters (Step 2) ------------------------------------------
    # Matches the existing find_coastline_keypoints defaults. At a ~2500 km
    # framing box this is ~2.5 km/px, two orders of magnitude below the expected
    # accuracy floor, so resolution is not a precision constraint here.
    reference_raster_width: int = 1024
    reference_raster_height: int = 768

    # --- User-side evidence (Step 3) -----------------------------------------
    # Canny thresholds match the existing coastline keypoint finder.
    edge_blur_ksize: int = 5
    edge_canny_low: int = 75
    edge_canny_high: int = 175
    # Canny fires outside a glyph as readily as inside, so a mask tight to the
    # OCR box still leaves a rectangle of edges around every label.
    text_mask_dilation_px: int = 7

    # Straight-line suppression. The length threshold is a fraction of the image
    # diagonal so it means the same thing at any scan resolution.
    straight_line_min_length_ratio: float = 0.15
    straight_line_hough_threshold: int = 80
    straight_line_max_gap_px: int = 8
    straight_line_thickness_px: int = 3
    # Down-weighted, not deleted: a real coast can run straight for a while, and
    # a neatline sitting on a coast should not take the coast with it.
    straight_line_weight: float = 0.15

    # Water mask from the water pipette. Same colour metric as zone extraction.
    water_delta_e: float = 12.0
    water_morph_radius_px: int = 2
    water_min_component_px: int = 200

    # --- Alignment (Step 4) --------------------------------------------------
    # Off by default: turning it on is the experiment, not the baseline.
    enable_curve_alignment: bool = False

    # Reference curve sampling, per stage. Alignment runs coastline-first and
    # only then admits lakes: coastline is the most distinctive structure on a
    # map and the one most likely to be drawn faithfully, so it should set the
    # transform before anything finer is allowed to pull on it.
    curve_sample_spacing_px: float = 2.0
    curve_max_samples: int = 8000
    # Rivers are loaded and rasterized but **not used as alignment evidence**.
    # They contribute a lot of thin, dense linework that is often drawn
    # schematically or omitted entirely, so on a real map most of it matches
    # nothing a reader would recognise. Set true to put them back in.
    use_rivers_for_alignment: bool = False
    use_lakes_for_alignment: bool = True

    # Term balance. Both terms are normalised by their own sample count first,
    # so these are true relative weights and not an artifact of there being
    # thousands of curve samples and seven control points.
    weight_gcp: float = 1.0
    weight_curve: float = 1.0

    # A suppressed edge should act as if it were further away, not vanish:
    # D = min(D_strong, D_weak + penalty).
    straight_line_distance_penalty_px: float = 25.0

    # Annealing. One entry per level, coarse to fine: the distance field is
    # blurred by `sigma`, and Tukey rejects beyond `cutoff` pixels.
    #
    # Stage 1 is coastline-only and starts very wide on purpose. If the GCP-only
    # affine leaves the map a hundred-odd pixels out, a 16 px blur and a 120 px
    # cutoff cannot see the true coast at all, the fit does not move, and every
    # sanity gate then passes because nothing changed -- success indistinguishable
    # from never having engaged. Starting at 64 px of blur and a 400 px cutoff
    # gives the basin of attraction somewhere to attract from.
    coarse_blur_px: tuple = (64.0, 40.0, 24.0, 14.0)
    coarse_cutoff_px: tuple = (400.0, 260.0, 170.0, 110.0)
    # Stage 2 admits lakes and sharpens.
    anneal_blur_px: tuple = (8.0, 4.0, 2.0, 0.0)
    anneal_cutoff_px: tuple = (70.0, 45.0, 28.0, 18.0)
    max_iterations_per_level: int = 60

    # Normal-search ICP.
    enable_icp: bool = True
    icp_iterations: int = 8
    icp_search_radius_px: tuple = (40.0, 30.0, 22.0, 16.0, 12.0, 9.0, 7.0, 5.0)
    icp_orientation_tolerance_deg: float = 30.0
    icp_cutoff_px: float = 20.0
    icp_min_correspondences: int = 50

    # Gates (section 8.3).
    gate_probe_gcp_ratio: float = 2.0
    gate_probe_gcp_max_km: float = 150.0
    gate_water_iou_min: float = 0.7
    gate_max_scale_drift: float = 0.25
    gate_max_rotation_deg: float = 15.0
    gate_min_inlier_fraction: float = 0.2
    # Did the curve term actually engage? A fit that never moved passes every
    # sanity check, because nothing drifted. This is a *convergence* check, not
    # a correctness one -- a low chamfer residual still proves nothing, which is
    # why residual magnitude is never a gate.
    gate_min_chamfer_improvement: float = 0.02

    # Recovery ladder (section 10.2).
    recovery_multistart_translation_px: float = 40.0
    recovery_multistart_rotation_deg: float = 4.0
    recovery_multistart_scale: float = 0.06
    recovery_gcp_weight_boost: float = 8.0

    def to_dict(self) -> Dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}

    def with_overrides(self, **overrides: Any) -> "GeorefConfig":
        """Return a copy with *overrides* applied, ignoring None values."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean) if clean else self


DEFAULT_GEOREF_CONFIG = GeorefConfig()
