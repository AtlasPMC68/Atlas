"""The synthetic analysis script (scripts/analyze_georef_synthetic.py): votes
per map, ties, verdicts and twin comparisons, on a made-up results.csv; the
real-corpus reports on made-up signals.csv and checkpoints.csv."""

import csv
import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if not os.path.isdir(_SCRIPTS):
    pytest.skip("scripts/ is not mounted in this container", allow_module_level=True)
sys.path.insert(0, _SCRIPTS)

from analyze_georef_synthetic import (  # noqa: E402
    Comparison,
    _check_cells,
    by_variant,
    load,
    signals_report,
    twins_report,
)


def _row(seed, twin, layout, variant, px, radius=0.8):
    return {
        "id_case": f"m{seed:05d}-{twin}-l{layout:02d}",
        "id_mapSeed": seed,
        "id_deformation": twin,
        "id_layout": layout,
        "id_variant": variant,
        "gen_deformation": twin,
        "gen_imageWidth": 1000,
        "gen_imageHeight": 800,
        "gen_kmPerPixel": 2.0,
        "gen_radiusRatio": radius,
        "run_status": "ok",
        "m_denseMeanPx": px,
        "m_denseMeanKm": px * 2.0,
        "m_denseCoastalMeanKm": px,
        "m_denseInlandMeanKm": px * 3.0,
        "m_denseMeanKmGcpAffine": px * 2.0,
    }


@pytest.fixture
def run_dir(tmp_path):
    rows = []
    for seed in range(6):
        for layout in range(3):
            rows.append(_row(seed, "none", layout, "A0", 10.0))
            rows.append(_row(seed, "field", layout, "A0", 20.0))
            # Better by 2 px on every map of `none`, by 0.1 px (a tie) on `field`.
            rows.append(_row(seed, "none", layout, "B2", 8.0))
            rows.append(_row(seed, "field", layout, "B2", 19.9))
    # One map whose layouts disagree: its vote is their median.
    rows += [_row(9, "none", 0, "A0", 10.0), _row(9, "none", 0, "B2", 13.0),
             _row(9, "none", 1, "A0", 10.0), _row(9, "none", 1, "B2", 12.0),
             _row(9, "none", 2, "A0", 10.0), _row(9, "none", 2, "B2", 5.0)]
    rows.append({**_row(9, "none", 3, "B2", 0.0), "run_status": "error"})
    _write(tmp_path / "results.csv", rows)
    return str(tmp_path)


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_one_vote_per_map_and_twin(run_dir):
    rows = load(run_dir)
    assert all(r["run_status"] == "ok" for r in rows)
    c = Comparison(by_variant(rows, "denseMeanPx"), "B2", "A0", tie=0.2, tie_ratio=0.02)
    # 7 maps on `none` + 6 on `field`.
    assert c.n == 13
    # `none`: 6 maps better; map 9's median layout is +2 (worse). `field`: ties.
    assert (c.better, c.worse, c.tied) == (6, 1, 6)
    assert c.case_better == 19 and c.case_worse == 2


def test_the_tie_scales_with_the_map_error(run_dir):
    rows = load(run_dir)
    values = by_variant(rows, "denseMeanPx")
    field = [k for k in values["A0"] if k[1] == "field"]
    # 0.1 px on a 20 px map: under 2% (0.4 px), a tie even with a 0.05 floor.
    assert Comparison(values, "B2", "A0", tie=0.05, tie_ratio=0.02, keys=field).verdict() == "tie"
    assert Comparison(values, "B2", "A0", tie=0.05, tie_ratio=0.0, keys=field).verdict() == "better"


def test_twins_report_the_change_of_an_effect(run_dir):
    rows = [r for r in load(run_dir) if r["id_mapSeed"] != 9]
    text = "\n".join(twins_report(rows, [("B2", "A0")], ("none", "field"), "denseMeanPx", 0.2, 0.02))
    # The effect goes from -2 px to -0.1 px: weaker on all 6 maps, median +1.9.
    assert "0 / 6 / 0" in text
    assert "+1.90" in text


def test_derived_columns(run_dir):
    r = load(run_dir)[0]
    assert r["gen_longSide"] == 1000.0
    assert r["m_denseCoastalMeanPx"] == r["m_denseCoastalMeanKm"] / 2.0


def test_signals_flag_a_real_case_outside_the_synthetic_range(run_dir, tmp_path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    synthetic = [
        {"id_case": f"m{seed:05d}-none-l{layout:02d}", "id_variant": "PROD", "run_baselineGcpRmsPx": 2.0 + seed,
         "run_alignedGcpRmsPx": 2.5 + seed}
        for seed in range(6) for layout in range(3)
    ]
    _write(os.path.join(run_dir, "signals.csv"), synthetic)
    # In-fit: one case past the synthetic max (7 px). Clicks moved: all inside.
    _write(real_dir / "signals.csv", [
        {"id_case": "t/a", "id_variant": "PROD", "run_baselineGcpRmsPx": 4.0, "run_alignedGcpRmsPx": 4.5},
        {"id_case": "t/b", "id_variant": "PROD", "run_baselineGcpRmsPx": 9.0, "run_alignedGcpRmsPx": 9.5},
    ])
    rows = [r for r in load(run_dir) if r["id_deformation"] == "none"]
    lines = signals_report(rows, run_dir, str(real_dir), "PROD")
    in_fit = next(line for line in lines if line.startswith("| In-fit"))
    moved = next(line for line in lines if line.startswith("| How far alignment moves the clicks"))
    assert "`t/b` 9" in in_fit and in_fit.endswith("**no** |")
    assert moved.endswith("none | yes |")


def test_check_points_split_coastal_and_inland():
    def point(case, i, variant, km, coast_km, source):
        return {"id_case": case, "id_point": float(i), "id_variant": variant, "errorKm": km, "kmPerPixel": 2.0,
                "coastDistanceKm": coast_km, "source": source}

    points = []
    for case in ("t1/a", "t2/a"):
        # The coastal point loses three quarters of its error, the inland one none.
        points += [point(case, 0, "A0", 8.0, 10.0, "sift"), point(case, 0, "B5c", 2.0, 10.0, "sift"),
                   point(case, 1, "A0", 8.0, 200.0, "city"), point(case, 1, "B5c", 8.0, 200.0, "city")]
    cells = _check_cells(points, "B5c", lambda c: c.split("/")[0])
    coastal, inland = cells["coastal (≤ 50 km)"], cells["inland"]
    assert coastal[:4] == ["2", "4.00 → 1.00", "+75%", "2 / 0"]
    assert coastal[4] == "+75% (2)"
    assert inland[:4] == ["2", "4.00 → 4.00", "+0%", "0 / 0"]
    assert cells["SIFT"] == coastal and cells["city"] == inland


def test_sweep_freezes_a_knob_that_never_matters_and_flags_one_that_flips_between_twins(tmp_path):
    from analyze_georef_synthetic import sweep_knobs

    rows = []
    for seed in range(12):
        for twin in ("none", "field"):
            base = 10.0
            rows.append(_row(seed, twin, 0, "A0", 20.0))
            rows.append(_row(seed, twin, 0, "PROD", base))
            # 0.1 px better everywhere: a tie.
            rows.append(_row(seed, twin, 0, "S-icp_cutoff_px-40", base - 0.1))
            # 1 px better everywhere.
            rows.append(_row(seed, twin, 0, "S-weight_curve-30", base - 1.0))
            rows.append(_row(seed, twin, 0, "S-weight_curve-3", base + 0.5))
            # Better on `none`, worse on `field`.
            rows.append(_row(seed, twin, 0, "S-anneal-x2", base + (-1.0 if twin == "none" else 1.0)))
    _write(tmp_path / "results.csv", rows)
    knobs = sweep_knobs(load(str(tmp_path)), tie=0.2, tie_ratio=0.02)
    assert knobs["icp_cutoff_px"]["verdict"] == "frozen"
    assert knobs["weight_curve"]["verdict"] == "phase B"
    assert knobs["weight_curve"]["best"] == {"`none`": "30", "`field`": "30"}
    assert [v["value"] for v in knobs["weight_curve"]["values"]] == ["3", "30"]
    assert knobs["anneal"]["verdict"] == "selector"
    assert knobs["anneal"]["best"] == {"`none`": "x2", "`field`": "default"}

