# Georeferencing — what a synthetic corpus taught us

From 2026-10-27 to 2026-11-03, maps were rendered under a known deformation, run through the
unchanged pipeline, and measured against the truth everywhere. That work chose today's
production placement: the bend to the coast with a piecewise fallback, and snapping that only
snaps the coast (config v22–v24). This document keeps what was tried, what it showed, and why
production is what it is. How the pipeline works: [`georeferencing.md`](georeferencing.md);
the real-corpus evidence: [`georeferencing-testing.md` §8](georeferencing-testing.md#8-results).

**The code is not on `main`.** The generator (`app/utils/georef_synthetic/`), its runner and
analyses (`run_georef_synthetic.py`, `analyze_georef_synthetic.py`, `show_georef_twins.py`,
`georef_coast_ceiling.py`, `read_georef_records.py`), the research variants and their tests
are at the git tag `archive/georef-synthetic`:

```
git checkout archive/georef-synthetic
```

The quality estimator and the "add a point here" experiments (§10.10–10.11) were removed one
commit earlier: they are in that tag's parent, commit `cc09864`. The runs themselves
(`Backend-Atlas/ablations/`) were never committed; their numbers are below.

---

## 1. Why a synthetic corpus

The real corpus is 18 scored cases on 8 maps, 15 of them with check points. It can tell a
30 km effect from noise; it cannot tune 30 constants, choose a model per map, or make the
alignment checks fail. A generator produces thousands of cases, failures on demand, and the
true error everywhere.

## 2. Labels at training time, observables at run time

Anything learned from synthetic maps is a function of signals the pipeline has on every map
(control points, residuals, chamfer, whether the bend applied); the synthetic truth is only
the label. The real risk is whether synthetic maps produce the same signals, for the same
reasons, as real ones: that was checked first (§10.2). **Real check points stay the test set**:
nothing shipped on synthetic results alone.

---

## 3. The generator

### 3.1 What a case is

A real place, rendered as a map under a known warp `W(lon, lat) = D(A(P(lon, lat)))`
(projection, affine, then a pixel displacement field), with a simulated user's clicks. The warp
is applied to vectors, never to a raster, so the truth is exact everywhere. Extraction is out
of scope: the zones arrive in pixels, exact. The pipeline gets what an import gives it: the
image, control points, one water pick, the framing box. Every region is centred on a coastline.

### 3.2 Deformations and the four twins

Projection (Mercator, equirectangular, Lambert conic), a random affine, a smooth displacement
field (RMS 0.5–3% of the diagonal, for hand-drawn or engraved maps), a local error (one region
shifted or scaled, for maps that draw a region wrong). Every map seed also gives the same map
under four deformations that share everything else:

| Twin | What it stands for |
|---|---|
| `none` | a modern map: projection and affine only, the real corpus's slice |
| `field` | a hand-drawn or engraved map |
| `local` | a map that draws one region wrong |
| `stress` | how bad it can get (field 3–10%, 2–4 local errors, a patchwork of affines) |

The drawn coast is never the reference coast: it is displaced 1–5 px, simplified and loses
small islands, as a pen would. The coast is drawn as a line (1–4 px), a zone outline, or a
plain colour change.

### 3.3 Zones

Countries, or provinces when too few countries show, cut to the pipeline's own land mask, from
0.1% of the image.

### 3.4 The simulated user

At least 3 SIFT pairs (the real finder's suggestions), cities optional; a `protocol` family
over the whole map, and `open` layouts concentrated in a circle; click noise σ 1–8 px; a bad
point on 5% of layouts (a SIFT pair matched to the neighbouring cape, 20–80 px along the
coast); check points scored, never fitted, as on the real cases.

### 3.5 The metric

**Dense error**: 20,000 points uniform on the ground inside the true zones, the distance in km
(and px) between where the pipeline puts each and where it is, before snapping and the clip.
**Zone scores**: mean IoU and outline distance through the real corpus's evaluator, three
ways from the same transform: `raw`, `unsnapped` (clipped to land) and `snapped` (what
ships). From §10.6 on, choices were made on the **snapped IoU**. A map with no deformation and
exact clicks must place at ~0 under the affine: that test proves the generator and the
pipeline agree on pixel origin, axes, units and projection.

### 3.6 What it does not model

Labels, legends, rivers and scan noise; extraction error; inland maps (every region has a
coast); a drawn coast straying far from the reference; maps across the antimeridian. Results
are read through these.

---

## 4. What was tried, and what came of it

| Tried | Result | Fate |
|---|---|---|
| Calibrating the generator against the real findings | Reproduces 7 of 8 (§10.2) once the coast is generalised and click noise is 1–8 px | the basis of the rest |
| Sweeping 10 constants, then 30 joint draws | Production's values were already the best; seven constants are flat (§10.3) | nothing changed |
| A coast-driven smooth correction (the bend) | Large headroom on every twin (§10.4); tuned and confirmed on unseen seeds (§10.5) | **production** (v22) |
| Choosing the bend's stiffness per map by cross-validation | Barely better than chance, worse than a fixed one (§10.5) | removed |
| An inland correction after the bend | Ties or loses on both corpora (§10.6) | removed |
| A per-map selector between pipelines | 0.005 IoU of headroom left once the fallback existed (§10.7) | not built |
| The piecewise step only where the bend refuses | Safer at no cost (§10.6) | **production** (v22) |
| Snapping only coastal stretches, within a measured tolerance | Removes snapping's losses (§10.8–10.9) | **production** (v22) |
| A guard on the second alignment's pull off the clicks | Stops the one shear seen (§10.12) | **production** (v23) |
| A looser snap area guard (25% → 60%) | +0.006 synthetic, +0.002 real, worse on no real case (§10.13) | **production** (v24) |
| A quality estimator (predict a map's error, its IoU) | Ranks maps well, 2.5× optimistic in km on real maps (§10.10) | removed |
| "Add a point here" and guarded reruns | "Farthest from your points" gets most of the gain; no guard works (§10.11) | not built |

**Why not a learned selector or reinforcement learning.** The pipeline has 3–4 stages and a run
takes seconds: every option can simply be run on every case, and the measured headroom between
the best fixed pipeline and a per-map oracle was 0.005 IoU, which no corpus here could measure.

---

## 5. Headroom before building a model

The gap between the best fixed pipeline and a per-map oracle is the most any selector can win.
Measured at 0.019 IoU at first, 0.005 once the fallback and the new snapping were built into the
default (§10.7): too small to be worth a selector.

## 6. The sim-to-real gap

Checked against the real findings before anything was learned (§10.2); real check points as
the test set; split by map, never by layout or twin; rankings rather than absolute numbers.
The real corpus is in sample for what was tuned on it, so a tie there is a good result for a
challenger.

---

## 7. How results are read

- **One vote per map** (per map and twin when twins are compared): a map's layouts share its
  warp, coast and zones. The median of the paired differences, then better / worse / tie.
- **Ties**: 0.2 px or 2% of the map's affine error on the dense error; 0.002–0.005 IoU on zone
  scores; on the real corpus 1 km of check-point RMS, 0.005 IoU.
- **Seeds**: a choice made on some maps is trusted once it holds on others. 100–139 calibrated,
  200–249 swept, 300–349 tuned the bend, 400–449 confirmed it, 500–549 chose the fallback and
  the snapping, 600–749 fitted and tested the estimator, 750–799 confirmed the warm bend.

---

## 8. Open questions

- **Click noise** is a guess (1–8 px); real clicks look noisier (52a1aedc's check points are
  ~17 px off in every layout on a map at IoU 0.98).
- **Historical maps** were never scored with check points. On the one in the repository
  (`Quebec_Traite1783.png`, probes 3bebfa45 and 278e5083), measured at five cities it draws,
  v22 and v21 tie on the sane click sets (66 against 64 km, 161 against 155 km).
- **Snapping's floor is in pixels** (5 px): looser on small images than on large ones.
- **Bad control points**: the bend spreads one over about a sixth of the image; nothing blind
  detects it (§10.10).
- **The coarse schedule at ×0.25** tied production on unseen seeds and ran 30% faster; never
  tried on the real corpus.

## 9. Reproducing a result

Check out the tag, then, as the archived `dev-test-tool.md` describes (it needs the Natural Earth
`borders/` files):

```
docker compose run --rm georef-dev python scripts/run_georef_synthetic.py \
    --maps 50 --seed 500 --layouts 1 --deformation none,field,local,stress \
    --variants P21,PROD --workers 4
```

A map seed always gives the same map, a (seed, layout) pair the same clicks, so a case id such
as `m00520-stress-l00` reproduces a case. Results from two `GENERATOR_VERSION`s (11 at the tag)
are never compared.

---

## 10. Results

`PROD` is production at the time of the run: config v21 (align, piecewise, align, the old
snapping; the variant `P21`) until §10.9, `C7` since. Medians are over maps unless said
otherwise. The variants named here (`B2`, `W7`, `W13`, `C3`, …) are defined at the archive tag.

### 10.1 Found in the pipeline while building the generator (2026-10-27)

- **The keypoint finder lost ~98% of its SIFT detections** and drew phantom lines across the
  frame: regional frames got 0–2 suggestions, below the import's minimum of 3. Fixed
  ([history](georeferencing-history.md#2026-10-27--the-keypoint-finder-lost-most-of-its-detections)).
- **Alignment fit the sea-side edge of a thick coastline**, not its centre: ~1.4 px off on a
  perfect map with the coast 2 px wide. Fixed in config v21
  ([history](georeferencing-history.md#2026-10-27--alignment-is-biased-by-the-coastlines-drawn-width)).

### 10.2 Does the corpus behave like the real one? (2026-10-27)

On the `none` twins (40 maps), map votes better / worse / tie:

| # | Real finding | Synthetic | Holds |
|---|---|---|---|
| F1 | Alignment helps (`B2` vs `A0`) | 27 / 2 / 11 | yes |
| F2 | The coastline weight helps up to ×30 | 7.55 → 4.82 → 4.51 → 4.48 px at ×1 / ×10 / ×30 / ×100 | yes |
| F3 | The gain is at the coast | 41% coastal, 33% inland; at check points as the real maps | yes |
| F4 | Piecewise ≈ affine on its own | 11 / 19 / 10 | yes |
| F5 | Piecewise after alignment undoes it | 11 / 22 / 7 | yes |
| F6 | Local piecewise between two alignments wins | 29 / 8 / 3 | yes |
| F7 | The chamfer is needed when points are clustered | 3 / 6 / 15 | no |
| F8 | ICP's orientation filter changes nothing | 3 / 0 / 37 | yes |

Every real case's signals fall inside the synthetic range. What made the synthetic maps behave
like real ones was click noise and how the coast is drawn.

### 10.3 Which constants matter (2026-10-28)

Ten constants one at a time, then 30 joint draws, 4,200 runs: `weight_curve` ×10, the piecewise
reach 0.175 and ICP's cutoff 20 were already the best values; the other seven are flat. No draw
beat production anywhere.

### 10.4 Headroom for a coast fit (2026-10-28/29)

`denseMeanPx`, seeds 300–349:

| | `none` | `field` | `local` | `stress` |
|---|---|---|---|---|
| `A0` (control-point affine) | 6.1 | 15.3 | 12.5 | 49.4 |
| `PROD` (v21) | 4.8 | 12.1 | 10.6 | 43.6 |
| ceiling: the best affine of the truth | 1.5 | 9.3 | 7.5 | 35.1 |
| ceiling: a smooth fit to the true correction across the coast | 0.7 | 1.8 | 3.3 | 15.2 |

Alignment does nothing on `stress` (an affine cannot follow a coast bent by 2–5% of the
diagonal), and the coast alone pins down most of the bend: seen across the coast only, a smooth
fit takes out 90% of the stress error near it and 58% far from it.

### 10.5 The bend (2026-10-29/30)

`bend.py`: the reference coast pushed into the map, matched to the drawn coast by the
alignment's normal search over shrinking radii, Tukey-reweighted, across the coast only, with
the control points sharing the weight by their noise (1/σ²). Refused if it folds the map, moves
it more than 10% of the diagonal, or makes the coast chamfer worse.

- Loose bends tilt maps that were right; very stiff ones keep little of the gain.
- Weighting by noise beats a fixed share on every twin; more weight on the control points makes
  the bend refuse itself.
- **Block cross-validation does not find the ridge** (on the oracle's ridge 3–8 times in 30,
  chance 4). Removed.

On unseen seeds 400–449 (`denseMeanPx`, then votes against `PROD`):

| Variant | `none` | `field` | `local` | `stress` |
|---|---|---|---|---|
| `PROD` (v21) | 4.7 | 11.5 | 8.5 | 44.9 |
| `W1`: `PROD`, then the bend | 4.1 · 25/16 | 7.2 · 36/7 | 5.9 · 36/6 | 40.3 · 35/4 |
| `W7`: alignment, then the bend at 3e-3, no piecewise step | **3.0** · 36/9 | **5.7** · 45/3 | 6.6 · 37/9 | 34.7 · **41/6** |

**The bend replaces the piecewise step rather than adding to it**, in half the time.

### 10.6 The real corpus, and the fallback (2026-10-30/31)

`W11` is `W7` on production's settings; `W13` adds the fallback: the piecewise step and the
second alignment where the bend refuses. Mean IoU, votes against `PROD` (v21):

| | synthetic, snapped (196) | real, snapped (17) |
|---|---|---|
| `PROD` | 0.712 | 0.886 |
| `W11` | 0.750 · 136/53 | **0.895** · 7/1 |
| `W13` | 0.750 · 129/41 | 0.894 · 5/1 |

- **The bend beats v21 on both corpora**; the fallback makes it safer at no cost on average
  (it applies on 19 of 196 synthetic cases).
- **An inland correction after the bend** (`coast_bend_inland`, variants `W8`–`W14`) ties or
  loses on both corpora, the worst on the real corpus when it corrects at every point. Removed.
- A first comparison had the bend unsnapped against a snapped `PROD`; since then every variant
  is scored three ways from the same transform (§3.5).

### 10.7 How much a choice per map could win (2026-10-30/31)

Oracle against the best fixed pipeline, 196 cases: 0.776 against 0.757 at first; with the
fallback and the new snapping, **0.005 IoU** between the two pipelines still worth choosing
between. The one signal a first selector found, whether the bend applied, became the fallback.
No selector.

### 10.8 Snapping that only snaps the coast (2026-10-31)

The old snapping moved every boundary vertex within 1.5% of the diagonal of the coast (17–220 km)
onto it: inland borders near the sea moved onto the coast, borders reaching the sea bent, and
the shore became chords. On `W13` it took more than 0.05 IoU off 24 of 196 cases. Two switches:
`coastline_snap_stretches` (only runs of vertices along the coast, onto the coast's own
vertices; a polygon left alone if its area would change too much) and `coastline_snap_measured`
(a tolerance of 3× the coast's measured misfit, between a floor and the old 1.5%).

| Synthetic, 196 cases | cleaned | snapped | costs > 0.01 | costs > 0.05 |
|---|---|---|---|---|
| `P21` (old snapping) | 0.709 | 0.712 | 37 | 10 |
| `C3`: `P21`, both switches | 0.709 | 0.724 | **1** | **0** |
| `W13` (old snapping) | 0.758 | 0.751 | 53 | 24 |
| `C6`: `W13`, both switches | 0.758 | **0.768** | **2** | **0** |

On the real corpus both switches turn snapping's worst case from −0.022 to +0.001.

### 10.9 Step 7: `C7` on the real corpus, and production (2026-10-31)

The floor of the measured tolerance at 5 px rather than 3 (`C7`): free on synthetic maps, and it
takes the real gain on the hand-drawn Mexico map (15df33d7, 0.743 → 0.756).

**c0d9544d had one wrong control point**: a SIFT pair drawn at Iquique but paired with
Antofagasta, 380 km down the coast. The bend, a smooth field ~960 km wide on this map, pulled its
region south; the piecewise step had kept it local. The point was removed from the case, and the
case with it kept as the probe `protocol-iquique`.

**`C7` against `P21`**, 18 real cases (snapped IoU):

| Map (cases) | `P21` | `C7` |
|---|---|---|
| 10c029ef (1) | 0.914 | 0.926 |
| 15df33d7, drawn (1) | 0.706 | **0.756** |
| 44992611 (3) | 0.849–0.852 | 0.847–0.876 |
| 52a1aedc (5) | 0.976–0.981 | 0.980–0.981 |
| c0d9544d (1) | 0.624 | **0.753**; check points 77.7 → 49.9 km |
| c4e81e4d (3) | 0.867–0.878 | **0.904–0.915** |
| c858266f (1) | 0.879 | **0.937** |
| f12f2ea4 (3) | 0.842–0.847 | 0.842–0.851 |
| mean | 0.873 | **0.897**: 9 better, none worse by more than 0.005 |

**Decision (config v22).** Alignment ×10, the bend at ridge 3e-3, the piecewise step and the
second alignment only where the bend refuses, snapping only the coast with the measured
tolerance and a 5 px floor. Re-run on 2026-11-15, before §10.13's change: 0.897 against 0.873,
the same nine better.

### 10.10 The quality estimator (2026-11-01, removed)

A linear model on log error from blind signals, fitted on 1,470 synthetic runs, tested on 750
and on the held-out stress twin. On synthetic maps it ranked maps far better than the reported
`rmse_km` (rank 0.63 against 0.22) and its p90 covered 85%. On the real corpus it ranked maps by
IoU (+0.73) but its kilometres were **2.5× optimistic**: real check points carry their own error
(~20 km), and real maps distort their interior more than any twin. A second model predicting the
snapped IoU from the error over each zone's size transferred (rank +0.86 on the real corpus).
Flagging a wrong control point by its leave-one-out residual did not work: drawing distortion
makes good points disagree with an affine as much. It ran on every import as a diagnostic that
nothing read; removed on 2026-11-15 (commit `cc09864` has it).

### 10.11 One more click (2026-11-01/03, not built)

Adding the click the estimator picks gains 2.8× a random one, but the point farthest from every
control point gets most of that. One click can make a map worse (13% of cases), because it moves
the affine the bend starts from; no blind guard fixed it. Bending the old placement again with
the new click, and placing the map again only where that bend refuses, halves the maps made
worse and gains a third more, on unseen seeds too. It needs the previous placement stored with
the map; not built.

### 10.12 The second alignment's guard (2026-11-01)

On the fallback, the second alignment fits an affine in front of a piecewise model that already
sits on the clicks. On 255 synthetic fallback runs it pulled the clicks off by 0.25% of the
diagonal (median), 0.85% at p99. One front, adding a correct city to m00712/local, sheared the
map (y scale 2.14) and pulled the clicks 2.45% off: dense error 20 → 94 km.
`post_align_max_gcp_shift_ratio_of_diagonal` = 0.02 refuses such a front (config v23); it
refuses none of the 255 runs and nothing on the real corpus (6 px at most).

### 10.13 The snap area guard (2026-11-15)

On the cases where `C7`'s snapping lost to the old one, the stretches snapped nothing at all:
m00520-stress, 0 of 345 vertices, where the old snapping gained +0.19. Relaxing each rule in
turn showed the cause: the area guard, which leaves a zone unsnapped when snapping would change
its area by more than 25%. With no guard, the narrow zone it exists for folds onto the coast
again (one case −0.09); retrying at half the tolerance helped little. Each map placed once,
only the snapping varying:

| Guard | synthetic, 196 cases | better / worse by > 0.01 | real, 18 cases | worse |
|---|---|---|---|---|
| 25% (`C7`) | 0.768 | | 0.897 | |
| **60%** | **0.774** | 33 / 6 (worst −0.021) | **0.899** | none |

The gain on the real corpus is on the three east asia cases (+0.010–0.012), which makes
44992611/protocol, the one case `C7` placed slightly below `P21`, better than it. Production
since config v24. It remains a trade-off: the guard cannot tell a narrow zone from a shore
placed far off.
