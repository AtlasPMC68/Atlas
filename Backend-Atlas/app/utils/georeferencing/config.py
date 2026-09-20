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

CONFIG_VERSION = "2"


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

    def to_dict(self) -> Dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}

    def with_overrides(self, **overrides: Any) -> "GeorefConfig":
        """Return a copy with *overrides* applied, ignoring None values."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean) if clean else self


DEFAULT_GEOREF_CONFIG = GeorefConfig()
