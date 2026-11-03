"""The variant runner's contract (scripts/run_georef_variants.py)."""

import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if not os.path.isdir(_SCRIPTS):
    pytest.skip("scripts/ is not mounted in this container", allow_module_level=True)
sys.path.insert(0, _SCRIPTS)

from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG  # noqa: E402
from app.utils.georeferencing.config import parse_config_overrides  # noqa: E402
from georef_variants import BY_NAME, VARIANTS  # noqa: E402


def test_every_variant_is_a_valid_config():
    """A misspelt override would otherwise fail mid-run, or worse, if the
    parser dropped it, run as the baseline under another name."""
    assert len(BY_NAME) == len(VARIANTS)
    for variant in VARIANTS:
        parsed = parse_config_overrides(dict(variant.overrides))
        assert set(parsed) == set(variant.overrides), variant.name
        DEFAULT_GEOREF_CONFIG.with_overrides(**variant.overrides)




def test_the_sweep_is_one_knob_at_a_time_around_prod():
    """Stage S (georeferencing-synthetic.md §7.4): 26 variants, each
    production up to config v21 with one knob moved; a schedule keeps its
    shape."""
    import georef_variants

    sweep = [v for v in VARIANTS if v.stage == "S"]
    assert len(sweep) == 26
    pinned = set(georef_variants._PROD21)
    for knob in georef_variants.KNOBS:
        assert sum(georef_variants._is_default(knob, v) for v in knob.values) == 1, knob.name
        assert not pinned & set(knob.fields), knob.name
        for v in sweep:
            if v.name.startswith(f"S-{knob.name}-"):
                assert set(v.overrides) == set(knob.fields) | pinned, v.name
    coarse = BY_NAME["S-coarse-x0.5"].overrides
    assert coarse["coarse_cutoff_px"] == tuple(c / 2 for c in DEFAULT_GEOREF_CONFIG.coarse_cutoff_px)
    assert coarse["coarse_blur_px"] == tuple(b / 2 for b in DEFAULT_GEOREF_CONFIG.coarse_blur_px)
    assert BY_NAME["S-weight_curve-30"].overrides == {**georef_variants._PROD21, "weight_curve": 30.0}
    assert BY_NAME["S-curve_max_samples-4000"].overrides == {**georef_variants._PROD21, "curve_max_samples": 4000}


def test_the_search_draws_inside_the_swept_ranges(monkeypatch):
    import georef_variants

    monkeypatch.setattr(georef_variants, "SEARCH", {"weight_curve": (1, 100), "icp_search_radius_px": (0.5, 2), "curve_max_samples": (4000, 16000)})
    drawn = georef_variants._search()
    assert len(drawn) == georef_variants.SEARCH_CONFIGS
    assert drawn == georef_variants._search(), "seeded: a name keeps its meaning"
    default_radius = DEFAULT_GEOREF_CONFIG.icp_search_radius_px
    for v in drawn:
        assert all(k.name in georef_variants.SEARCH for k in georef_variants.KNOBS if set(k.fields) & set(v.overrides))
        parse_config_overrides(dict(v.overrides))
        assert 1 <= v.overrides["weight_curve"] <= 100
        assert isinstance(v.overrides["curve_max_samples"], int)
        factor = v.overrides["icp_search_radius_px"][0] / default_radius[0]
        assert 0.5 - 1e-3 <= factor <= 2 + 1e-3
    assert len({v.overrides["weight_curve"] for v in drawn}) > 20


def test_phase_b_draws_inside_its_ranges():
    import georef_variants

    for v in (v for v in VARIANTS if v.stage == "R"):
        for name, (lo, hi) in georef_variants.SEARCH.items():
            knob = georef_variants.KNOB_BY_NAME[name]
            value = v.overrides[knob.fields[0]]
            assert lo - 1e-9 <= value <= hi + 1e-9, (v.name, name)
