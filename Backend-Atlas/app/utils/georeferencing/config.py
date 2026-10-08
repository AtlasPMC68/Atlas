# This file contains all the necessary parameters for the georeferencing and color extraction

import math
import os
from dataclasses import dataclass, replace
from typing import Any, Dict, Tuple

CONFIG_VERSION = "20"

#: The transform models a run may choose between, in increasing order of
#: freedom, then ``auto``, which picks one of them per map. Adding one here is
#: not enough: ``pipeline`` has to know how to build it, and a test holds the
#: two lists together.
TRANSFORM_MODELS = ("affine", "piecewise_affine", "auto")

#: How far the piecewise correction may reach; see ``piecewise_regularization``.
PIECEWISE_REGULARIZATIONS = ("none", "local")

#: How label ink is found and repainted before classification; see
#: `color_extraction`. Not imported from there so the config stays free of the
#: image stack.
TEXT_INPAINT_ALGOS = ("palette", "telea")

#: Where a control point came from. ``sift``: the user matched a suggested
#: coastline keypoint to their map. ``city``: the user named a city their map
#: shows, picked it from the gazetteer, and clicked where the map draws it.
SOURCE_SIFT = "sift"
SOURCE_CITY = "city"
GCP_SOURCES = (SOURCE_SIFT, SOURCE_CITY)


@dataclass(frozen=True)
class GeorefConfig:
    """All georeferencing hyperparameters, in one place."""

    version: str = CONFIG_VERSION

    # --- Control points ------------------------------------------------------
    # Which sources a run fits from. All of them by default; the dev tool
    # unticks one to see what the other carries on its own, from the same
    # clicks. Applied once, where the task reads the points, so the baseline,
    # the alignment, the gates and the piecewise correction all see one set.
    gcp_sources: tuple = GCP_SOURCES
    # Expected positional error per source, in image pixels. Only the ratio
    # matters: the alignment GCP term weights each point by (median/sigma)^2,
    # and the GCP-only baseline is unweighted. Equal on purpose -- a SIFT point
    # is a user matching an abstract coastline shape, a city is a named dot the
    # map may place wrongly, and which is noisier is for residuals to say, not
    # for a constant to assume. Kept per source so it can be set from them.
    #
    # Before making these differ: the GCP term is normalised by point count
    # and median sigma, so its total strength against the coastline term would
    # then shift with the mix of sources. Normalise by the sum of the weights
    # instead at the same time (identical while the sigmas are equal).
    gcp_sigma_px_sift: float = 6.0
    gcp_sigma_px_city: float = 6.0

    # --- Coastline snapping (georeferencing.md section 6) -------------------
    # A cleaning step. It hides placement error, so placement is judged before
    # it (the raw score); it improves the shipped zones, so it stays on.
    snap_to_coastline: bool = True
    # Snap tolerance = this share of the image diagonal, converted to metres
    # with the transform's scale. The only knob: no pixel or metre clamps.
    coastline_snap_ratio_of_diagonal: float = 0.015 # old value was : 0.01

    # --- Land clipping (georeferencing.md section 6) -------------------------
    clip_to_land_mask: bool = True
    land_coverage_threshold: float = 0.01

    # --- Zone extraction ------------------------------------------------------
    # Strictly upstream of georeferencing, and here anyway: it changes the
    # zones every metric is computed on, so a run has to record what it used,
    # and the dev tool has to be able to turn it off to compare.
    #
    # A place name is drawn *over* a zone, so its glyphs belong to that zone.
    # Nearest-colour assignment drops them and hole filling cannot get them
    # back -- on a real map the glyphs touch the rivers and borders, so the
    # gaps reach the image edge and are not holes at all. On by default: that
    # is a defect, not an experiment. Needs OCR boxes, so it does nothing when
    # none are available.
    #
    # The labels' ink is erased from the image before classification, so a
    # name written half over the sea comes back as sea on one side and land on
    # the other. A "label" method that repaired the zones after classification
    # instead was worse on every case of the first corpus run
    # (georeferencing-testing.md 8.3) and was removed.
    text_aware_zone_fill: bool = True
    # Pixels added around the detected ink, for the anti-aliased fringe whose
    # blended colour otherwise lands in the wrong zone.
    text_inpaint_dilation_px: int = 1
    # cv2.inpaint's neighbourhood radius.
    text_inpaint_radius_px: float = 3.0
    # A box whose "ink" covers more than this share of it did not split into
    # strokes and background, and is left alone.
    text_inpaint_max_ink_ratio: float = 1 # old value was 0.6
    # "palette": the background of each label is the palette of colours in the
    # ring around its box, ink is whatever is far from that palette, and each
    # ink pixel takes the colour most voted by its known neighbours -- never a
    # blend. "telea": the earlier Otsu split + cv2.inpaint (weighted mean);
    # the radius above only applies to it.
    text_inpaint_algo: str = "palette"
    # Palette mode: how far (ΔE2000) from every background colour of its box a
    # pixel must be to count as ink. Lower catches more of the anti-aliased
    # fringe, and more genuine texture with it.
    text_inpaint_ink_deltaE: float = 12.0
    # A border drawn between two zones matches neither colour, so both zones
    # stop short of it and a strip of nothing runs between them. On: every
    # zone grows at the same rate into unassigned pixels that sit in a narrow
    # gap between two *different* zones (a lake, the sea or a coast is left
    # alone), each pixel is settled on one zone, and all zones are vectorised
    # together so neighbours share one border. Off until compared.
    zone_gap_fill: bool = False
    # Widest gap closed, as a share of the image diagonal (0.008 is ~6 px on a
    # 600 px scan, ~40 px on a 5000 px one): a drawn line, not a strait.
    zone_gap_max_ratio_of_diagonal: float = 0.008

    # --- Transform model (georeferencing.md section 5.3) ---------------------
    # Which model places the map. One named choice rather than a flag per
    # model, so later models (a smoothed warp, roadmap section 3) slot in and a
    # caller cannot ask for two at once. The first corpus run did not support
    # plain piecewise as the default. The local piecewise below, between two
    # alignments at coastline weight 10 (variant B7b, 2026-10-08), did: best
    # mean before-cleaning IoU of every variant, 14 cases better than B2 and 3
    # worse, with its large gains on the maps placed worst. That is the
    # default now.
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
    #
    # ``auto`` measures the affine's RMS residual on the control points it was
    # fitted to (or, after Step 4, the aligned affine's). At or under the
    # threshold below, the affine is kept; over it, the piecewise correction is
    # applied. With exactly 3 points the affine is exact and its residual says
    # nothing, so ``auto`` keeps the affine. Not the default: B7b applies the
    # correction on every map. Kept as the switch to try when the losses on
    # maps the affine already fits (about 0.01 IoU, 2026-10-08) are worth
    # gating away.
    transform_model: str = "piecewise_affine"
    # The ``auto`` threshold: affine GCP RMS in image pixels, as a share of the
    # image diagonal, so one value means the same misfit on a small and a large
    # scan (0.01 is ~6 px on 512x256, ~23 px on 2048x1048). A first guess, not
    # measured: set it from corpus runs.
    auto_piecewise_rmse_ratio_of_diagonal: float = 0.01
    # Frame padding as a fraction of the map's width and height. Wider means
    # the correction decays more gently and reaches further toward the edges.
    piecewise_anchor_margin: float = 0.25
    # Longest segment kept before a piecewise warp, as a share of the image
    # diagonal. Only vertices are warped, so a longer straight edge would stay
    # straight across triangles the correction bends.
    piecewise_densify_ratio_of_diagonal: float = 0.01
    # ``none``: a point's correction reaches across every triangle it is a
    # corner of, so a region with no control point near it is pulled by a
    # blend of the corrections of points far away. ``local``: zero-correction
    # anchors fill the map wherever the nearest control point is at least the
    # radius below away, so each correction fades out within about that
    # distance and those regions keep the affine (or the aligned affine).
    # ``local`` beat ``none`` on top of alignment (B3La/b/c vs B3, 2026-10-08).
    piecewise_regularization: str = "local"
    # The ``local`` reach, as a share of the image diagonal (0.175 is ~125 px
    # on 600x400). Also the anchor grid's spacing. 0.175 was the most even of
    # 0.1 / 0.175 / 0.25 across maps (2026-10-08); 0.25 is about ``none``.
    piecewise_influence_radius_ratio_of_diagonal: float = 0.175

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

    # Keep only edges on the water/land boundary: this is what identifies the
    # map's coastline, and alignment never runs without it. An edge counts if
    # it lies within `margin` px of water *and* of non-water: Canny can put the
    # edge a pixel or two either side of the true boundary, and anti-aliasing
    # leaves a band that matches neither colour. Requiring both sides also
    # drops lines drawn across open water (graticules, routes). Off only as an
    # experiment, to measure what the filter is worth.
    edge_water_filter: bool = True
    edge_water_margin_px: int = 3
    # Alignment is skipped when the water mask covers less of the image than
    # this: a mask that small is more likely a stray pick (a legend swatch)
    # than the sea, and filtering on it would delete nearly every edge.
    edge_water_min_fraction: float = 0.01

    # --- Alignment (Step 4) --------------------------------------------------
    # On: production extraction aligns the map to the coastline. It lowered
    # check-point error on 11 of 12 corpus cases and worsened none
    # (georeferencing-testing.md 8.3). The regression suite and the dev
    # script run with it on too, so every number is the production one.
    enable_curve_alignment: bool = True
    # Run the alignment stages (coastline, fine, ICP) again *after* the
    # piecewise correction, as an affine in front of it (post_align.py), kept
    # only if the coastline chamfer does not get worse. Independent of the
    # switch above: with it, align -> piecewise -> align; without it,
    # piecewise -> align. Without a piecewise model (``auto`` kept the affine,
    # or the correction was refused) the GCP affine is aligned instead, and an
    # already aligned affine is left as it is. The second fit moves the map off
    # the clicks the piecewise model interpolates; on the corpus that was a
    # gain (B7 vs B3Lb, 2026-10-08), so it is on. With ``enable_curve_alignment``
    # on as well, this is B7b.
    align_after_piecewise: bool = True

    # Reference curve sampling, per stage. Alignment runs coastline-first and
    # only then admits lakes: coastline is the most distinctive structure on a
    # map and the one most likely to be drawn faithfully, so it should set the
    # transform before anything finer is allowed to pull on it.
    curve_sample_spacing_px: float = 2.0
    curve_max_samples: int = 8000
    use_lakes_for_alignment: bool = True

    # Term balance. Both terms are normalised by their own sample count first,
    # so these are true relative weights and not an artifact of there being
    # thousands of curve samples and seven control points.
    # The corpus run's weight sweep: the gain grows from x1 to x30 and stops
    # there, mostly at the coast (georeferencing-testing.md 8.1-8.2). x10 takes
    # most of it while leaving the control points more say than x30 inland.
    weight_gcp: float = 1.0
    # The gain from x1 to x3 to x10 holds with the piecewise step and the
    # second alignment too (B7a/b, 2026-10-08).
    weight_curve: float = 10.0

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

    # The two chamfer stages (coastline, then coastline + lakes). Off leaves
    # ICP alone, starting from the control-point affine: the ICP-only variant.
    enable_chamfer: bool = True

    # Normal-search ICP.
    enable_icp: bool = True
    icp_iterations: int = 8
    # Back to the values from before the "tryhard" runs (v14). Those runs
    # widened the search to 100 px, the cutoff to 100 px and the orientation
    # tolerance to 60 degrees while the control points were being dropped by
    # the shared robust loss and off-image samples still counted; the wider
    # values were compensating for bugs. 60 degrees also lets most crossing
    # lines through, which is what the orientation filter exists to stop.
    # Test the wide values as a variant, not as the reference.
    icp_search_radius_px: tuple = (40.0, 30.0, 22.0, 16.0, 12.0, 9.0, 7.0, 5.0)
    icp_orientation_tolerance_deg: float = 30.0
    icp_cutoff_px: float = 20.0
    icp_min_correspondences: int = 50

    # Gates (georeferencing.md section 5.2): sanity checks on the aligned
    # affine; any failure falls back to the control-point affine. Lenient on
    # purpose -- they catch a fit that went somewhere absurd, not one that
    # moved a little. A mirrored transform always fails.
    #
    # The coastline chamfer must improve by at least this much. At 0 it fails
    # only when the fit made the coastline match *worse*. Never a threshold on
    # the residual's size: a fit locked onto the wrong feature scores well.
    gate_min_chamfer_improvement: float = 0.0
    # How far below the control-point affine's water IoU the aligned one may
    # fall. Lenient: a sea put on the wrong side of the coast loses far more,
    # while a legitimate correction of a few pixels can cost a narrow sea a few
    # hundredths. Measured on the corpus at x10, aligned water IoU ran
    # 0.72-0.89, rising with the coastline weight.
    gate_water_iou_max_drop: float = 0.10
    # How much the fit may raise the control-point RMS, as a share of the image
    # diagonal (5% is 50 px on a 1000 px map). Measured on the corpus at x10:
    # +0.4 to +3.6 px. Set far above that: only a fit that dragged the map off
    # the user's clicks reaches it.
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
    """What a run uses when nothing is overridden: the defaults above with the
    deployment's environment applied.

    One reader, so the Celery tasks and the dev script agree on what an
    unswitched run is -- which is what decides whether a run may become a
    dev-test case's best.

    The file defaults are the production configuration; the environment can
    only override them for one deployment, and none does by default.
    """
    return DEFAULT_GEOREF_CONFIG.with_overrides(
        snap_to_coastline=_env_flag(
            "GEOREF_ENABLE_COASTLINE_SNAPPING", DEFAULT_GEOREF_CONFIG.snap_to_coastline
        ),
        enable_curve_alignment=_env_flag(
            "GEOREF_ENABLE_CURVE_ALIGNMENT", DEFAULT_GEOREF_CONFIG.enable_curve_alignment
        ),
    )


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


#: The config's sections, in declaration order, so the dev tool can lay the
#: fields out the way this file reads. A test holds it to cover every field
#: exactly once: a field left out would be untunable from the UI, and nobody
#: would notice.
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
        ),
    ),
    ("Land clipping", ("clip_to_land_mask", "land_coverage_threshold")),
    (
        "Zone extraction",
        (
            "text_aware_zone_fill",
            "text_inpaint_algo",
            "text_inpaint_ink_deltaE",
            "zone_gap_fill",
            "zone_gap_max_ratio_of_diagonal",
            "text_inpaint_dilation_px",
            "text_inpaint_radius_px",
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
            "edge_water_min_fraction",
        ),
    ),
    (
        "Alignment",
        (
            "enable_curve_alignment",
            "align_after_piecewise",
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

#: Never overridable: it labels which *code* produced a run, not a setting.
_NOT_OVERRIDABLE = frozenset({"version"})

#: Fields whose value comes from a fixed list. A free-text setting would be a
#: typo away from silently running something other than what was asked for, so
#: these are validated against the list and offered as a dropdown by the UI.
FIELD_CHOICES: Dict[str, Tuple[str, ...]] = {
    "transform_model": TRANSFORM_MODELS,
    "piecewise_regularization": PIECEWISE_REGULARIZATIONS,
    "text_inpaint_algo": TEXT_INPAINT_ALGOS,
}

#: Fields holding a non-empty subset of a fixed list, offered as checkboxes.
#: Stored in the list's own order, so the same subset always compares equal.
FIELD_MULTI_CHOICES: Dict[str, Tuple[str, ...]] = {
    "gcp_sources": GCP_SOURCES,
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
        # JSON has no tuple, so a schedule arrives as a list. Length is free:
        # a schedule is one entry per annealing level, and adding or dropping a
        # level is a legitimate thing to try.
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError(f"{key} must be a non-empty list of numbers, got {value!r}")
        return tuple(_number(v) for v in value)

    raise ValueError(f"{key} has an unsupported type {type(default).__name__}")


def parse_config_overrides(raw: Any) -> Dict[str, Any]:
    """Coerce a caller-supplied override map to typed config fields.

    The dev tool's tuning panel: it admits *every* field, because its whole
    purpose is to try thresholds without editing this file. Overrides live only in the run's config copy; nothing
    here can reach the worker's ambient settings.

    Unknown keys are dropped rather than raising, so a stale frontend sending
    a retired field does not fail the run. A known key with a value of the wrong type raises, because a
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
        "multiChoices": {
            field: list(options) for field, options in FIELD_MULTI_CHOICES.items()
        },
    }
