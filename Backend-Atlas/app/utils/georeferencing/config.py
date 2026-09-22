"""Frozen hyperparameters for the georeferencing pipeline.

Every tunable constant lives here as one versioned dataclass rather than as a
default scattered across a function signature. This deliberately deviates from
the surrounding style (``extract_colors`` carries ~10 inline defaults): the
offline tuning track needs to tune and ablate these *as a set*, which is
impossible when they are spread across call sites.

Bump ``CONFIG_VERSION`` whenever a field is added, removed or its default
changes, so run records made under different settings stay comparable.
"""

import math
from dataclasses import dataclass, replace
from typing import Any, Dict, Tuple

CONFIG_VERSION = "7"

#: The transform models a run may choose between, in increasing order of
#: freedom. Adding one here is not enough: ``pipeline`` has to know how to
#: build it, and a test holds the two lists together.
TRANSFORM_MODELS = ("affine", "piecewise_affine")


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

    # --- Transform model (roadmap §5.4) --------------------------------------
    # Which model places the map. One named choice rather than a flag per
    # model: the roadmap's candidate registry adds similarity, affine +
    # latitude stretch and FFD later, and a pile of mutually exclusive booleans
    # would let a caller ask for two at once.
    #
    # ``affine`` is the baseline. ``piecewise_affine`` keeps that affine and
    # adds a Delaunay correction pinned at each control point, decaying to zero
    # on a frame around the image so nothing extrapolates. The correction
    # interpolates rather than averages, so it reproduces a mis-clicked point
    # instead of smoothing it away: judge it by the leave-one-out error it
    # reports, never by its residual, which is 0 by construction.
    #
    # When Step 4 alignment supplies a model, this chooses what happens to it:
    # ``affine`` uses the aligned affine as-is, ``piecewise_affine`` corrects it.
    transform_model: str = "affine"
    # Frame padding as a fraction of the map's width and height. Wider means
    # the correction decays more gently and reaches further toward the edges.
    piecewise_anchor_margin: float = 0.25

    # --- Reference rasters (Step 2) ------------------------------------------
    # Matches the existing find_coastline_keypoints defaults. At a ~2500 km
    # framing box this is ~2.5 km/px, two orders of magnitude below the expected
    # accuracy floor, so resolution is not a precision constraint here.
    reference_raster_width: int = 1024
    reference_raster_height: int = 768

    # --- User-side evidence (Step 3) -----------------------------------------
    # Chosen by eye with scripts/edge_mask.py --sweep: blur 5 and 75/175 (the
    # coastline keypoint finder's values) dropped whole stretches of coast where
    # land and sea have similar grey levels. The extra interior linework this
    # admits is what the water filter below is for.
    edge_blur_ksize: int = 3
    edge_canny_low: int = 40
    edge_canny_high: int = 120
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

    # Keep only edges on the water/land boundary, when water was picked. An
    # edge counts if it lies within `margin` px of water *and* of non-water:
    # Canny can put the edge a pixel or two either side of the true boundary,
    # and anti-aliasing leaves a band that matches neither colour. Requiring
    # both sides also drops lines drawn across open water (graticules, routes).
    # Skipped when the water mask is too small to be trusted -- a stray pick on
    # a legend swatch would otherwise delete nearly every edge.
    edge_water_filter: bool = True
    edge_water_margin_px: int = 3
    edge_water_min_fraction: float = 0.01

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


#: The on/off switches the dev-test re-run button shows as checkboxes: settings
#: whose correct value depends on what you are looking at rather than on
#: tuning. Every other field is reachable too, through the tuning panel and
#: :func:`parse_config_overrides`; this set only decides which ones get a
#: first-class control and which go in the panel.
RUN_SWITCHES = frozenset(
    {
        # Blind snapping corrects transform error after the fact, so it both
        # flatters the baseline and hides alignment improvements (plan 8c).
        # Judging alignment means turning it off, per run, not per deployment.
        "snap_to_coastline",
        "enable_curve_alignment",
        "clip_to_land_mask",
    }
)


def parse_run_switches(raw: Any) -> Dict[str, bool]:
    """Coerce a caller-supplied switch map to known boolean fields.

    Unknown keys are dropped rather than raising: these arrive from a URL query
    and a stale frontend sending a retired switch should not fail the run. Only
    real booleans are accepted -- a string "false" is a classic way to silently
    turn a switch *on*, so it is rejected rather than guessed at.

    Raises:
        ValueError: if a known switch is given a non-boolean value, because
            that is a caller bug and silently ignoring it would run the map
            under settings the caller did not ask for.
    """
    if not isinstance(raw, dict):
        return {}

    switches: Dict[str, bool] = {}
    for key, value in raw.items():
        if key not in RUN_SWITCHES:
            continue
        if not isinstance(value, bool):
            raise ValueError(
                f"{key} must be a boolean, got {type(value).__name__}: {value!r}"
            )
        switches[key] = value
    return switches


#: The config's sections, in declaration order, so the dev tool can lay the
#: fields out the way this file reads. A test holds it to cover every field
#: exactly once: a field left out would be untunable from the UI, and nobody
#: would notice.
FIELD_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "Coastline snapping",
        (
            "snap_to_coastline",
            "coastline_snap_ratio_of_diagonal",
            "coastline_snap_fallback_px",
            "coastline_snap_min_px",
            "coastline_snap_max_px",
            "coastline_snap_min_m",
            "coastline_snap_max_m",
        ),
    ),
    ("Land clipping", ("clip_to_land_mask", "land_coverage_threshold")),
    ("Transform model", ("transform_model", "piecewise_anchor_margin")),
    ("Reference rasters", ("reference_raster_width", "reference_raster_height")),
    (
        "Edge detection",
        (
            "edge_blur_ksize",
            "edge_canny_low",
            "edge_canny_high",
            "text_mask_dilation_px",
        ),
    ),
    (
        "Straight-line suppression",
        (
            "straight_line_min_length_ratio",
            "straight_line_hough_threshold",
            "straight_line_max_gap_px",
            "straight_line_thickness_px",
            "straight_line_weight",
        ),
    ),
    (
        "Water",
        (
            "water_delta_e",
            "water_morph_radius_px",
            "water_min_component_px",
            "edge_water_filter",
            "edge_water_margin_px",
            "edge_water_min_fraction",
        ),
    ),
    (
        "Alignment",
        (
            "enable_curve_alignment",
            "curve_sample_spacing_px",
            "curve_max_samples",
            "use_rivers_for_alignment",
            "use_lakes_for_alignment",
            "weight_gcp",
            "weight_curve",
            "straight_line_distance_penalty_px",
        ),
    ),
    (
        "Annealing",
        (
            "coarse_blur_px",
            "coarse_cutoff_px",
            "anneal_blur_px",
            "anneal_cutoff_px",
            "max_iterations_per_level",
        ),
    ),
    (
        "ICP",
        (
            "enable_icp",
            "icp_iterations",
            "icp_search_radius_px",
            "icp_orientation_tolerance_deg",
            "icp_cutoff_px",
            "icp_min_correspondences",
        ),
    ),
    (
        "Gates",
        (
            "gate_probe_gcp_ratio",
            "gate_probe_gcp_max_km",
            "gate_water_iou_min",
            "gate_max_scale_drift",
            "gate_max_rotation_deg",
            "gate_min_inlier_fraction",
            "gate_min_chamfer_improvement",
        ),
    ),
    (
        "Recovery ladder",
        (
            "recovery_multistart_translation_px",
            "recovery_multistart_rotation_deg",
            "recovery_multistart_scale",
            "recovery_gcp_weight_boost",
        ),
    ),
)

#: Never overridable: it labels which *code* produced a run, not a setting.
_NOT_OVERRIDABLE = frozenset({"version"})

#: Fields whose value comes from a fixed list. A free-text setting would be a
#: typo away from silently running something other than what was asked for, so
#: these are validated against the list and offered as a dropdown by the UI.
FIELD_CHOICES: Dict[str, Tuple[str, ...]] = {
    "transform_model": TRANSFORM_MODELS,
}


def _coerce_field(key: str, value: Any, default: Any) -> Any:
    """Coerce one override to the type of *default*, or raise ValueError.

    The type comes from the default rather than an annotation, so a field
    added to the dataclass is tunable with no change here.
    """
    def _number(v: Any) -> float:
        # bool is an int subclass; True as a threshold is always a caller bug.
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{key} must be a number, got {type(v).__name__}: {v!r}")
        if not math.isfinite(v):
            raise ValueError(f"{key} must be finite, got {v!r}")
        return float(v)

    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError(
                f"{key} must be a boolean, got {type(value).__name__}: {value!r}"
            )
        return value

    if isinstance(default, str):
        choices = FIELD_CHOICES.get(key)
        if not isinstance(value, str) or (choices and value not in choices):
            raise ValueError(
                f"{key} must be one of {list(choices or ())}, got {value!r}"
            )
        return value

    if isinstance(default, int):
        number = _number(value)
        if not number.is_integer():
            raise ValueError(f"{key} must be an integer, got {value!r}")
        return int(number)

    if isinstance(default, float):
        return _number(value)

    if isinstance(default, tuple):
        # JSON has no tuple, so a schedule arrives as a list. Length is free:
        # a schedule is one entry per annealing level, and adding or dropping a
        # level is a legitimate thing to try.
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError(f"{key} must be a non-empty list of numbers, got {value!r}")
        return tuple(_number(v) for v in value)

    raise ValueError(f"{key} has an unsupported type {type(default).__name__}")


def parse_config_overrides(raw: Any) -> Dict[str, Any]:
    """Coerce a caller-supplied override map to typed config fields.

    The dev tool's tuning panel: unlike :func:`parse_run_switches`, this admits
    *every* field, because its whole purpose is to try thresholds without
    editing this file. Overrides live only in the run's config copy; nothing
    here can reach the worker's ambient settings.

    Unknown keys are dropped, for the same stale-frontend reason as the
    switches. A known key with a value of the wrong type raises, because a
    guessed conversion would run the map under settings nobody asked for.
    """
    if not isinstance(raw, dict):
        return {}

    fields = GeorefConfig.__dataclass_fields__
    overrides: Dict[str, Any] = {}
    for key, value in raw.items():
        if key not in fields or key in _NOT_OVERRIDABLE:
            continue
        overrides[key] = _coerce_field(key, value, getattr(DEFAULT_GEOREF_CONFIG, key))
    return overrides


def describe_config(ambient: GeorefConfig) -> Dict[str, Any]:
    """What the dev tool needs to render the tuning panel.

    ``values`` is the *ambient* config -- the file defaults with the worker's
    environment applied -- because that is what a run uses when nothing is
    overridden, and so what an edit should be compared against.
    """
    return {
        "version": ambient.version,
        "values": ambient.to_dict(),
        "fileDefaults": DEFAULT_GEOREF_CONFIG.to_dict(),
        "groups": [{"title": title, "fields": list(names)} for title, names in FIELD_GROUPS],
        "switches": sorted(RUN_SWITCHES),
        "choices": {field: list(options) for field, options in FIELD_CHOICES.items()},
    }
