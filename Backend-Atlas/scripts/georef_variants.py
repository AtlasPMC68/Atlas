"""The named variants the test plan compares (dev-docs/georeferencing-testing.md).

Each variant is a set of GeorefConfig overrides on top of the **file defaults**
(``DEFAULT_GEOREF_CONFIG``), never on the worker's environment, so a variant
means the same thing on every machine and in every container. Change a
variant here and the next run's ``variants.json`` records what it ran with.

``A0`` is the floor every other variant is compared against; the runner always
includes it.
"""

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG

# The baseline every georeferencing variant starts from: the GCP-only affine,
# judged without snapping, which corrects placement error after the fact and so
# hides it (georeferencing-history.md, Step 4). Clipping to land stays on, as in
# the app, so zone metrics describe the zones a user would see.
#
# The defaults moved to B7b (config v19); every setting B7b changed is pinned
# back here, so A0, B2, B5b and the rest still mean what they meant in the
# runs that compared them.
#
# They moved again to C7 (config v22): the bend with the piecewise fallback,
# and snapping that only snaps the coast. _SNAP21 and _PROD21 pin back what C7
# changed, for the variants defined on the old defaults.
_SNAP21: Dict[str, Any] = {
    "coastline_snap_measured": False,
    "coastline_snap_stretches": False,
    "coastline_snap_min_px": 3.0,
}
_PROD21: Dict[str, Any] = {
    **_SNAP21,
    "transform_model": "piecewise_affine",
    "align_after_piecewise": True,
    "coast_bend": False,
    "coast_bend_ridge": 1e-3,
    "coast_bend_fallback_piecewise": False,
}
_A0: Dict[str, Any] = {
    **_SNAP21,
    "transform_model": "affine",
    "snap_to_coastline": False,
    "clip_to_land_mask": True,
    "enable_curve_alignment": False,
    "piecewise_regularization": "none",
    "piecewise_influence_radius_ratio_of_diagonal": 0.15,
    "align_after_piecewise": False,
    "coast_bend": False,
    "coast_bend_ridge": 1e-3,
    "coast_bend_fallback_piecewise": False,
    "weight_curve": 1.0,
}

# The bend in place of the piecewise step and the second alignment, every
# other setting PROD's up to config v21 (W11-W14).
_BEND_ALONE: Dict[str, Any] = {
    **_PROD21,
    "transform_model": "affine",
    "align_after_piecewise": False,
    "coast_bend": True,
    "coast_bend_ridge": 3e-3,
}

# Alignment at equal weights. The weight is pinned rather than inherited from
# the file default (x10 since config v15), so B1-B6 keep the meaning their
# recorded results have: each states its own weight.
_ALIGNED: Dict[str, Any] = {
    **_A0,
    "enable_curve_alignment": True,
    "weight_curve": 1.0,
}


@dataclass(frozen=True)
class Variant:
    name: str
    stage: str
    question: str
    overrides: Dict[str, Any]
    #: Translates the extracted zones in pixel space before georeferencing:
    #: the same as moving the transform by that much. Noise-floor variants only.
    pixel_shift_px: Tuple[float, float] = (0.0, 0.0)


#: The local piecewise reach tried, as a share of the image diagonal: the ends
#: of the plausible range and its middle (the config default, 0.15, is a guess).
_LOCAL_RADII: Tuple[Tuple[str, float], ...] = (("a", 0.1), ("b", 0.175), ("c", 0.25))

#: B3Lb's correction, for the variants built on it.
_B3LB: Dict[str, Any] = {
    "transform_model": "piecewise_affine",
    "piecewise_regularization": "local",
    "piecewise_influence_radius_ratio_of_diagonal": 0.175,
}


def _local_piecewise(
    prefix: str, stage: str, question: str, base: Dict[str, Any]
) -> Tuple[Variant, ...]:
    """One variant per radius in ``_LOCAL_RADII``: *base* plus local piecewise."""
    return tuple(
        Variant(
            f"{prefix}{suffix}",
            stage,
            f"{question} Reach {ratio:g} of the diagonal.",
            {
                **base,
                "transform_model": "piecewise_affine",
                "piecewise_regularization": "local",
                "piecewise_influence_radius_ratio_of_diagonal": ratio,
            },
        )
        for suffix, ratio in _LOCAL_RADII
    )


@dataclass(frozen=True)
class Knob:
    """A constant of the sensitivity sweep (georeferencing-synthetic.md
    §7.4): the config fields it sets, moved together, and the values tried."""

    name: str
    fields: Tuple[str, ...]
    #: The default among them: the config's value, or 1 for a factor.
    values: Tuple[float, ...]
    #: The values are factors on the defaults (a schedule keeps its shape).
    scaled: bool = False
    #: Phase B draws on a log scale.
    log: bool = True
    integer: bool = False

    def overrides(self, value: float) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for f in self.fields:
            default = getattr(DEFAULT_GEOREF_CONFIG, f)
            if self.scaled:
                out[f] = tuple(round(level * value, 3) for level in default)
            else:
                out[f] = int(round(value)) if self.integer else float(value)
        return out

    def label(self, value: float) -> str:
        return f"x{value:g}" if self.scaled else f"{value:g}"


#: Swept one at a time around PROD (phase A), defaults included.
KNOBS: Tuple[Knob, ...] = (
    Knob("weight_curve", ("weight_curve",), (1, 3, 10, 30, 100)),
    Knob("coarse", ("coarse_blur_px", "coarse_cutoff_px"), (0.25, 0.5, 1, 1.5), scaled=True),
    Knob("anneal", ("anneal_blur_px", "anneal_cutoff_px"), (0.5, 1, 2), scaled=True),
    Knob("icp_search_radius_px", ("icp_search_radius_px",), (0.5, 1, 1.5, 2), scaled=True),
    Knob("icp_orientation_tolerance_deg", ("icp_orientation_tolerance_deg",), (15, 30, 45, 60), log=False),
    Knob("icp_cutoff_px", ("icp_cutoff_px",), (10, 20, 40)),
    Knob("curve_sample_spacing_px", ("curve_sample_spacing_px",), (1, 2, 4)),
    Knob("curve_max_samples", ("curve_max_samples",), (4000, 8000, 16000), integer=True),
    Knob(
        "piecewise_influence_radius_ratio_of_diagonal",
        ("piecewise_influence_radius_ratio_of_diagonal",), (0.1, 0.175, 0.25, 0.35), log=False,
    ),
    Knob("piecewise_anchor_margin", ("piecewise_anchor_margin",), (0.1, 0.25, 0.5)),
)
KNOB_BY_NAME: Dict[str, Knob] = {k.name: k for k in KNOBS}


def _is_default(knob: Knob, value: float) -> bool:
    if knob.scaled:
        return value == 1
    return value == getattr(DEFAULT_GEOREF_CONFIG, knob.fields[0])


def _sweep() -> Tuple[Variant, ...]:
    """Stage S: PROD with one knob at one of its other values."""
    return tuple(
        Variant(
            f"S-{knob.name}-{knob.label(value)}", "S",
            f"PROD v21 with {knob.name} at {knob.label(value)}.", {**_PROD21, **knob.overrides(value)},
        )
        for knob in KNOBS
        for value in knob.values
        if not _is_default(knob, value)
    )


#: Phase B: the knobs phase A kept, the range each is drawn from, and how many
#: draws. Phase A (synthetic-step3-A-2026-10-27, georeferencing-synthetic.md
#: §10.3) kept these three; the other seven mattered nowhere and stay at their
#: default. A range is the swept one less any end that lost over all maps
#: (``worse``): x1 and x100 for the coastline weight.
SEARCH: Dict[str, Tuple[float, float]] = {
    "weight_curve": (3, 30),
    "piecewise_influence_radius_ratio_of_diagonal": (0.1, 0.35),
    "icp_cutoff_px": (10, 40),
}
SEARCH_CONFIGS = 30
SEARCH_SEED = 200


def _search() -> Tuple[Variant, ...]:
    """Stage R: PROD with every knob of ``SEARCH`` drawn from its range,
    log-uniform where the knob is ``log``. Seeded, so the names keep their
    meaning."""
    rng = random.Random(SEARCH_SEED)
    out = []
    for i in range(SEARCH_CONFIGS if SEARCH else 0):
        overrides: Dict[str, Any] = dict(_PROD21)
        drawn = []
        for name, (lo, hi) in SEARCH.items():
            knob = KNOB_BY_NAME[name]
            value = math.exp(rng.uniform(math.log(lo), math.log(hi))) if knob.log else rng.uniform(lo, hi)
            value = float(f"{value:.3g}")
            overrides.update(knob.overrides(value))
            drawn.append(f"{knob.name} {knob.label(value)}")
        out.append(Variant(f"R{i + 1:02d}", "R", f"PROD v21 with {', '.join(drawn)}.", overrides))
    return tuple(out)


VARIANTS: Tuple[Variant, ...] = (
    # --- Stage 1: the base transform -----------------------------------------
    Variant("A0", "1", "The floor: GCP-only affine, no snapping.", dict(_A0)),
    Variant(
        "A1", "1", "Does the piecewise correction beat the affine?",
        {**_A0, "transform_model": "piecewise_affine"},
    ),
    *_local_piecewise(
        "A1L", "1", "Piecewise with each correction kept local: does it beat A1?", _A0
    ),
    Variant(
        "A2", "1", "What does blind coastline snapping do to placement?",
        {**_A0, "snap_to_coastline": True},
    ),
    Variant(
        "A3", "1", "How good are the SIFT points on their own?",
        {**_A0, "gcp_sources": ("sift",)},
    ),
    Variant(
        "A4", "1", "How good are the cities on their own?",
        {**_A0, "gcp_sources": ("city",)},
    ),
    # --- Stage 2: curve alignment --------------------------------------------
    Variant(
        "B1", "2", "Does the coastline chamfer alone help?",
        {**_ALIGNED, "enable_icp": False},
    ),
    Variant("B2", "2", "Chamfer + ICP: alignment as designed.", dict(_ALIGNED)),
    Variant(
        "B3", "2", "Alignment, then the piecewise correction on top.",
        {**_ALIGNED, "transform_model": "piecewise_affine"},
    ),
    # B3 lost to B2 on the first corpus run: does keeping each correction
    # local stop the piecewise from pulling regions without a point of their own?
    *_local_piecewise(
        "B3L", "2", "Alignment, then the local piecewise correction on top.", _ALIGNED
    ),
    Variant(
        "B4", "2", "ICP with the wide 60 degree orientation filter.",
        {**_ALIGNED, "icp_orientation_tolerance_deg": 60.0},
    ),
    Variant(
        "B5a", "2", "Coastline weighted x3 against the control points.",
        {**_ALIGNED, "weight_curve": 3.0},
    ),
    Variant(
        "B5b", "2", "Coastline weighted x10 against the control points.",
        {**_ALIGNED, "weight_curve": 10.0},
    ),
    # The first corpus run (2026-10-04) still gained from x3 to x10: where
    # does the weight stop helping, and is ICP needed at a high weight?
    Variant(
        "B5c", "2", "Coastline weighted x30 against the control points.",
        {**_ALIGNED, "weight_curve": 30.0},
    ),
    Variant(
        "B5d", "2", "Coastline weighted x100 against the control points.",
        {**_ALIGNED, "weight_curve": 100.0},
    ),
    Variant(
        "B6", "2", "Chamfer only (no ICP), coastline weighted x10.",
        {**_ALIGNED, "enable_icp": False, "weight_curve": 10.0},
    ),
    # B3Lb was the most even piecewise variant on the 2026-10-08 run. Does
    # aligning again after the correction help, and does the first alignment
    # matter once the last step is an alignment anyway?
    Variant(
        "B7", "2", "B3Lb, then the curve alignment again: align, piecewise, align.",
        {**_ALIGNED, **_B3LB, "align_after_piecewise": True},
    ),
    Variant(
        "B8", "2", "Local piecewise (B3Lb's), then the curve alignment: piecewise, align.",
        {**_A0, **_B3LB, "align_after_piecewise": True},
    ),
    # B7 led the 2026-10-08 run and its gains came from the second alignment:
    # does a stronger coastline help it, as it helped B2 (B5a, B5b)? The weight
    # applies to both alignments.
    Variant(
        "B7a", "2", "B7 with the coastline weighted x3 against the control points.",
        {**_ALIGNED, **_B3LB, "align_after_piecewise": True, "weight_curve": 3.0},
    ),
    Variant(
        "B7b", "2", "B7 with the coastline weighted x10 against the control points.",
        {**_ALIGNED, **_B3LB, "align_after_piecewise": True, "weight_curve": 10.0},
    ),
    # Is the chamfer needed at all? ICP from the control-point affine, with no
    # chamfer stage to bring the map within its search radius first.
    Variant(
        "B9", "2", "ICP only (no chamfer), equal weights.",
        {**_ALIGNED, "enable_chamfer": False},
    ),
    Variant(
        "B10", "2", "ICP only (no chamfer), coastline weighted x10.",
        {**_ALIGNED, "enable_chamfer": False, "weight_curve": 10.0},
    ),
    # --- Stage L: the coast line's centre (config v21) -----------------------
    # The evidence now sits at a drawn coast line's centre, not its sea-side
    # flank; every aligned variant above runs with it. These run without it,
    # to measure the fix (georeferencing-history.md, 2026-10-27).
    Variant(
        "L1", "L", "B5b on the sea-side flank only: the evidence before config v21.",
        {**_ALIGNED, "weight_curve": 10.0, "coast_line_max_width_px": 0},
    ),
    Variant(
        "L2", "L", "PROD on the sea-side flank only: the evidence before config v21.",
        {**_PROD21, "coast_line_max_width_px": 0},
    ),
    Variant(
        "L3", "L", "B5b keeping both flanks with a wider water margin, instead of their midpoint.",
        {**_ALIGNED, "weight_curve": 10.0, "coast_line_max_width_px": 0, "edge_water_margin_px": 8},
    ),
    # --- Stage 3: what the app runs ------------------------------------------
    # The file defaults are the production configuration (alignment on at
    # x10, the bend with the piecewise fallback, snapping only the coast,
    # inpaint), so PROD overrides nothing. Since config v22 it places the
    # zones C7 placed; P21 is production before it (align, piecewise, align,
    # the old snapping), what every "PROD" before v22 means.
    Variant("PROD", "3", "Where we are: the config the app runs.", {}),
    Variant("P21", "3", "Production up to config v21: align, piecewise, align.", dict(_PROD21)),
    # --- Stage W: the map bent to its coast after PROD (synthetic step 4) ----
    # W1 is PROD v21 bent (6 knots, ridge 1e-3, weights by noise); W3 is
    # stiffer, W4 also holds back the bend's affine part (the safest on maps
    # without a bend), W5 has no piecewise step under it. The runs of §10.5
    # had the coast at a fixed 0.9 of the weight; §10.5's X1 and X4 are W1
    # and W5 as they are now.
    Variant("W1", "W", "PROD v21, then bent to the coast.", {**_PROD21, "coast_bend": True}),
    Variant("W3", "W", "W1 stiffer: ridge 1e-2.", {**_PROD21, "coast_bend": True, "coast_bend_ridge": 1e-2}),
    Variant(
        "W4", "W", "W3 with its affine part held back as much.",
        {**_PROD21, "coast_bend": True, "coast_bend_ridge": 1e-2, "coast_bend_affine_ridge": 1e-2},
    ),
    Variant(
        "W5", "W", "The bend on the aligned affine alone (B5b), no piecewise step.",
        {**_ALIGNED, "weight_curve": 10.0, "coast_bend": True},
    ),
    # W6 and W7 are the best fixed ridges of a sweep on 10 maps (§10.5),
    # where block cross-validation did worse than either.
    Variant("W6", "W", "W1 looser: ridge 3e-4.", {**_PROD21, "coast_bend": True, "coast_bend_ridge": 3e-4}),
    Variant(
        "W7", "W", "W5 stiffer: ridge 3e-3.",
        {**_ALIGNED, "weight_curve": 10.0, "coast_bend": True, "coast_bend_ridge": 3e-3},
    ),
    # W8 and W9 split the work: the bend takes the coast (W7), then a local
    # correction the control points far from it (5% / 10% of the diagonal),
    # what only the piecewise step followed on c0d9544d (§10.6). W10 takes
    # every point, near the coast too.
    Variant(
        "W8", "W", "W7, then corrected at the control points far from the coast.",
        {
            **_ALIGNED, "weight_curve": 10.0, "coast_bend": True, "coast_bend_ridge": 3e-3,
            "coast_bend_inland": True,
        },
    ),
    Variant(
        "W9", "W", "W8 with only the points twice as far from the coast.",
        {
            **_ALIGNED, "weight_curve": 10.0, "coast_bend": True, "coast_bend_ridge": 3e-3,
            "coast_bend_inland": True, "coast_bend_inland_min_ratio_of_diagonal": 0.10,
        },
    ),
    Variant(
        "W10", "W", "W8 from every control point: the bend, then the local correction.",
        {
            **_ALIGNED, "weight_curve": 10.0, "coast_bend": True, "coast_bend_ridge": 3e-3,
            "coast_bend_inland": True, "coast_bend_inland_min_ratio_of_diagonal": 0.0,
        },
    ),
    # W11-W14: W7 and W8 on PROD's settings rather than A0's. A0's turn
    # coastline snapping off, so W5-W10's shipped zones were never snapped
    # while PROD's and W1's were (the runners now score every variant both
    # ways, §10.6, so W11 and W7 place the same zones). These keep PROD's
    # piecewise reach too, which W13 and W14 fall back to where the bend
    # refuses (§10.7).
    Variant("W11", "W", "PROD's settings, the bend in place of the piecewise step.", dict(_BEND_ALONE)),
    Variant("W12", "W", "W11, then corrected at the control points far from the coast.", {**_BEND_ALONE, "coast_bend_inland": True}),
    Variant(
        "W13", "W", "W11, falling back to the piecewise step where the bend refuses.",
        {**_BEND_ALONE, "coast_bend_fallback_piecewise": True},
    ),
    Variant(
        "W14", "W", "W12, falling back to the piecewise step where the bend refuses.",
        {**_BEND_ALONE, "coast_bend_inland": True, "coast_bend_fallback_piecewise": True},
    ),
    # --- Stage C: the coastline snap (§10.8) ----------------------------------
    # The snap's tolerance, 1.5% of the diagonal, runs to tens of km and moves
    # inland borders near the sea onto it. C1-C3 change it on PROD, C4-C6 on
    # W13: measured from the coast's misfit, stretches only, both.
    Variant(
        "C1", "C", "PROD v21, snapping within 3x the measured coast misfit.",
        {**_PROD21, "coastline_snap_measured": True},
    ),
    Variant(
        "C2", "C", "PROD v21, snapping only stretches along the coast.",
        {**_PROD21, "coastline_snap_stretches": True},
    ),
    Variant(
        "C3", "C", "PROD v21, snapping stretches within 3x the measured misfit.",
        {**_PROD21, "coastline_snap_measured": True, "coastline_snap_stretches": True},
    ),
    Variant(
        "C4", "C", "W13, snapping within 3x the measured coast misfit.",
        {**_BEND_ALONE, "coast_bend_fallback_piecewise": True, "coastline_snap_measured": True},
    ),
    Variant(
        "C5", "C", "W13, snapping only stretches along the coast.",
        {**_BEND_ALONE, "coast_bend_fallback_piecewise": True, "coastline_snap_stretches": True},
    ),
    Variant(
        "C6", "C", "W13, snapping stretches within 3x the measured misfit.",
        {
            **_BEND_ALONE, "coast_bend_fallback_piecewise": True,
            "coastline_snap_measured": True, "coastline_snap_stretches": True,
        },
    ),
    # The measured tolerance sits at its 3 px floor on most real maps (§10.9),
    # where a drawn coast can stray further from the reference one. C7-C9 are
    # C6 with a higher floor. C7 is production since config v22.
    *(
        Variant(
            name, "C", f"C6 with the snap tolerance at least {px:g} px.",
            {
                **_BEND_ALONE, "coast_bend_fallback_piecewise": True,
                "coastline_snap_measured": True, "coastline_snap_stretches": True,
                "coastline_snap_min_px": px,
            },
        )
        for name, px in (("C7", 5.0), ("C8", 8.0), ("C9", 12.0))
    ),
    # --- Stage X: how much the control points weigh in the bend (step 4) ----
    # The coast's share follows the counts: with σ 4 px for a click, 2 px for
    # a coast match and 20 px of correlation, about 0.93 with 10 control
    # points and 700 matches, 0.98 with 3, 0.88 with 20. X2-X3 give the
    # control points more say on PROD, X5 on B5b (§10.5).
    Variant(
        "X2", "X", "W1 with the clicks at 2 px: the control points 4x stronger.",
        {**_PROD21, "coast_bend": True, "coast_bend_gcp_sigma_px": 2.0},
    ),
    Variant(
        "X3", "X", "X2 with the coast correlated over 60 px: the coast 3x weaker again.",
        {**_PROD21, "coast_bend": True, "coast_bend_gcp_sigma_px": 2.0, "coast_bend_coast_correlation_px": 60.0},
    ),
    Variant(
        "X5", "X", "W5 with the clicks at 2 px.",
        {**_ALIGNED, "weight_curve": 10.0, "coast_bend": True, "coast_bend_gcp_sigma_px": 2.0},
    ),
    # --- Stage S: one constant at a time around PROD (synthetic step 3, A) ---
    *_sweep(),
    # --- Stage R: the constants that mattered, together (step 3, B) ----------
    *_search(),
    # --- Extraction, on the A0 transform -------------------------------------
    Variant("E2", "E", "Zone gap fill on.", {**_A0, "zone_gap_fill": True}),
    # --- Noise floor (Phase 4) -----------------------------------------------
    Variant(
        "N1", "N", "Noise floor: A0 with the transform moved by one pixel.",
        dict(_A0), pixel_shift_px=(1.0, 0.0),
    ),
)

BASELINE = "A0"
BY_NAME: Dict[str, Variant] = {v.name: v for v in VARIANTS}
