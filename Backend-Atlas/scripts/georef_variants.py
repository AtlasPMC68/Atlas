"""The named variants the test plan compares (dev-docs/georeferencing-testing.md).

Each variant is a set of GeorefConfig overrides on top of the **file defaults**
(``DEFAULT_GEOREF_CONFIG``), never on the worker's environment, so a variant
means the same thing on every machine and in every container. Change a
variant here and the next run's ``variants.json`` records what it ran with.

``A0`` is the floor every other variant is compared against; the runner always
includes it.
"""

from dataclasses import dataclass
from typing import Any, Dict, Tuple

# The baseline every georeferencing variant starts from: the GCP-only affine,
# judged without snapping, which corrects placement error after the fact and so
# hides it (georeferencing-history.md, Step 4). Clipping to land stays on, as in
# the app, so zone metrics describe the zones a user would see.
_A0: Dict[str, Any] = {
    "transform_model": "affine",
    "snap_to_coastline": False,
    "clip_to_land_mask": True,
    "enable_curve_alignment": False,
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


VARIANTS: Tuple[Variant, ...] = (
    # --- Stage 1: the base transform -----------------------------------------
    Variant("A0", "1", "The floor: GCP-only affine, no snapping.", dict(_A0)),
    Variant(
        "A1", "1", "Does the piecewise correction beat the affine?",
        {**_A0, "transform_model": "piecewise_affine"},
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
    # Is the chamfer needed at all? ICP from the control-point affine, with no
    # chamfer stage to bring the map within its search radius first.
    Variant(
        "B7", "2", "ICP only (no chamfer), equal weights.",
        {**_ALIGNED, "enable_chamfer": False},
    ),
    Variant(
        "B8", "2", "ICP only (no chamfer), coastline weighted x10.",
        {**_ALIGNED, "enable_chamfer": False, "weight_curve": 10.0},
    ),
    # --- Stage 3: what the app runs ------------------------------------------
    # The file defaults are the production configuration (alignment on at
    # x10, piecewise, snapping, inpaint), so PROD overrides nothing.
    Variant("PROD", "3", "Where we are: the config the app runs.", {}),
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
