# Georeferencing — Experiments Log

What has been tried, what it measured, and what is switchable. Companion to
[`georeferencing-plan.md`](georeferencing-plan.md) (the PoC),
[`georeferencing-roadmap.md`](georeferencing-roadmap.md) (what comes after) and
[`georeferencing-current.md`](georeferencing-current.md) (what exists).

**Read the numbers as weak evidence.** Everything below rests on two maps. The
roadmap's own rule (§5.3) is that two models are distinguishable only when the
difference in held-out error exceeds its standard error, and n = 2 has no
standard error to compare against.

Last updated 2026-09-22.

---

## Test subjects

| Case | Map | Size | GCPs | Notes |
|---|---|---|---|---|
| `52a1aedc…/pip_7sift` | scanned map | — | 7 sift | Scored, IoU ~0.94. **Currently broken**: its `config.json` predates `frameBounds`, so the suite fails it. |
| `278e5083…/test-5-sift-points-peut-etre` | `Quebec_1791.png` | 602×375 | 6 sift | Probe (no expected zones). Water pipetted. |
| `278e5083…/test_piece_wise_affine` | same map | 602×375 | 6 sift | Probe, run with the gates neutralized. |

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

Not done yet: geometries are not densified before warping, so a long straight
edge crossing several triangles stays straight; and the gates judge only the
base affine.

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
| `transform_model` | `affine` | More freedom is the experiment, not the baseline. |

Ambient values come from the environment (`GEOREF_ENABLE_CURVE_ALIGNMENT`,
`GEOREF_ENABLE_COASTLINE_SNAPPING`). `GEOREF_DEBUG` writes a per-run diagnostic
folder; for a dev-test case it lands in `<case>/alignment_debug/` and is
**overwritten on every re-run**, so copy it before comparing two settings.

Config versions: 5 → 6 (piecewise) → 7 (`transform_model` as a named choice).

---

## Open questions, in priority order

1. **A second scored case.** The plan has called this the bottleneck since Step
   4 landed. Both current Quebec cases are probes, so neither produces an IoU.
2. **Fix `pip_7sift`** or recreate it: its missing `frameBounds` is the suite's
   only failure.
3. **Do the Tier 3 constants fit a small map?** §4's scaled schedule is the
   cheapest thing left to try.
4. **Is `gate_water_iou_min = 0.70` right?** One measurement, 0.395, and no idea
   whether it is the map or the threshold.
5. **Separate chamfer from ICP** on a clean run.
6. **Is the piecewise gain real?** It needs a case with ground truth, scored by
   IoU rather than by leave-one-out on six points.
