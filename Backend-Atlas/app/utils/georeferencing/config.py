"""Every georeferencing and zone-extraction parameter, in one place."""

import math
import os
from dataclasses import dataclass, replace
from typing import Any, Dict, Tuple

CONFIG_VERSION = "23"

#: In increasing order of freedom, then ``auto``, which picks one per map.
#: ``pipeline`` has to know how to build each; a test holds the two together.
TRANSFORM_MODELS = ("affine", "piecewise_affine", "auto")

#: How far the piecewise correction may reach; see ``piecewise_regularization``.
PIECEWISE_REGULARIZATIONS = ("none", "local")

#: Where a control point came from. ``sift``: the user matched a suggested
#: coastline keypoint. ``city``: the user picked a gazetteer city and clicked
#: where the map draws it.
SOURCE_SIFT = "sift"
SOURCE_CITY = "city"
GCP_SOURCES = (SOURCE_SIFT, SOURCE_CITY)


@dataclass(frozen=True)
class GeorefConfig:
    """All georeferencing hyperparameters, in one place."""

    version: str = CONFIG_VERSION

    # --- Control points ------------------------------------------------------
    # Which sources a run fits from. Applied where the task reads the points,
    # so every later step sees the same set.
    gcp_sources: tuple = GCP_SOURCES
    # Expected click error per source, in pixels. Only the ratio matters (the
    # GCP term weights by (median/sigma)^2). Equal until residuals show one
    # source is noisier. Before making them differ, normalise the GCP term by
    # the sum of the weights rather than the point count, or its strength
    # against the coastline will shift with the mix of sources.
    gcp_sigma_px_sift: float = 6.0
    gcp_sigma_px_city: float = 6.0

    # --- Coastline snapping (georeferencing.md section 6) -------------------
    # Hides placement error, so placement is scored before it (the raw score).
    # On because it improves the shipped zones.
    snap_to_coastline: bool = True
    # Tolerance as a share of the image diagonal, converted to metres with the
    # transform's scale.
    coastline_snap_ratio_of_diagonal: float = 0.015
    # That tolerance runs to 35-220 km on the corpus and moves half the
    # boundary vertices or more, inland borders near the sea with them
    # (georeferencing-synthetic.md §10.8). Measured: the tolerance is this
    # many times how far the reference coast sits from the drawn edges under
    # the applied transform (the trimmed chamfer), at least the floor, at
    # most the ratio above. Off, or with no alignment evidence: the ratio.
    # The misfit is ~1 px on most real maps, so the floor decides there: 5 px
    # costs nothing on synthetic maps and gains on real ones, whose drawn
    # coasts stray further from the reference; 8 px and more cost on
    # synthetic ones (§10.9). Pixels, not a share of the map: open.
    coastline_snap_measured: bool = True
    coastline_snap_misfit_factor: float = 3.0
    coastline_snap_min_px: float = 5.0
    # Stretches: only a run of consecutive boundary vertices near the coast
    # and along it is snapped, and onto the coast's own vertices between them
    # rather than in chords. A run shorter than this, or the run's ends where
    # the boundary leaves the coast at more than the angle, are left as they
    # are. A polygon whose snap would change more than this share of its
    # area is left as it is (a zone narrower than the tolerance folds onto
    # the coast). Off: every vertex within the tolerance moves to its nearest
    # point. With both on, snapping costs more than 0.01 IoU on 2 of 196
    # synthetic cases and on no real one (old snapping: 53 and 4, §10.8).
    coastline_snap_stretches: bool = True
    coastline_snap_min_run_px: float = 20.0
    coastline_snap_max_angle_deg: float = 45.0
    coastline_snap_max_area_change: float = 0.25

    # --- Land clipping (georeferencing.md section 6) -------------------------
    clip_to_land_mask: bool = True
    land_coverage_threshold: float = 0.01

    # --- Zone extraction ------------------------------------------------------
    # Upstream of georeferencing, but it changes the zones every metric is
    # computed on, so a run records it here.
    #
    # Label ink is erased before classification: each ink pixel takes the
    # colour most voted by its neighbours from the palette of the ring around
    # its OCR box, so a name over a zone comes back as that zone. Needs OCR
    # boxes. Repairing the zones after classification instead ("label") and
    # cv2.inpaint (Telea) both lost to this and were removed.
    text_aware_zone_fill: bool = True
    # Pixels added around the ink, for the anti-aliased fringe.
    text_inpaint_dilation_px: int = 1
    # A box whose ink covers more than this share of it is left alone.
    text_inpaint_max_ink_ratio: float = 1
    # How far (ΔE2000) from every ring colour a pixel must be to count as ink.
    # Lower catches more fringe, and more genuine texture with it.
    text_inpaint_ink_deltaE: float = 12.0
    # Grow zones into the unassigned strip a drawn border leaves between two
    # *different* zones (not into the sea or a lake), and vectorise all zones
    # together so neighbours share one edge. Off: worse in its current form.
    zone_gap_fill: bool = False
    # Widest gap closed, as a share of the image diagonal: a line, not a strait.
    zone_gap_max_ratio_of_diagonal: float = 0.008

    # --- Transform model (georeferencing.md section 5.3) ---------------------
    # ``affine``: the baseline (or the aligned affine, after Step 4).
    # ``piecewise_affine``: that affine plus a Delaunay correction pinned at
    # each control point, fading to zero on a frame around the image. It
    # reproduces a mis-clicked point rather than smoothing it, so judge it by
    # its leave-one-out error; its residual is 0 by construction.
    # ``auto``: piecewise only when the affine's GCP RMS exceeds the threshold
    # below (with 3 points the affine is exact, so it stays affine).
    #
    # Piecewise between two alignments (B7b, 2026-10-08) was production until
    # config v22. Now the aligned affine is bent to the coast instead
    # (``coast_bend``), and the piecewise step only runs where the bend
    # refuses (``coast_bend_fallback_piecewise``): W13 on synthetic and real
    # maps, georeferencing-synthetic.md §10.6-10.9.
    transform_model: str = "affine"
    # Affine GCP RMS as a share of the image diagonal. Not measured yet.
    auto_piecewise_rmse_ratio_of_diagonal: float = 0.01
    # Frame padding, as a fraction of the map's size. Wider: gentler decay.
    piecewise_anchor_margin: float = 0.25
    # Longest segment before a piecewise warp, as a share of the diagonal: only
    # vertices are warped, so longer edges would not bend with the triangles.
    piecewise_densify_ratio_of_diagonal: float = 0.01
    # ``none``: a correction reaches across every triangle the point is a
    # corner of, so empty regions are pulled by distant points. ``local``:
    # zero-correction anchors wherever the nearest point is over the radius
    # below away, so those regions keep the affine. ``local`` won (B3L vs B3).
    piecewise_regularization: str = "local"
    # The ``local`` reach and anchor spacing, as a share of the diagonal. The
    # most even of 0.1 / 0.175 / 0.25; 0.25 is about ``none``.
    piecewise_influence_radius_ratio_of_diagonal: float = 0.175

    # --- Reference rasters (Step 2) ------------------------------------------
    # ~2.5 km/px on a ~2500 km frame: far finer than the accuracy we can reach.
    reference_raster_width: int = 1024
    reference_raster_height: int = 768

    # --- User-side evidence (Step 3) -----------------------------------------
    # Chosen with scripts/edge_mask.py --sweep: stronger settings dropped coast
    # where land and sea have similar grey levels. The water filter below
    # removes the extra interior lines these let through.
    edge_blur_ksize: int = 3
    edge_canny_low: int = 40
    edge_canny_high: int = 120
    # Canny fires just outside glyphs too, so the OCR box mask is grown.
    text_mask_dilation_px: int = 7

    # Straight-line suppression. Length is a share of the diagonal.
    straight_line_min_length_ratio: float = 0.15
    straight_line_hough_threshold: int = 80
    straight_line_max_gap_px: int = 8
    straight_line_thickness_px: int = 3
    # Down-weighted, not deleted: a real coast can run straight for a while.
    straight_line_weight: float = 0.15

    # Water mask from the water pipette, same colour metric as zone extraction.
    water_delta_e: float = 12.0
    water_morph_radius_px: int = 2
    water_min_component_px: int = 200

    # Keep only edges within `margin` px of both water and non-water: the
    # map's coastline. Also drops lines drawn across open water. Off only to
    # measure what the filter is worth.
    edge_water_filter: bool = True
    edge_water_margin_px: int = 3
    # A coast drawn as a line: each kept edge is paired with the line's other
    # flank, up to this far landward (px), and the evidence moved to their
    # midpoint, the line's centre (evidence.centre_drawn_coast_lines). Covers
    # lines up to ~5 px wide plus Canny's spread. 0 keeps the sea-side flank,
    # which biased the fit by half the line's width (before config v21).
    coast_line_max_width_px: int = 8
    # Below this share of the image, the water mask is more likely a stray pick
    # than the sea, and alignment is skipped.
    edge_water_min_fraction: float = 0.01

    # --- Alignment (Step 4) --------------------------------------------------
    # Lowered check-point error on 11 of 12 corpus cases, worsened none
    # (georeferencing-testing.md 8.3).
    enable_curve_alignment: bool = True
    # Align again after the piecewise correction, as an affine in front of it
    # (post_align.py), kept only if the coastline chamfer does not get worse.
    # Without a piecewise model the GCP affine is aligned instead. A gain on
    # the corpus (B7 vs B3Lb, 2026-10-08). Off since config v22: with the
    # affine as the model there is nothing to align again, and the bend's
    # fallback runs this alignment after its own piecewise step.
    align_after_piecewise: bool = False
    # The second alignment starts on the clicks (the piecewise step pins
    # them), so it may only pull them this far off, RMS over the diagonal.
    # Synthetic runs pulled them at most 0.013 (0.0085 at p99), the real
    # corpus 6 px; the one front past 0.02 sheared a map from 20 to 94 km
    # (georeferencing-synthetic.md §10.12). Since config v23.
    post_align_max_gcp_shift_ratio_of_diagonal: float = 0.02

    # Bend the map to its coast after the alignments (bend.py), a smooth
    # correction in pixels: Gaussians on a grid of knots, fitted by ridge to
    # the coast's normal-search correspondences and the control points. The
    # bound it was built from is georeferencing-synthetic.md §10.4.
    coast_bend: bool = True
    coast_bend_knots_across: int = 6
    # Against the observations' mean squared px, weights summing to 1. Stiffer
    # than the ceiling's best (1e-4): real correspondences are noisy, and at
    # 1e-4 the bend tilted maps that were already right (10 maps, 2026-10-29).
    # 3e-3 was the best fixed ridge of the sweep with no piecewise step under
    # the bend (W7, §10.5).
    coast_bend_ridge: float = 3e-3
    # The same on the correction's affine part. Near 0 lets the bend take out
    # what alignment left of the affine; at the ridge it is safer on maps
    # without a bend but keeps little of the gain on the bent ones.
    coast_bend_affine_ridge: float = 1e-8
    # Each observation is weighted by 1/σ², a coast match counting as the
    # share of an independent one its spacing is of the correlation length,
    # so the balance follows how many control points and how much coast a map
    # has; the weights then sum to 1, so the ridges keep their scale. Better
    # than a fixed share of 0.9 on every twin, and more weight on the control
    # points made the bend refuse itself (georeferencing-synthetic.md §10.5).
    coast_bend_gcp_sigma_px: float = 4.0
    coast_bend_coast_sigma_px: float = 2.0
    coast_bend_coast_correlation_px: float = 20.0
    # One search per entry, as ICP's.
    coast_bend_search_radius_px: tuple = (40.0, 30.0, 22.0, 16.0, 12.0, 9.0, 7.0, 5.0)
    # Refused past this correction anywhere on the image.
    coast_bend_max_ratio_of_diagonal: float = 0.10
    # After the bend, a local correction at the control points this far
    # from the reference coast (share of the diagonal): what the coast
    # cannot show and only the piecewise step followed (§10.6). Each
    # point's pull fades out over the radius, the piecewise step's reach.
    coast_bend_inland: bool = False
    coast_bend_inland_min_ratio_of_diagonal: float = 0.05
    coast_bend_inland_radius_ratio_of_diagonal: float = 0.15
    # Where the bend refuses and no piecewise step ran (``transform_model``
    # affine), run it then, as PROD does: the piecewise step, then the
    # second alignment. The inland correction is skipped, since the
    # piecewise step pins every control point (§10.6).
    coast_bend_fallback_piecewise: bool = True

    # Reference curve sampling. Coastline sets the transform first; lakes are
    # admitted in the fine stage.
    curve_sample_spacing_px: float = 2.0
    curve_max_samples: int = 8000
    use_lakes_for_alignment: bool = True

    # Relative weights: each term is normalised by its own sample count. The
    # gain grows up to x30 and stops (georeferencing-testing.md 8.1-8.2); x10
    # takes most of it and leaves the control points more say inland. It holds
    # with the piecewise step and the second alignment (B7a/b).
    weight_gcp: float = 1.0
    weight_curve: float = 10.0

    # A suppressed edge acts as further away, not absent:
    # D = min(D_strong, D_weak + penalty).
    straight_line_distance_penalty_px: float = 25.0

    # Annealing, one entry per level, coarse to fine: the distance field is
    # blurred by `blur`, and Tukey rejects beyond `cutoff` px. The coastline
    # stage starts very wide so a map placed a hundred-odd px out can still
    # see the coast; otherwise the fit never moves and every gate passes.
    coarse_blur_px: tuple = (64.0, 40.0, 24.0, 14.0)
    coarse_cutoff_px: tuple = (400.0, 260.0, 170.0, 110.0)
    # The fine stage admits lakes and sharpens.
    anneal_blur_px: tuple = (8.0, 4.0, 2.0, 0.0)
    anneal_cutoff_px: tuple = (70.0, 45.0, 28.0, 18.0)
    max_iterations_per_level: int = 60

    # Off leaves ICP alone, from the control-point affine.
    enable_chamfer: bool = True

    # Normal-search ICP. Wider values (100 px, 60 degrees) only compensated
    # for since-fixed bugs, and 60 degrees lets crossing lines through.
    enable_icp: bool = True
    icp_iterations: int = 8
    icp_search_radius_px: tuple = (40.0, 30.0, 22.0, 16.0, 12.0, 9.0, 7.0, 5.0)
    icp_orientation_tolerance_deg: float = 30.0
    icp_cutoff_px: float = 20.0
    icp_min_correspondences: int = 50

    # Gates (georeferencing.md section 5.2): any failure falls back to the
    # control-point affine. Lenient: they catch an absurd fit, not a small
    # move. A mirrored transform always fails.
    #
    # Minimum coastline chamfer improvement; at 0, fails only if it got worse.
    gate_min_chamfer_improvement: float = 0.0
    # Allowed drop in water IoU against the control-point affine. Corpus
    # aligned water IoU ran 0.72-0.89 at x10.
    gate_water_iou_max_drop: float = 0.10
    # Allowed rise in control-point RMS, as a share of the diagonal. Corpus
    # rises were +0.4 to +3.6 px at x10.
    gate_max_gcp_shift_ratio_of_diagonal: float = 0.05

    def to_dict(self) -> Dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}

    def with_overrides(self, **overrides: Any) -> "GeorefConfig":
        """Return a copy with *overrides* applied, ignoring None values."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean) if clean else self


DEFAULT_GEOREF_CONFIG = GeorefConfig()


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def ambient_georef_config() -> GeorefConfig:
    """The defaults above with the deployment's environment applied.

    The one reader, so the Celery tasks and the dev script agree on what an
    unswitched run is, which decides whether a run may become a dev-test
    case's best.
    """
    return DEFAULT_GEOREF_CONFIG.with_overrides(
        snap_to_coastline=_env_flag(
            "GEOREF_ENABLE_COASTLINE_SNAPPING", DEFAULT_GEOREF_CONFIG.snap_to_coastline
        ),
        enable_curve_alignment=_env_flag(
            "GEOREF_ENABLE_CURVE_ALIGNMENT", DEFAULT_GEOREF_CONFIG.enable_curve_alignment
        ),
    )


#: The switches the dev-test re-run button shows as checkboxes. Every other
#: field is still tunable through the tuning panel.
RUN_SWITCHES = frozenset(
    {
        # Snapping hides alignment error, so judging alignment means turning
        # it off per run.
        "snap_to_coastline",
        "enable_curve_alignment",
        "clip_to_land_mask",
    }
)


#: The config's sections, in declaration order, for the dev tool's layout. A
#: test holds it to cover every field exactly once.
FIELD_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "Control points",
        ("gcp_sources", "gcp_sigma_px_sift", "gcp_sigma_px_city"),
    ),
    (
        "Coastline snapping",
        (
            "snap_to_coastline",
            "coastline_snap_ratio_of_diagonal",
            "coastline_snap_measured",
            "coastline_snap_misfit_factor",
            "coastline_snap_min_px",
            "coastline_snap_stretches",
            "coastline_snap_min_run_px",
            "coastline_snap_max_angle_deg",
            "coastline_snap_max_area_change",
        ),
    ),
    ("Land clipping", ("clip_to_land_mask", "land_coverage_threshold")),
    (
        "Zone extraction",
        (
            "text_aware_zone_fill",
            "text_inpaint_ink_deltaE",
            "zone_gap_fill",
            "zone_gap_max_ratio_of_diagonal",
            "text_inpaint_dilation_px",
            "text_inpaint_max_ink_ratio",
        ),
    ),
    (
        "Transform model",
        (
            "transform_model",
            "auto_piecewise_rmse_ratio_of_diagonal",
            "piecewise_anchor_margin",
            "piecewise_densify_ratio_of_diagonal",
            "piecewise_regularization",
            "piecewise_influence_radius_ratio_of_diagonal",
        ),
    ),
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
            "coast_line_max_width_px",
            "edge_water_min_fraction",
        ),
    ),
    (
        "Alignment",
        (
            "enable_curve_alignment",
            "align_after_piecewise",
            "post_align_max_gcp_shift_ratio_of_diagonal",
            "coast_bend",
            "coast_bend_knots_across",
            "coast_bend_ridge",
            "coast_bend_affine_ridge",
            "coast_bend_gcp_sigma_px",
            "coast_bend_coast_sigma_px",
            "coast_bend_coast_correlation_px",
            "coast_bend_search_radius_px",
            "coast_bend_max_ratio_of_diagonal",
            "coast_bend_inland",
            "coast_bend_inland_min_ratio_of_diagonal",
            "coast_bend_inland_radius_ratio_of_diagonal",
            "coast_bend_fallback_piecewise",
            "curve_sample_spacing_px",
            "curve_max_samples",
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
            "enable_chamfer",
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
            "gate_min_chamfer_improvement",
            "gate_water_iou_max_drop",
            "gate_max_gcp_shift_ratio_of_diagonal",
        ),
    ),
)

#: It labels which code produced a run, not a setting.
_NOT_OVERRIDABLE = frozenset({"version"})

#: Fields validated against a fixed list, offered as a dropdown.
FIELD_CHOICES: Dict[str, Tuple[str, ...]] = {
    "transform_model": TRANSFORM_MODELS,
    "piecewise_regularization": PIECEWISE_REGULARIZATIONS,
}

#: Fields holding a non-empty subset of a fixed list, offered as checkboxes.
#: Stored in the list's order, so the same subset always compares equal.
FIELD_MULTI_CHOICES: Dict[str, Tuple[str, ...]] = {
    "gcp_sources": GCP_SOURCES,
}


def _coerce_field(key: str, value: Any, default: Any) -> Any:
    """Coerce one override to the type of *default*, or raise ValueError.

    The type comes from the default, so a new field is tunable with no change
    here.
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

    multi = FIELD_MULTI_CHOICES.get(key)
    if multi is not None:
        if (
            not isinstance(value, (list, tuple))
            or not value
            or not all(isinstance(v, str) and v in multi for v in value)
            or len(set(value)) != len(value)
        ):
            raise ValueError(
                f"{key} must be a non-empty list of distinct values from"
                f" {list(multi)}, got {value!r}"
            )
        return tuple(v for v in multi if v in value)

    if isinstance(default, tuple):
        # JSON has no tuple, so a schedule arrives as a list. Any length: one
        # entry per annealing level, and changing the level count is fair game.
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError(f"{key} must be a non-empty list of numbers, got {value!r}")
        return tuple(_number(v) for v in value)

    raise ValueError(f"{key} has an unsupported type {type(default).__name__}")


def parse_config_overrides(raw: Any) -> Dict[str, Any]:
    """Coerce a caller-supplied override map to typed config fields.

    For the dev tool's tuning panel, so every field is admitted. Overrides
    apply to the run's config copy only, never the worker's ambient settings.

    Unknown keys are dropped, so a stale frontend sending a retired field does
    not fail the run. A known key with the wrong type raises rather than being
    guessed at.
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

    ``values`` is the ambient config (file defaults plus the worker's
    environment): what a run uses when nothing is overridden.
    """
    return {
        "version": ambient.version,
        "values": ambient.to_dict(),
        "fileDefaults": DEFAULT_GEOREF_CONFIG.to_dict(),
        "groups": [{"title": title, "fields": list(names)} for title, names in FIELD_GROUPS],
        "switches": sorted(RUN_SWITCHES),
        "choices": {field: list(options) for field, options in FIELD_CHOICES.items()},
        "multiChoices": {
            field: list(options) for field, options in FIELD_MULTI_CHOICES.items()
        },
    }
