# Georeferencing — Experiments Log

What has been tried, what it measured, and what is switchable. Companion to
[`georeferencing-plan.md`](georeferencing-plan.md) (the PoC),
[`georeferencing-roadmap.md`](georeferencing-roadmap.md) (what comes after) and
[`georeferencing-current.md`](georeferencing-current.md) (what exists).

**Read the numbers as weak evidence.** Everything below rests on two maps. The
roadmap's own rule (§5.3) is that two models are distinguishable only when the
difference in held-out error exceeds its standard error, and n = 2 has no
standard error to compare against.

> **Every alignment number in §1 and §4 was measured with bugs active**, fixed
> on 2026-09-30 and described in [`georeferencing-fixes.md`](georeferencing-fixes.md):
> the control points were rejected by a robust loss shared with the curve
> samples (so "joint" meant curve-only), and reference samples off the image
> read the distance field at its border. Those numbers describe the bugs, not
> alignment. §6's leave-one-out comparison was computed honestly and stands;
> the per-run piecewise error the pipeline reported was optimistic. §5 and §3
> are unaffected.

Last updated 2026-09-30.

---

## Test subjects

| Case | Map | Size | GCPs | Notes |
|---|---|---|---|---|
| `52a1aedc…/pip_7sift` | scanned map | — | 7 sift | Scored, IoU ~0.94. **Currently broken**: its `config.json` predates `frameBounds`, so the suite fails it. Needs re-clicking. |
| `278e5083…/test-5-sift-points-peut-etre` | `Quebec_1791.png` | 602×375 | 6 sift | Probe (no expected zones). Water pipetted. |
| `278e5083…/test_piece_wise_affine` | same map | 602×375 | 9 sift | Probe, run with the gates neutralized. |
| `278e5083…/ville2`, `vlle`, `test_with_lake` | same map | 602×375 | 5 sift + 4 city / 6 / 9 sift | Probes. `ville2`'s points fold the map, so piecewise is refused there. |
| `3bebfa45…/1st`, `bite` | `quebec_traite1783` | — | 6 / 4 sift | Probes. |
| `0152677a…/italy_test_tryhard` | Italy | — | 7 sift | Probe. |
| `92518248…/test_on_uk_map_tryhard` | UK | — | 6 sift | Probe. |

`italy_test_tryhard`, `test_on_uk_map_tryhard` and `test_with_lake` were stored
in the pre-city `imagePoints`/`worldPoints` format and ran with **no control
points** until migrated on 2026-09-30.

---

## 1. Curve alignment (chamfer + ICP) — plan §8b, §8c

| Configuration | IoU on `pip_7sift` |
|---|---|
| Stage 2 affine, snapping **on** | 0.9414 |
| affine + chamfer + ICP, snapping on | 0.9443 |
| Stage 2 affine, snapping **off** | 0.9260 |
| affine + chamfer + ICP, snapping off | **0.9301** (+0.0040) |

**Blind coastline snapping invalidated the first measurement.** Translating the
same transform a few pixels and rescoring gave a non-monotonic IoU with a 0.012
downward spike at 5 px with snapping on, versus a smooth 0.0063 fall with it
off. The deltas being compared were smaller than that artifact.

**Judge alignment with `snap_to_coastline` off.** Snapping corrects transform
error after the fact, so it flatters the baseline and hides improvements.

Chamfer and ICP have still never been measured apart on a clean run.

**These are pre-fix numbers.** The "+ chamfer + ICP" rows are a curve-only fit
started from the GCP affine (fixes §1). They are not a measurement of the joint
fit.

## 2. Coastline-first staging — plan §8d

Driven by a second map where the starting transform was too far off for the
chamfer to reach the coast.

- Rivers dropped as alignment evidence (`use_rivers_for_alignment=False`): thin,
  dense, often drawn schematically.
- Two stages: coastline alone, then lakes admitted, then ICP.
- Coarse schedule widened to 64 px blur / 400 px cutoff (was 16/120).
- New gate `curve_fit_engaged`: a fit that never moved used to pass every
  sanity check and return the baseline wearing a success label.

## 3. Edge evidence and the water filter

Current values in `config.py`: blur 3, Canny 40/120 (looser than the coastline
keypoint finder's 5 and 75/175, which dropped whole stretches of coast), text
mask dilated 7 px, straight lines down-weighted to 0.15 rather than deleted.

`edge_water_filter` keeps only edges within 3 px of *both* water and non-water.
On `Quebec_1791` it kept **33%** of 7,895 raw edge pixels. Intended, but it
leaves few samples on a small map — see §4.

## 4. Quebec_1791 — where it stands

Run with defaults, snapping off, alignment on:

| Gate | Value | Threshold | |
|---|---|---|---|
| `probe_gcp_disagreement` | 23.06 px (169 km) | 20.63 px (2× baseline 10.32) | FAIL |
| `water_mask_iou` | 0.395 | 0.70 | FAIL |
| `inlier_fraction` | 0.090 | 0.20 | FAIL |

Rungs 0–3 all failed the same three gates; the run fell to rung 7, `gcp_only`.
The curve term *did* engage (coastline chamfer 3.4 → 2.9 px, coast moved 6.4 px).

**Pre-fix.** The probe disagreement was inflated by off-map samples dragging the
probe toward the image border, and the inlier fraction divided by samples that
were off the map. With the fixes, on the same case: probe 11.0 px (was 23.1),
joint fit within 0.1 px of the GCP affine, coast moved 1.9 px. Per-case
before/after numbers are in [fixes §5](georeferencing-fixes.md#5-what-changed-on-the-real-cases).
The "constants do not fit a small map" hypothesis below predates the fixes and
has not been re-examined.

**First time `water_mask_iou` has ever had data** — it reported
`applicable: false` on every earlier run. Whether 0.70 is the right threshold is
untested.

**Leading hypothesis: the constants do not fit a 602×375 map.** The coarse
Tukey cutoff (400 px) is wider than the image, and the blur (64 px) is a sixth
of its height. Untested suggestion, scaled ~4×:

```
coarse_blur_px    16, 10, 6, 3.5      anneal_blur_px     2, 1, 0.5, 0
coarse_cutoff_px  100, 65, 42, 27     anneal_cutoff_px   18, 11, 7, 4.5
icp_search_radius_px  10, 7.5, 5.5, 4, 3, 2.2, 1.7, 1.2
```

A second run with every threshold neutralized (`gate_probe_gcp_ratio` 1000 etc.)
passed at rung 0 with `method: joint`, probe 20.03 px, chamfer 4.4 → 3.1 px
(+30%). **That is a look, not a result**: the gates were the only thing
measuring it.

## 5. Reference keypoint selection (`sift_key_points_finder.py`)

Old: strongest-first, keep anything ≥ `MIN_DISTANCE` px from those already kept.
New: **farthest-point sampling** — seed with the strongest, then repeatedly take
the candidate farthest from all chosen.

Why: the radius was doing two jobs and could only do one. On a Quebec framing
box at 1024×768, the surviving pool was 19 points at D=10 px but only 6 at
D=200 px, so no value both spread the points and filled the request. The count
also behaved non-monotonically, because `N` decides whether lakes get added
(roughly doubling the pool), so raising it changed the candidates, not just the
cut.

| | returned | closest pair | mean nearest |
|---|---|---|---|
| Old, N=10 | 10 | 33 px | 107 px |
| New, N=10 | 10 | **103 px** | **165 px** |

N is honoured up to the pool (35 here). Border margin and the duplicate floor
are now ratios of the diagonal (2% and 1%), so the raster size no longer changes
what they mean — verified identical at 512, 1024 and 2048 px wide.

Spread is not cosmetic: clustered GCPs make the affine badly conditioned, which
is what `probe_gcp_disagreement` punishes.

## 6. Piecewise affine (`piecewise.py`)

Global affine, plus a Delaunay correction pinned at each control point and
decaying to zero on a frame around the image. Continuous everywhere, so zones
are never cut and never need stitching; outside the frame it is the plain affine,
which is what the old TPS got wrong.

On `Quebec_1791`'s real control points, error in km (leave-one-out — the point
being measured was excluded from the fit):

| Model | LOO RMS |
|---|---|
| Affine | 172.3 km |
| Piecewise | **156.9 km** |

Better at all 6 points, mean gain 16.5 km (sd 10.3, se 4.2). Caveats: n=6, LOO
folds are correlated, and both numbers are terrible in absolute terms — the
control points disagree with each other whatever model is fitted (the affine's
in-sample RMS is 75.5 km against its 172 km LOO).

The correction reaches 98 km at one vertex. It interpolates rather than averages,
so it reproduces a bad click instead of smoothing it away — roadmap §5.4:
*worse-drawn maps need fewer DOF, not more*.

Reported error is always leave-one-out: an interpolating model's in-sample
residual is 0 by construction.

**The table above stands; the per-run number did not.** The 156.9 km was a real
leave-one-out. What the pipeline reported on every run (`rmse_km`, the run
record, the dev tool's per-source error) held the base affine fixed, and that
base had been fitted with the held-out point: 101.9 km on this case, and ~0 km
with 3 points. Fixed on 2026-09-30 ([fixes §3a](georeferencing-fixes.md#a-the-reported-error-was-not-leave-one-out)).
On other cases the honest comparison does not favour piecewise everywhere: on
the Italy map it is 47.4 km against the affine's 43.6.

Since 2026-09-30, geometries are densified before a piecewise warp, and the
frame the correction decays to is padded around the image, the zones and the
control points (it used to be the zones only, which broke continuity when a
point lay beyond them). Still true: the gates judge only the base affine.

---

## What is switchable, and how

Every `GeorefConfig` field can be overridden **per run** from the dev tool's
**Paramètres (ce run seulement)** panel, and the model itself from the
**Modèle de transformation** dropdown. Nothing is written to `config.py`; what a
run used is in its `run_record.json` under `runSwitches`. A run with any
override is never promoted to `zones_best`.

| Setting | Default | Why it is off |
|---|---|---|
| `enable_curve_alignment` | on in the app, off in the suite | The suite measures the GCP-only floor; the app is where it is judged by hand. |
| `snap_to_coastline` | on (off in the re-run panel) | Hides alignment improvements — §1. |
| `transform_model` | `piecewise_affine` | Set as the default in v13, during the "tryhard" runs; not yet justified by a measurement. |
| Gates | neutralised (v13) | All logged; only a mirror, a non-converged optimiser or a chamfer that got worse can still reject. |

Ambient values come from the environment (`GEOREF_ENABLE_CURVE_ALIGNMENT`,
`GEOREF_ENABLE_COASTLINE_SNAPPING`). `GEOREF_DEBUG` writes a per-run diagnostic
folder; for a dev-test case it lands in `<case>/alignment_debug/` and is
**overwritten on every re-run**, so copy it before comparing two settings.

Config versions: 5 → 6 (piecewise) → 7 (`transform_model` as a named choice)
→ … → 13 (the "tryhard" values: gates neutralised, piecewise and inpaint by
default, ICP widened to 100 px / 60° / 100 px) → 14 (ICP back to 40→5 px / 30° /
20 px, `piecewise_densify_ratio_of_diagonal`; [fixes §4](georeferencing-fixes.md#4-also-in-this-change)).

---

## Open questions, in priority order

1. **A second scored case.** The plan has called this the bottleneck since Step
   4 landed. Both current Quebec cases are probes, so neither produces an IoU.
2. **Fix `pip_7sift`** with "Compléter les entrées" (draw the world area and answer the legend; its SIFT points are kept): its missing `frameBounds` is the suite's
   only failure.
3. **Do the Tier 3 constants fit a small map?** §4's scaled schedule is the
   cheapest thing left to try.
4. **Is `gate_water_iou_min = 0.70` right?** One measurement, 0.395, and no idea
   whether it is the map or the threshold.
5. **Separate chamfer from ICP** on a clean run. "Clean" now also means
   post-fix: no alignment measurement before 2026-09-30 counts.
5b. **The balance `weight_gcp` / `weight_curve`.** Post-fix, at 1:1 the joint
   fit stays within ~1 px of the GCP affine on every case. How far the coast
   should be allowed to move the map is now a real, untested dial.
6. **Is the piecewise gain real?** It needs a case with ground truth, scored by
   IoU rather than by leave-one-out on six points.
