# Georeferencing — a synthetic corpus, and what can be learned from it

Maps rendered under a known deformation, run through the unchanged pipeline, and measured
against the truth everywhere. This document answers one question: **with maps whose deformation
we know, what can we learn that still applies in production, where nothing is known?** It says
what the generator is (§3), what can be learned from it (§4–§6), how its results are read (§7),
the plan and where it stands (§8), and what the runs found (§10).

**Status (2026-10-31).** Steps 1–5 and 7 are done. They replaced the piecewise correction with a
bend to the coast and the old snapping with one that only snaps the coast: that is production
since config v22 (`C7`, §10.9). Step 6's selector is not worth building for now (§10.7); its
quality estimator is next. How to run the tools: [`dev-test-tool.md`](dev-test-tool.md#synthetic-maps).
How the pipeline works: [`georeferencing.md`](georeferencing.md). The real-corpus evidence:
[`georeferencing-testing.md` §8](georeferencing-testing.md#8-results).

---

## 1. Why a synthetic corpus

The real corpus is 18 scored cases on 8 maps, 15 of them with check points, none historical. It
can tell a 30 km effect from noise; it cannot tune 30 constants or learn when to choose which
model, and nothing on it ever made the alignment checks fail. A generator produces thousands of
cases, failures on demand, and the true error everywhere.

---

## 2. Labels at training time, observables at run time

The worry is: on a real map there are no expected zones, so anything trained against them does
not apply. That is not how it works.

Anything learned is a function of **signals the pipeline has on every map**: how many control
points and how spread, their residuals, the chamfer before and after alignment, whether the bend
applied. The synthetic ground truth is only the **label** used to fit that function. In
production the same signals are computed, and the function is applied without any label.

So the real risk is not the missing ground truth. It is whether **synthetic maps produce the
same signals, for the same reasons, as real maps** (§6, §3.7). Step 2 checked that (§10.2).

### What the blind signals are

`records.record_signals` reads them from every run record, real or synthetic, into the `run_`
columns:

| Signal | Columns | Kind |
|---|---|---|
| control points, per source | `controlPointCount`, `siftCount`, `cityCount` | input |
| the affine's residual on the control points | `baselineGcpRmsPx` | in-fit |
| how far alignment moves the clicks and the coast | `alignedGcpRmsPx`, `coastDisplacementPx` | in-fit |
| chamfer before and after alignment; inliers, ICP correspondences | `baselineChamferPx`, `alignedChamferPx`, `inlierFraction`, `correspondences` | in-fit |
| the bend: applied or why not, its largest correction, matches, the coast's share, chamfer before and after; the fallback | `coastBend*`, `bendFallbackApplied` | in-fit |
| the coast misfit snapping reads, and its tolerance | `snapMisfitPx`, `snapToleranceMeters` | in-fit |
| the error the pipeline reports, and how (leave-one-out for piecewise) | `gcpRmseKm`, `gcpRmseKind` | held out |
| how the control points cover the image: hull share, nearest-neighbour gaps, the largest empty radius | `hullShare`, `nearestGapMedianRatio`, `nearestGapMaxRatio`, `emptyRadiusRatio` | input |
| the affine's leave-one-out residuals (closed form) | `looAffineRmsPx`, `looAffineMaxPx`, `looAffineMaxOverMedian` | held out |
| how much coast the frame holds | `coastlineSamples`, `coastlineCoverage` | input |
| scale, latitude, image size | `metersPerPixel`, `referenceLatitude`, `imageDiagonalPx` | input |
| water agreement, the checks | the record's `gates` | in-fit |

Per point, `quality.point_features` gives what the run knows at one pixel (§4.3); the synthetic
runner writes it with each scored point (`--points`).

The difference between **in-fit** and **held-out** matters. In-fit signals were optimised by the
fit, so they look better the harder the fit tries, whether or not the map is better placed.
Held-out signals are honest estimates of error *at those locations*, but noisy with few points
and blind where there is no evidence.

---

## 3. The generator

`app/utils/georef_synthetic/`, run by `scripts/run_georef_synthetic.py`. Dev-only: nothing in
the pipeline imports it, and the pipeline runs exactly as in production. `GENERATOR_VERSION` 11.

### 3.1 What a case is

A real place, rendered as a map, under a known warp `W`, with a simulated user's clicks.

**The warp maps world → pixel and is applied to vectors**, never to a raster: zones, coastline,
lakes, borders, cities and keypoints are pushed through `W` and then drawn. Nothing is
resampled, so the truth is exact everywhere, and measuring a run needs no inverse: take a ground
point, find its true pixel `W(s)`, ask the pipeline where that pixel goes.

```
W(lon, lat) = D( A( P(lon, lat) ) )
    P: projection     lon/lat -> plane
    A: affine         plane -> pixel (fits the region to the image, plus a random distortion)
    D: displacements  pixel -> pixel (smooth field, local error)
```

**Extraction is out of scope.** The zones are handed to the pipeline already in pixels (the true
zones through `W`, their coastal edges following the drawn coast, §3.2): no zone picks, no colour
extraction. What the pipeline is given, as the import would give it:

- **the image**, rendered plainly: sea, land, zones, lakes, borders, the coast, and as
  distractors a neatline (70%) and a warped graticule (50%). The coast is drawn three ways: a
  line on half the maps, 1–4 px wide, its colour anywhere from barely off the sea's to dark; the
  zones' 1 px outline along the coast on 40%, otherwise between zones only; neither, on 30%, a
  plain colour change (as on the italie map);
- **control points** from the simulated user (§3.4);
- **one water pick**, at the ocean pixel farthest from land: alignment needs it to identify the
  coastline ([`georeferencing.md` §5.2](georeferencing.md#52-curve-alignment));
- **the framing box**: the bounding box of what the image shows, padded 5–10% per side;
- no legend, no OCR text regions (no labels are drawn, §3.7).

**The region** is centred on a point of the coastline drawn uniformly **by length**, with a
longitude span log-uniform 5°–90° (median ~21°), an aspect of 0.6–1.6, and an image of
500–2000 px on its long side. There is no minimum of land or sea: every map has a coast at its
centre, and how much it shows is recorded (`coastLengthRatio`, `zoneCoastShare`, land and ocean
fractions).

### 3.2 Deformation families, and the four twins

Coherent errors, not just noise: noise alone tests the optimiser, not the problem.

| Family | What | Drawn | Real counterpart |
|---|---|---|---|
| Projection `P` | Mercator (an affine fits it exactly, since the pipeline fits in EPSG:3857) · equirectangular · Lambert conformal conic | 30% · 35% · 35% | maps drawn in another projection (east asia, [testing §8.5](georeferencing-testing.md#85-east-asia-no-affine-fits)) |
| Affine `A` | rotation, scale ratio, shear | always | any scan; absorbed exactly by the affine |
| Smooth field | a random low-frequency displacement, RMS 0.5–3% of the diagonal | 60% | hand-drawn or engraved maps |
| Local error | one region shifted (1–4% of the diagonal) or scaled (±10–30%) | 40% | historical maps that draw a region wrong |

A warp that folds is redrawn. A Mercator map with neither field nor local error is the **easy
case** (~7% of maps): only click noise separates the affine from the truth.

**Twins.** Every map seed also gives the same map under four deformations, drawn together so
they share the region, projection, affine, style, framing box and layout draws; only `D`
differs. The paired difference between a map's twins isolates what deformation does.

| Twin | `D` | What it stands for |
|---|---|---|
| `none` | none | a modern map: projection and affine only. The real corpus's slice, where step 2 calibrates |
| `field` | the map's smooth field | a hand-drawn or engraved map |
| `local` | the map's local error | a map that draws one region wrong |
| `stress` | a field of RMS 3–10% of the diagonal, 2–4 local errors (4–10% or ±30–50%), and a patchwork of 2–3 pieces each placed by its own affine | how bad it can get; not calibrated |

The stress twin comes from a stream of its own (the base twins are identical with or without it);
a stress draw that folds is drawn again 15% weaker (`gen_stressStrength`). Its non-affine part is
2–5% of the diagonal (35–80 px), 4–8 times the field's. `gen_nonAffineRmsPx` measures every
twin's strength. `scripts/show_georef_twins.py --seeds …` draws a map's twins with arrows for
what no affine takes out.

**Coastline generalisation** (`generalise.py`): the drawn coast is never the reference coast. It
is a drawing error of the coast alone, on every map, the same for a map's twins:

| Part | Drawn | What it does |
|---|---|---|
| Displacement | RMS 1–5 px, a Gaussian-kernel field with kernels every 2–5% of the diagonal | capes and bays drawn a few pixels off, irregularly: short against the control points' spacing, so no interpolator between them follows it |
| Simplification | Douglas–Peucker at 0.5–2.5 px | what is too small to draw |
| Dropped islands | under a disc of 3 tolerances in radius | the same |

In pixels, as a pen's error on a scan (0.5 mm at 300 dpi is 6 px). It changes the land fill, the
coastline, the zones' coastal edges, and where a user clicks a coastal SIFT feature; a feature
the map no longer draws is not suggested. The truth, the warp and the metric are unchanged.
Lakes are drawn exactly. The convention tests turn it off (`WarpOptions(coast_generalisation=False)`).

### 3.3 Zones

Zones are **countries, or provinces when the map shows too few countries**, cut to the
pipeline's own land mask:

- **Countries** when at least 2 cover 1% of the image each; otherwise the **provinces** of the
  countries in view (countries alone would reject every regional map on the coast of a large
  country). A country's provinces are replaced by Natural Earth's groups only when too small to
  pick.
- A zone is kept from **0.1% of the image** (~37 × 37 px on a 1400 px map).
- Zones are extended ~5 km into the sea before being cut to land (borders are Natural Earth 10m,
  the coastline 50m).
- Zone colours never come within ΔE 15 of the sea's, since the water mask is built by colour.

### 3.4 The simulated user

The only user input that varies is the control points. Every layout parameter is drawn, none is
a category, so a continuous range covers the real case roles (`protocol`, `minimal`,
`clustered`) and everything between. The layout follows the import's rules: **at least 3 SIFT
pairs, cities optional**.

| Parameter | Distribution |
|---|---|
| Family | `protocol` on 40% of layouts: the whole map, at least 6 SIFT pairs and 3–6 cities, each picked with weight × the squared distance to the nearest point already chosen, so they spread and some cities fall inland, as in the real protocol cases. `open` otherwise, as below. A `gen_` column, never a feature |
| SIFT pairs (open) | uniform from 60% of the suggestions on the map to all of them. The suggestions are the real finder's, called as the import calls it |
| Cities (open) | none 60% of the time; otherwise 1–6 |
| Area (open) | a circle, radius log-uniform 30%–100% of the diagonal, centred on a SIFT suggestion chosen in proportion to how many lie within the radius. Only candidates inside can be picked; the area grows until it holds 3 suggestions |
| Click noise | σ uniform 1–8 px per layout, around where the map draws the point (for a coastal SIFT pair, its feature on the generalised coast) |
| Bad point | 5% of layouts: one SIFT pair matched to the neighbouring cape or bay, its click 20–80 px **along the drawn coast** |
| Check points | scored, never fitted, as on the real cases: up to 4 SIFT suggestions and 4 cities the layout did not click, near the zones, none nearer a control point than a third of their typical gap, at most 2 outside their hull, clicked with the layout's noise |

Within the area, SIFT pairs are picked uniformly and cities by √population, never within 1% of
the diagonal of a point already chosen. Families, check points and layouts each have their own
random stream, so adding one never changes another.

**Why a bad point.** A gross error is the one piecewise interpolates instead of averaging, the
one a leave-one-out test must notice. The realistic one is a SIFT pair matched to a nearby
feature that looks the same, hence the move along the coast. The real corpus has one
(c0d9544d, §10.9). A wrong city is not drawn: picking the wrong candidate almost never happens.

### 3.5 The metric

Two kinds of score, both against the truth.

**Dense error**, the transform's: 20,000 points uniform **on the ground** inside the true zones;
for each, the distance in ground km between where the pipeline puts its pixel and where it is,
with the Mercator scale at the point's own latitude. Mean, median, p90 and max, split coastal /
inland at 50 km, and under the control-point affine too.

- **The points are drawn once per map**, so every layout and variant of a map is measured on the
  same points: differences between variants are paired.
- **In px as well** (`denseMeanPx`, the error over the map's km per pixel): maps run from 0.3 to
  10 km/px, and means in km are dominated by the largest maps.
- Before snapping and the clip, which correct transform error after the fact.

**Zone scores**, what the user gets: mean IoU and mean boundary distance through the real
corpus's evaluator, so the two corpora compare. Scored three ways from the same transform,
whatever the variant's snapping setting: `raw` (straight out of the transform), `unsnapped`
(clipped to land) and `snapped` (snapped, then clipped: what ships). `m_meanIou` is the
variant's own shipped zones.

**Which one decides.** The dense error ranked transforms through step 4. From §10.6 on, choices
are made on the **snapped IoU**, a plain mean over zones (not area-weighted), with the outline
distance alongside: the two can rank variants differently (§10.6), and the user sees the zones.

**The convention check.** A map with no deformation and exact clicks must place at ~0 under the
affine (`tests/test_georef_synthetic.py`): it proves the generator and the pipeline agree on
pixel origin, axis direction, units and projection. Changing the dense metric's points or its
units invalidates every earlier result.

### 3.6 Reproducibility and the results table

- **A map seed gives a map and its twins; a (map seed, layout) pair gives a layout.** A case id
  like `m00042-field-l03` reproduces a case. **Train and test sets are split by map**, never by
  layout or twin, since those share everything else.
- **`GENERATOR_VERSION`** is bumped whenever a seed would produce a different case; results from
  two versions are never compared.
- **Variants come from `scripts/georef_variants.py`**, shared with the real corpus. Variants
  defined on old defaults pin those defaults, so a name keeps its meaning: `P21` is production up
  to config v21, `PROD` the current one.
- **`results.csv` has one row per case × variant**, with prefixed columns, the guard against a
  model learning from what the generator knows and production does not:

| Prefix | What | Blind? |
|---|---|---|
| `id_` | case, map seed, twin, layout, variant | — |
| `gen_` | everything the generator drew: families, amplitudes, layout, bad point | **no: never a feature** |
| `run_` | what the run did and saw (§2) | yes |
| `m_` | the metrics | labels |

Synthetic cases are never committed: they are regenerated from their seeds, and runs go to
`ablations/`.

### 3.7 What the generator does not model

Results are read through these:

| Not modelled | Effect |
|---|---|
| Labels, legends, rivers, scan noise | fewer wrong edges; a cleaner water mask (water agreement is reported, not gated, §7.3) |
| Extraction error | zones arrive exact; real zones carry their own error (15df33d7, §10.9) |
| A whole stretch of coast drawn off together | tried as a long-wave drift (v10) and dropped: alignment then pulled the interior off, which real maps do not show (§10.2) |
| A drawn coast straying far from the reference | generalisation is 1–5 px; a hand-drawn map's coast strays more, which is why snapping's floor was tuned on the real corpus (§10.9) |
| Inland maps | every region is centred on the coastline (§3.1), and a map needs 3 SIFT suggestions, which are coast and lake features: 20 of 2,945 quality runs had no coast in the frame. The real corpus is all coastal too (§10.10); its one inland map, e14c0fdb (Mongolia), has no framing box and cannot run |
| Maps crossing the antimeridian; projections beyond three | none generated |
| Guessed rates: 40% protocol layouts, 60% of open layouts without cities, 5% bad points, click noise 1–8 px, padding 5–10% | recorded per case, so analyses can reweight; the `reclick` cases should measure click noise |

---

## 4. What can be learned and used blind

From cheapest and most robust to most ambitious; stop at the first that leaves no headroom (§5).

### 4.1 Which constants matter — done

A sweep shows which constants move the true error; the rest are frozen. It transfers well: it is
a statement about the pipeline, not about the maps. Result (§10.3): seven constants are flat over
their ranges, three matter, and their defaults were already the best values found.

### 4.2 Robust defaults — done

The best pipeline **when nothing is known about the map**: the lowest expected error over the
generator's distribution, checked on the real corpus. The steps of §10.4–10.9 found it: `C7`
(alignment ×10, the bend, the piecewise step only where the bend refuses, snapping only the
coast), production since config v22.

### 4.3 Calibrating the blind signals: a quality estimator — next

Synthetic data does not make a signal reliable; it **measures how reliable it is, and when**:

- How well does leave-one-out RMS predict the true zone error, as a function of n and spread?
- When alignment or the bend makes a case worse, what does the run record look like?
- How fast do in-fit signals and true error diverge?

The result is a **quality estimator**, `f(blind signals) → expected error`. It is what
[roadmap §8](georeferencing-roadmap.md#8-telling-the-user-how-good-the-result-is) needs (an
accuracy estimate per map, and where more control points would help) and what
[roadmap §6](georeferencing-roadmap.md#6-the-alignment-checks) needs (check thresholds from
data). It does not need headroom between pipelines to be useful, and any future selector would be
built on it.

**What it is for**, in order: tell the user how accurate their map is ("typically within 15 km,
up to 40"); show where the placement is least reliable and where one more control point would
help most; flag a control point that disagrees with the others, shown to the user and acted on by
nothing (the user's clicks are trusted); later, the checks' thresholds and any selector.

**What it predicts.** The dense error in km (§3.5) of what ships (`PROD`), per map (median and
p90) and per point (the error at any pixel: every case already has 20,000 scored ground points).
Km rather than IoU, which depends on zone sizes and means nothing without expected zones; it must
still rank maps as the snapped IoU does.

**What it sees.** Blind signals only (§2), computed by `quality.py` the same way in production
and in the runners. Per map: the `run_` columns, with the control points' spread and the affine's
leave-one-out. Per point: the distance to the nearest control point and how many are near,
inside their hull or not, how far the pipeline moved the pixel from the control-point affine,
the distance to the coast and how well the coast fits around it, and the leave-one-out residuals
of the nearest control points.

**The model** is small: a linear model on log(error) with 3–6 inputs chosen under leave-map-out
cross-validation, quantile regression for the p90. Monotone boosted trees only as a comparison.
It must beat a constant (the corpus median, scaled by km per pixel) and, above all, the
`rmse_km` the pipeline already reports.

| # | What | Status |
|---|---|---|
| Q1 | Log the missing signals; one function for the per-point inputs, shared by production and the runners | **done** |
| Q2 | The synthetic runner saves a sample of scored points per case, with their inputs (`--points`) | **done** |
| Q3 | Dataset: `PROD` only, seeds 600–699 to fit and 700–749 to test, four twins, 5 layouts per map (~3,000 runs) | **done** (§10.10) |
| Q4 | Fit against the baselines, leave-map-out; the stress twin held out entirely | **done** (§10.10): passes on the fit twins, optimistic on stress |
| Q5 | "Add a point here": one more simulated click where it predicts the largest error, against one at random; the gain of each | **done** (§10.11): 2.8× random, but "farthest from the points" gets most of it |
| Q6 | The real corpus: predicted against measured error at the real check points (~100 on 15 cases), maps ranked by error and IoU; flagging on c0d9544d's original Iquique point (a probe case) and on the synthetic bad points | **done** (§10.12): ranks maps by IoU, 2.5× optimistic in km; the flag does not work |
| Q7 | What the user sees: a number per map, an overlay, "add a point near here", a point warning | after Q6 |
| Q8 | Whether to ask at all: the map's snapped IoU predicted from the error over each zone's size; ask for a click below a threshold | **done** (§10.13): AUC 0.89 on unseen maps, rank 0.86 on the real corpus; recorded on every run since (`errors.predictedQuality`) |

**Usable** if it beats `rmse_km` at ranking maps on both corpora, its p90 covers 80–95% of the
real check points, and no twin or layout family makes it optimistic by more than 2×. **"Add a
point here" is worth building** if in Q5 the suggested spot gains at least 1.5× what a random one
does. It estimates placement only, not extraction error, and has never seen a historical map.

### 4.4 Validating selection rules

Blind procedures that pick a setting per map, compared with an **oracle** (the choice the truth
says was best):

- **The bend's ridge by block cross-validation over the coast** — tested, **fails** (§10.5):
  barely better than chance at finding the oracle's ridge, worse on average than a fixed one.
  The coast's own fit cannot say how far its correction should carry inland.
- **Piecewise when its leave-one-out is 20% lower** ([roadmap §2](georeferencing-roadmap.md#2-transform-model-affine-by-default-piecewise-by-leave-one-out))
  — not tested. With the bend in production, piecewise only runs in the fallback.

### 4.5 A per-map selector

The usable form of "an agent whose toolbox is our transformations, their order and their
constants".

1. Fix K discrete pipelines: the affine, the piecewise step, the bend at a few stiffnesses, each
   with or without the second alignment, the coastline weight ×10 or ×30. K ≈ 10–30.
2. Run all K on every synthetic case. Record the blind signals (§2) and the true error of each.
3. Train a small model to predict each pipeline's error from the signals; choose the lowest. A
   shallow decision tree or a logistic model, readable enough to defend every choice.
4. Keep the non-regression rule: the default unless the model is confident another pipeline is
   better by a margin.

In the literature this is per-instance algorithm selection.

**Why not reinforcement learning.** RL pays when the decisions are sequential and too many to
enumerate. Here the pipeline has 3–4 stages, the sensible orders fit on one hand, and a run takes
seconds: every option can simply be run on every case.

**Why not learning from pixels.** A network looking at the map would learn the generator's
rendering, and the gap from a clean render to a scanned engraving is the largest there is.

**Not built, for now (2026-10-31).** The headroom it could take is 0.005 IoU between the two
pipelines that are still worth choosing between, 0.012 with a third (§10.7). A first selector
captured a fifth of a headroom four times that size, so here it would gain about 0.001, which no
corpus we have could measure. The one signal that did carry a choice, whether the bend applied,
is built in as the fallback. Worth reopening if a cheap oracle run over new candidates (bend
stiffnesses, `W1`) shows 0.02 IoU or more, and then on top of the quality estimator.

---

## 5. Measure the headroom before building a model

| | What |
|---|---|
| **Oracle** | the best of the K pipelines for each case, chosen with the truth |
| **Best fixed default** | the single pipeline with the lowest mean error over all cases (§4.2) |
| **Today** | the current file defaults |

The gap oracle → best fixed default is the **most any selector can ever win**. If it is small,
stop at §4.2. Measured (§10.7): 0.019 IoU at first; 0.005 once the fallback and the new snapping
were built into the default.

---

## 6. The sim-to-real gap, and how to contain it

- **Check the generator against what is already known** (step 2, §7.3): it must reproduce the
  real-corpus findings before anything is learned from it.
- **Real check points stay the test set.** Synthetic cases train and explore; nothing ships on
  synthetic results alone. A default or model ships only if it does at least as well as the
  current production on the real corpus, under the
  [decision rules](georeferencing-testing.md#decision-rules-phase-3).
- **The real corpus is in sample for what was tuned on it.** `P21`'s constants were chosen on it,
  so a tie there is a good result for a challenger.
- **Hold out whole maps, and whole families.** Split by map (§3.6); train on some twins, test on
  the others. A model that works only on the families it saw learned the generator.
- **Out-of-distribution fallback.** When a real map's signals fall outside what the generator
  produced, use the safe default.
- **Report rankings, not absolute numbers.** A ranking that holds across generator settings is
  what transfers.

---

## 7. How results are read

### 7.1 Votes per map, ties

A map's layouts and twins share its warp, coast and zones, so they are not independent. A
comparison is counted **one vote per map** (per map **and twin** when twins are compared): the
median of the paired differences over the map's cases, then better / worse / tie.

Ties: on the dense error, under **0.2 px or 2% of the map's `A0` error**; on zone scores, under
0.002–0.005 IoU (stated with each table). On the real corpus: 1 km of check-point RMS, 0.005 IoU,
0.5–1 km of outline. The cases of a real map are not independent either: read per map too.

### 7.2 Seeds

A choice made on a set of maps is only trusted once it holds on maps it was not made on.

| Seeds | Used for |
|---|---|
| 0–19 | the pilot; nothing decided on them |
| 100–139 | step 2, calibration |
| 200–249 | step 3, the sweep |
| 300–349 | step 3's confirmation, the stress twin, the coast ceiling, the bend's first tuning |
| 400–449 | the bend on unseen seeds |
| 500–549 | step 5 and everything after: the fallback, snapping, the snap floor |
| 600+ | unused |

### 7.3 Step 2's calibration rules

The real corpus's maps are modern: in generator terms, the `none` twins. Each real finding must
reproduce **in direction** on them (the real numbers are check-point errors on 12–14 cases, the
synthetic ones dense errors, so sizes are not compared):

| # | Real finding | Comparison |
|---|---|---|
| F1 | Alignment helps | `B2` vs `A0` |
| F2 | The coastline weight helps up to ×30, then stops | `B2`, `B5b`, `B5c`, `B5d` |
| F3 | The gain is at the coast | `B5c` vs `A0`, coastal and inland apart |
| F4 | Piecewise ≈ affine on its own | `A1` vs `A0` |
| F5 | Piecewise after alignment undoes it | `B3` vs `B2` |
| F6 | Local piecewise between two alignments wins | `B7b` vs `B2` |
| F7 | The chamfer is needed when points are clustered | `B10` vs `B5b`, area radius under 0.5 |
| F8 | ICP's orientation filter at 60° changes nothing | `B4` vs `B2` |

Two magnitude checks, on the `none` twins: the in-fit residual (`baselineGcpRmsPx`) within a
third to three times the real one; and **every real case's signals inside the synthetic range**,
not all in one tail (a real case outside is a map the generator cannot produce). Water agreement
is reported, not gated: its level is set by what a real sea holds (labels, legends, hatching).
For the deformed twins, what each finding should do was written down before the run, from its
mechanism.

When a finding does not reproduce: first look for the slice within `none` where it holds (both
corpora may agree, and the synthetic one says where the finding stops); then at what the
generator does not model (§3.7); then at how much real evidence the finding rests on.

### 7.4 Step 3's sweep rules

Ten constants were swept one at a time around production (stage `S`, 26 variants generated from
the defaults; schedules move as one factor): `weight_curve` 1–100, the coarse and fine
schedules ×0.25–×2, ICP's reach ×0.5–×2, orientation 15–60°, cutoff 10–40, curve sampling
1–4 px and 4,000–16,000 samples, the piecewise reach 0.1–0.35 and frame 0.1–0.5. Not swept:
structure (the transform model and the stages, which are pipelines, §4.5); the image-reading
constants (Canny, water, straight lines), which a clean render would show insensitive for the
wrong reason; optimiser budgets; the check thresholds.

**A constant matters** if one of its values moves the median of the per-map differences by more
than 0.3 px or 3% of `PROD`'s error, with votes at least 2 to 1, over all maps, on a twin, or on
a slice of 10 votes or more (image size, km per pixel, coastal / inland, area radius, point
count, projection, coast width). Phase B searches the survivors together (stage `R`, 30 seeded
draws); phase C confirms on unseen seeds. A constant whose best value differs between twins is a
choice for the selector, not a default.

### 7.5 Tools

| Tool | What |
|---|---|
| `scripts/run_georef_synthetic.py` | generates and runs cases: `--maps --seed --layouts --deformation none,field,local,stress --variants/--stage --workers`, `--case` for one, `--points N` for `points.csv` (N scored dense samples per run with their `pt_` inputs, §4.3). One BLAS thread per worker (before 2026-10-30, `pipelineSeconds` were inflated). Four workers fit in 7.5 GB of Docker memory; six ran out once |
| `scripts/analyze_georef_synthetic.py` | re-reads a run's `results.csv`: `--compare a:b`, `--twins none:field`, `--by`, `--where`, `--findings` (§7.3), `--signals` and `--checkpoints` against a real run (`--real`), `--sweep` (§7.4) |
| `scripts/read_georef_records.py` | reads a run folder's `run_record.json` files, real or synthetic, into `signals.csv` (the `run_` columns) and `checkpoints.csv`; refits the control-point affine where an old record did not log it |
| `scripts/run_georef_variants.py` | the same variants on the real corpus, scoring snapping three ways (§3.5) |
| `scripts/fit_georef_quality.py` | fits the quality estimator on `--fit` datasets (forward selection, leave-map-out CV, stress held out), scores it once on `--test`, against the constant and `rmse_km`; writes `report.md`, `model.json`, `predictions.csv` (§10.10). The point p90 (quantile regression by linear programme) takes most of its ~25 min |
| `scripts/run_georef_add_point.py` | Q5: each case placed by `PROD`, then again with one more click chosen four ways (estimator, random, farthest, oracle) from the SIFT suggestions and the 40 largest cities; `--model` a Q4 `model.json` (§10.11). The `guard_` columns and the guarded tables: what a guarded rerun could read to keep or drop the new click (§10.14). The `local_` columns: the old placement corrected instead of placed again, by a bump at the click or the warm-started bend; `--asked-only`, `--strategies` (§10.15) |
| `scripts/run_georef_quality_corpus.py` | Q6: the Q4 model on every dev-test case, probes included, against its check points and snapped IoU; the leave-one-out flag on the real cases and on the Q3 synthetic layouts (§10.12); each case's predicted IoU as production records it (§10.13) |
| `scripts/fit_georef_success.py` | Q8: predicted snapped IoU on the Q3 runs, from Q4's predictions and the zones' sizes (`quality.zone_sizes`, `zone_errors`, `disc_iou`), scored as "ask for a click below a threshold" (§10.13); `--ship` writes the Q4 and Q8 models into `georeferencing/quality_model.json`, the file production applies |
| `scripts/show_georef_twins.py`, `scripts/georef_coast_ceiling.py` | a map's twins drawn; the ceiling of a coast fit given the truth (§10.4) |

---

## 8. Plan

| Step | What | Where it stands |
|---|---|---|
| 1 | The generator (§3) | **done**, v11 |
| 2 | Check it against the real-corpus findings (§7.3) | **done** (§10.2): v10 reproduces F1–F6 and F8 and the signal ranges |
| 3 | Which constants matter (§4.1, §7.4) | **done** (§10.3): three matter, defaults already best |
| 4 | A non-rigid fit driven by the coast, its stiffness picked blind (§4.4) | **done** as the bend (§10.4–10.5); block CV failed, the ridge is fixed |
| 5 | Every candidate on every case: oracle, best fixed, today (§5) | **done** (§10.7): 0.005 IoU of headroom left |
| 6 | Quality estimator (§4.3), then selector (§4.5) | estimator: Q1–Q6 done (§10.10–10.12), not usable in km on real maps; whether to ask for a click, Q8 (§10.13); selector not for now (§4.5) |
| 7 | Validate on the real corpus | **done for `C7`** (§10.9), without historical maps: production since config v22 |

---

## 9. Open questions

- **Click noise.** Drawn 1–8 px, calibrated against the in-fit residual; the `reclick` cases
  should measure it. Real clicks look noisier: 52a1aedc's check points are off by the same
  ~17 px in each of the three layouts that share them, on a map at snapped IoU 0.98 (§10.12).
  Until it is measured, the estimator's km mean nothing on real maps.
- **Historical maps.** The field and the local error are guesses about what historical maps do.
  Two or three historical cases with check points
  ([testing §9](georeferencing-testing.md#9-where-things-stand)) would show which families
  matter and how strong they should be, and are the test the quality estimator most needs.
- **Snapping's floor is in pixels** (5 px, and the 20 px minimum stretch): 0.13% of the diagonal
  on a 3,757 px image, 1.0% on a 486 px one. Measuring how far a map's coast strays (a high
  percentile of the coast distances, not the trimmed mean) would remove it (§10.9).
- **Bad control points.** The bend spreads a wrong point over a sixth of the image (§10.9). The
  pipeline trusts the user's clicks; flagging a point that disagrees with its neighbours is for
  the quality estimator to decide. The affine's leave-one-out cannot (§10.12): drawing distortion
  gives good points ratios as large as bad ones'. Something that knows the deformation (the
  leave-one-out of the bend, or of near neighbours only), or for a SIFT pair whether the two
  features match along the coast, is untried.
- **Inland maps.** Neither corpus has one (§3.7). The estimator's two strongest inputs read the
  coast; without it they are filled and flagged from ~20 runs. A coast-free estimator does
  nearly as well on coastal maps (§10.10), but how the pipeline and the estimator behave on a map
  with no coast, placed from cities alone, is unmeasured: it needs inland regions in the
  generator, and city-only layouts.
- **An added click can make a map worse** in 13% of Q5's cases (§10.11, §10.13). No blind
  guard on the rerun fixes it (§10.14). Why (§10.15): the click changes the affine the bend
  starts from, and on the far side of the map part of the coast starts beyond the bend's 40 px
  reach. Bending the old placement again with the new click, and placing the map again only
  where that bend refuses, halves the maps made worse and gains a third to a half more, on Q5's
  maps and on unseen seeds. In production it needs the previous placement kept with the map;
  not built. What is left: the fallback's own losses (m00786/stress).
- **One click can still break the piecewise fallback.** With the second alignment guarded
  (§10.12), m00712/stress still goes from 53 to ~290 km with one more correct city, before the
  second alignment runs; not looked into.
- **The coarse schedule at ×0.25** ties production on unseen seeds and runs 30% faster (§10.3);
  not tried on the real corpus.
- **The thresholds** of §7 (ties, "matters", 2-to-1) were guesses written before the runs.

---

## 10. Results

What matters from each run, kept here: the `ablations/` folders are not committed. `PROD` is
production at the time of the run: config v21 (align, piecewise, align, the old snapping; now the
variant `P21`) until §10.9, `C7` since. Medians are over maps unless said otherwise.

### 10.1 Found in the pipeline while building the generator (2026-10-27)

- **The keypoint finder lost ~98% of its SIFT detections**, and drew phantom lines across the
  frame: on regional frames it suggested 0–2 points, below the import's minimum of 3. Fixed
  ([history](georeferencing-history.md#2026-10-27--the-keypoint-finder-lost-most-of-its-detections)).
- **Alignment fit the sea-side edge of a thick coastline**, not its centre: ~1.4 px off on a
  perfect map with the coast 2 px wide. Fixed in config v21, within 0.2–0.35 px at every width
  from 0 to 4 px ([history](georeferencing-history.md#2026-10-27--alignment-is-biased-by-the-coastlines-drawn-width)).

### 10.2 Step 2: does the corpus behave like the real one? (2026-10-27)

Runs `synthetic-step2-2026-10-27` (v7), `-v9-` and `-v10-`: seeds 100–139, three twins, 2
layouts, 11 variants, against the real corpus re-run with the fix of §10.1
(`coast-line-centre-2026-10-27`). Read with `analyze_georef_synthetic.py --findings`, `--signals`
and `--checkpoints`.

**How the generator got there.**

| Version | Change | What it showed |
|---|---|---|
| v7 | twins | F1–F3 pass; F5 and F7 do not. The `none` twins 1.5–3× too easy: in-fit residual 4.0 px against the real 6.6 |
| v8 | coast generalisation, first try | void: it clicked SIFT features the map no longer drew, 20–290 px from their truth |
| v9 | generalisation fixed (§3.2) | all eight findings on Mercator `none`; in-fit 4.8 px. The coastal/inland contrast did not move |
| v9 + check points | synthetic check points scored like the real ones | the inland contrast was the metric's: at check points the synthetic inland gain falls from 22% (dense) to 4%, as the real 5%, since an inland check point is a city with its own click error. The coastal gap was real (15–20% against 54%), and three signals were out of range (water agreement, coast-line pairing, chamfer improvement) |
| v10 | the coast drawn three ways; click noise 1–8 px (was 0.5–4) | everything in range (below). A long-wave coast drift, tried first, made alignment pull the interior off, which real maps do not show, and was dropped |

**The findings on v10, `none` twins**, map votes better / worse / tie:

| # | Finding | all 40 maps | Mercator (15) | Holds |
|---|---|---|---|---|
| F1 | `B2` vs `A0` | 27 / 2 / 11 | 13 / 1 / 1 | yes |
| F2 | median px at ×1 → ×10 → ×30 → ×100 | 7.55 → 4.82 → 4.51 → 4.48 | 2.87 → 1.76 → 1.59 → 1.71 | yes |
| F3 | dense gain, coastal / inland | 41% / 33% | 57% / 51% | yes; at check points, by source, as the real maps (SIFT +33% against +45%, cities +8% against +16%) |
| F4 | `A1` vs `A0` | 11 / 19 / 10 | 0 / 11 / 4 | yes |
| F5 | `B3` vs `B2` | 11 / 22 / 7 | 0 / 13 / 2 | yes |
| F6 | `B7b` vs `B2` | 29 / 8 / 3 | 7 / 6 / 2 | yes |
| F7 | `B10` vs `B5b`, radius < 0.5 | 3 / 6 / 15 | 2 / 3 / 4 | no: it needs the affine tens of px off the coast, which few layouts produce, whatever their area |
| F8 | `B4` vs `B2` | 3 / 0 / 37 | 2 / 0 / 13 | yes |

**The signals**, `PROD`, 80 `none` cases against the 17 real ones: every signal in range, the
real cases spread through it (in-fit 5.6 px median against 6.7; clicks moved +0.91 against
+1.24), except three single cases just past what the generator draws by construction: 7 cities
on one case (it draws up to 6), a coast with nothing drawn along it (italie, paired share 0.04),
a 6 px coast line (Japon; it draws up to 4). Accepted: no step-3 result is read as saying
anything about those.

**The deformed twins** did what their mechanisms predicted, except one: piecewise was expected
to tie or lose on `field` and wins clearly (`A1` 31 / 1 / 8). The field varies on a 4 × 4 grid,
slower than the spacing of 7-odd points, so the points sample it and an interpolator follows. And
on `field` the best coastline weight does not drop once the coast is generalised, so the weight
is one constant, not a per-map choice.

**What mattered.** Click noise and how the coast is drawn are what made the synthetic maps
behave like real ones; scoring check points the same way on both was what made them comparable.

### 10.3 Step 3: which constants matter (2026-10-28)

Phase A, `synthetic-step3-A-2026-10-27`: seeds 200–249, three twins, `A0`, `PROD` and stage `S`
(4,200 runs). Phase B, `synthetic-step3-B-2026-10-28`: the same cases, stage `R`'s 30 draws.

| Knob | Phase A |
|---|---|
| `weight_curve` | **kept**: ×1 worse everywhere (+0.59 px, 88 / 32 votes); ×100 worse overall and on small images; ×10 best on every twin |
| `piecewise_influence_radius_ratio_of_diagonal` | **kept**: 0.1 worse on `field` (+0.56); 0.35 better at the coast on conic maps (−0.43) |
| `icp_cutoff_px` | **kept**, narrowly: 10 worse at the coast on maps over 4 km/px |
| the coarse and fine schedules, ICP's reach and orientation, curve sampling, the piecewise frame | frozen: every median within ±0.1 px |

**Phase B**: no draw beats `PROD` anywhere, over all maps, on any twin or at any image size; the
draws nearest it tie. No interaction.

**Result.** `PROD`'s constants sit on a flat optimum: ×10, reach 0.175, cutoff 20 were already
the best values found. No constant depends on the twin. Phase C (seeds 300–349): the coarse
schedule at ×0.25 ties `PROD` on every twin and runs 30% faster, the one usable finding (§9).

### 10.4 Headroom for a coast fit: the stress twin and the ceiling (2026-10-28/29)

Run `synthetic-stress-2026-10-28` (seeds 300–349, four twins) and `scripts/georef_coast_ceiling.py`
on the same cases: a smooth correction (an affine part plus Gaussians on a 6–24 knot grid) fitted
by ridge to the generator's truth, from the control-point affine. `denseMeanPx`:

| | `none` | `field` | `local` | `stress` |
|---|---|---|---|---|
| non-affine part of the warp | 0 | 11.0 | 7.2 | 50.1 |
| `A0` | 6.1 | 15.3 | 12.5 | 49.4 |
| `B5b` (alignment only) | 3.8 | 14.3 | 10.9 | 51.5 |
| `A1` (piecewise only) | 6.8 | 14.1 | 11.8 | 44.8 |
| `PROD` | 4.8 | 12.1 | 10.6 | 43.6 |
| ceiling: the best affine of the truth | 1.5 | 9.3 | 7.5 | 35.1 |
| ceiling: the true correction across the coast, and the control points, one setting | 0.7 | 1.8 | 3.3 | 15.2 |

**What it showed.**
- **Alignment does nothing on stress**: an affine cannot follow a coastline bent by 2–5% of the
  diagonal. All of `PROD`'s gain there is the piecewise step's, and that only recovers what the
  control points see (1% of `A0`'s error with 3 points, 16% with 11 or more).
- **The coast pins down most of the bend.** Seen only across the coast, a smooth fit takes out
  90% of the stress error near the coast and still 58% beyond 10% of the diagonal from it; seeing
  along the coast too adds little. The control points add little on top.
- That is step 4's headroom: 43.6 px against a 15 px bound on stress, 4.8–12.1 against under
  3.3 on the base twins. The bound assumes perfect matches; the pipeline's own matches lose at
  least what alignment already loses (1.5 → 4.8 px on `none`).

### 10.5 Step 4: the bend (2026-10-29/30)

`bend.py` (`coast_bend`) is the ceiling's fit on the pipeline's own matches: the reference coast
pushed into the map through the current model, matched to the detected coast by the alignment's
normal search over shrinking radii, Tukey-reweighted, across the coast only, with the control
points sharing the weight. It refuses if it folds the map, moves it more than 10% of the
diagonal, or makes the coast chamfer worse. How it works now:
[`georeferencing.md` §5.5](georeferencing.md#55-the-bend-to-the-coast).

Tuned on seeds 300–349 (`synthetic-bend-2026-10-29`, `synthetic-weighting-2026-10-29`, a
cross-validation sweep):
- **Loose bends tilt maps that were right** (18 of 50 `none` maps worse at ridge 1e-3 with a
  free affine part); stiff ones keep a sixth of the stress gain.
- **Weighting by noise** (1/σ²: a click at 4 px, a coast match at 2 px discounted over a 20 px
  correlation length) beats a fixed 0.9 share by 0.1–0.3 px on every twin. **More weight on the
  control points does not help inland**: it makes the bend refuse itself ("chamfer got worse"
  goes from 7 maps to 33–38).
- **Block cross-validation does not find the ridge** (§4.4): on the oracle's ridge 3–8 times in
  30 (chance: 4), within a step 14–19 times (chance: 11), and a mean regret of 4.1–7.7 px against
  2.8–5.7 for the best fixed ridge. Removed.

**On unseen seeds** (`synthetic-bend-holdout-2026-10-30`, seeds 400–449, fixed beforehand):

| Variant | What | `none` | `field` | `local` | `stress` | s |
|---|---|---|---|---|---|---|
| `PROD` | | 4.7 | 11.5 | 8.5 | 44.9 | 12.6 |
| `W1` | `PROD`, then the bend (1e-3) | 4.1 · 25/16 | 7.2 · 36/7 | 5.9 · 36/6 | 40.3 · 35/4 | 13.2 |
| `W5` | alignment ×10, then the bend (1e-3), no piecewise step | 4.0 · 31/15 | 6.5 · 44/6 | 6.3 · 36/11 | 32.6 · 37/11 | 6.1 |
| `W7` | `W5` at 3e-3 | **3.0** · 36/9 | **5.7** · 45/3 | 6.6 · 37/9 | 34.7 · **41/6** | 6.2 |

`denseMeanPx`, then votes against `PROD`. **The bend replaces the piecewise step rather than
adding to it**, in half the time, and `W7` is the most even winner. The ridge 3e-4 that the
sweep suggested for `W1` did not confirm.

### 10.6 The real corpus, snapping, and the fallback (2026-10-30/31)

**A false start.** On the real corpus the bend first looked even with `PROD`, and "snapping
takes the same gain" looked like the reason. It was not: `W5`–`W10` were built on `A0`'s
settings, which turn snapping off, so they were compared unsnapped against a snapped `PROD`.
Since then both runners score every variant's zones three ways from the same transform (§3.5).

`W11` is `W7` on production's settings; `W13` adds the fallback: the piecewise step and the
second alignment where the bend refuses (`coast_bend_fallback_piecewise`), which was the one
signal the first selector found (§10.7). Runs `synthetic-fallback-v11-2026-10-30` (seeds
500–549, 196 cases) and `corpus-fallback-2026-10-30` (17 cases). Mean IoU, then votes against
`PROD` (ties under 0.002 synthetic, 0.005 real):

| | synthetic, cleaned | synthetic, snapped | real, cleaned | real, snapped | real check points |
|---|---|---|---|---|---|
| `PROD` | 0.709 | 0.712 | 0.879 | 0.886 | |
| `W1` | 0.753 · 140/38 | 0.742 · 119/52 | 0.887 · 7/1 | 0.891 · 5/2 | 3/4 |
| `W11` | 0.757 · 149/40 | 0.750 · 136/53 | **0.889** · 10/2 | **0.895** · 7/1 | 4/4 |
| `W13` | **0.758** · 142/28 | 0.750 · 129/41 | 0.888 · 8/2 | 0.894 · 5/1 | 3/3 |

**What it showed.**
- **The bend without the piecewise step beats `PROD` on both corpora** once snapping is fair.
  The one real loss was c0d9544d's check points (+34 km), explained in §10.9.
- **The fallback makes it safer at no cost on average.** It applies on 19 of 196 synthetic
  cases; `W13` loses to `PROD` on 41 cases against `W11`'s 53.
- **Snapping costs the bend on synthetic maps** (−0.007 to −0.011) and helps it on real ones:
  where the transform is already close at the coast, the old snapping moved more than it fixed
  (§10.8).
- **The transform and the zones can rank differently**: on stress the dense error preferred the
  bend without the piecewise step and the shipped zones the bend after it. Choices are made on
  the snapped zones since (§3.5).
- **Correcting at the inland control points after the bend does not pay** (`coast_bend_inland`,
  `W8`–`W10`, `W12`, `W14`): it ties or loses on both corpora, and correcting at every point is
  the worst variant on the real corpus. The synthetic layouts then had almost no inland points
  (15% of layouts, real 59%), so generator v11 added the protocol family (§3.4): 58% of protocol
  layouts have one, as the real protocol cases.

### 10.7 Step 5: how much a choice per map could win (2026-10-30/31)

Run `synthetic-step5-v11-2026-10-30`: seeds 500–549, 196 cases from 49 maps, the candidates
`PROD`, `W1`, `W7`, `W8`.

**First measure**: oracle 0.776 against the best fixed (`W7`) 0.757, a headroom of 0.019 IoU,
every candidate best on some cases. It was flattered: `W7` and `W8` were unsnapped (§10.6).

**A first selector did not reach it.** Leave one map out, choosing from the `run_` signals of all
four runs (126 signals): ridge regression did worse than always `W7`; the best single signal and
a threshold took 20% of the two-way headroom. That signal was whether `W7`'s bend applied, a
mechanism rather than a learned choice, and it became the fallback (§10.6).

**Recomputed with the fallback and the new snapping** (2026-10-31, the same 196 cases, all on
the same snapping):

| Candidates | Best fixed | Oracle | Headroom | Cases where another wins by > 0.01 |
|---|---|---|---|---|
| `C3` (`P21` with the new snapping), `C6` (`W13` with it) | `C6` 0.768 | 0.773 | **0.005** (0.47 km) | 24 of 196 |
| the same and `W1` | `C6` 0.768 | 0.780 | 0.012 | 52 of 196 |

`C3` beats `C6` only where the bend applied, spread over every twin and both layout families,
with no signal that picks those cases out. **So no selector for now** (§4.5): the fallback and
the snapping took about three quarters of the headroom.

### 10.8 Snapping that only snaps the coast (2026-10-31)

**Why the old snapping could make things worse.** It moved every boundary vertex within 1.5% of
the image diagonal of the reference coastline to the nearest point on it: 17–160 km on synthetic
maps and 35–220 km on real ones, 40% of the boundary vertices on a median synthetic case, 50–85%
on most real ones. An inland border near the sea moved onto the coast, a border reaching the sea
bent over its last tens of km, and the shore became chords across the coast's bends. On `W13`
it took more than 0.05 IoU off 24 of 196 synthetic cases.

**Two switches** (now on, [`georeferencing.md` §6](georeferencing.md#6-cleaning)):
`coastline_snap_measured`, a tolerance of 3× the coast's measured misfit under the applied
transform, between a floor and the old 1.5%; and `coastline_snap_stretches`, only runs of
consecutive vertices near the coast and along it, onto the coast's own vertices, a polygon left
alone if its area would change by more than 25% (a zone narrower than the tolerance folded onto
the coast in the first run). `C1`–`C3` are `P21` with measured, stretches, both; `C4`–`C6` the
same on `W13`. Each places the same zones as its base.

| Synthetic, 196 cases | cleaned | snapped | snapping's effect | costs > 0.01 | costs > 0.05 |
|---|---|---|---|---|---|
| `P21` | 0.709 | 0.712 | +0.003 | 37 | 10 |
| `C1` measured | 0.709 | 0.716 | +0.007 | 14 | 6 |
| `C2` stretches | 0.709 | 0.721 | +0.012 | 13 | 0 |
| `C3` both | 0.709 | 0.724 | **+0.015** | **1** | **0** |
| `W13` | 0.758 | 0.751 | −0.008 | 53 | 24 |
| `C6` both | 0.758 | **0.768** | **+0.010** | **2** | **0** |

On the real corpus (17 cases), both switches turn snapping's worst case from −0.022 (`P21`) and
−0.014 (`W13`) to +0.001, and its mean effect from +0.006–0.007 to +0.009–0.012. `C6` 0.897
against `P21` 0.886.

**What it showed.** Stretches remove the large losses; the measured tolerance removes the rest.
Snapped this way, snapping costs nothing you could see, so it stays on whatever the transform.
On the real maps the measured misfit is ~1 px, so the floor decides the tolerance (§10.9).

### 10.9 Step 7: `C7` on the real corpus, and production (2026-10-31)

Runs `corpus-step7-c6-2026-10-31`, `synthetic-snapfloor-v11-2026-10-31` and
`corpus-snapfloor-2026-10-31`. The real corpus has a new map, 15df33d7/protocol: hand-drawn
(Mexico and the Gulf), with an extraction error every variant shares; nothing was tuned on it.

**The snap floor.** At 3 px the tolerance was too tight on two maps: the bend placed
44992611/protocol a little worse and the snap recovered less of it (0.818 against `P21`'s
0.851), and on the drawn map the old snapping gained more, a drawn coast straying further from
Natural Earth's than 3 px. Tuned on synthetic maps first:

| Floor | synthetic snapped | vs 3 px (> 0.005) | real snapped | vs 3 px (> 0.002) |
|---|---|---|---|---|
| 3 px (`C6`) | 0.7682 | — | 0.888 | — |
| **5 px (`C7`)** | **0.7685** | 4/0 | 0.894 | 6/2 |
| 8 px | 0.7676 | 5/14 | 0.894 | 9/3 |
| 12 px | 0.7662 | 9/32 | 0.893 | 9/3 |

5 px is free on synthetic maps and takes the real gain (44992611/protocol 0.847, the drawn map
0.743 → 0.756). The floor is in pixels, which is open (§9).

**c0d9544d: one wrong control point.** The bend moved its three check points south (La Serena
−50 km, Salta −88 km). The cause was a SIFT pair drawn at Iquique (−20.2°) but paired with
Antofagasta (−23.66°), 380 km down a coast that runs almost straight north–south: 349 km off
under the affine, against ±100 km for its neighbours. The bend, a smooth field ~960 km wide on
this map, pulled it and its region south; the piecewise step kept it local. Without that point,
`P21` 77.7 km check-point RMS and `C7` 49.9 km (111.4 and 145.5 with it). The point was removed
from the case; the pipeline keeps trusting the user's clicks (§9).

**`C7` against `P21`**, 18 cases, c0d9544d fixed (snapped IoU; check-point RMS on 15 cases):

| Map (cases) | `P21` | `C7` |
|---|---|---|
| 10c029ef (1) | 0.914 | 0.926 |
| 15df33d7, drawn (1) | 0.706 | **0.756**; check points 58.3 → 53.8 km |
| 44992611 (3) | 0.849–0.852 | 0.847–0.876 |
| 52a1aedc (5) | 0.976–0.981 | 0.980–0.981 |
| c0d9544d (1) | 0.624 | **0.753**; check points 77.7 → 49.9 km |
| c4e81e4d (3) | 0.867–0.878 | **0.904–0.915** |
| c858266f (1) | 0.879 | **0.937** |
| f12f2ea4 (3) | 0.842–0.847 | 0.842–0.851 |
| mean | 0.873 | **0.897**: 9 better, none worse by more than 0.005 |
| check-point RMS | 54.4 km | **51.7 km**: 5 better, 2 worse (1 km ties) |
| outline distance | 76.8 km | **75.2 km** |

**Decision (config v22).** `C7` is production: alignment ×10, the bend at ridge 3e-3, the
piecewise step and the second alignment only where the bend refuses, snapping only the coast
with the measured tolerance and a 5 px floor. `P21` keeps the old production as a variant. Not
measured for it: historical maps, and more than 8 real maps.

### 10.10 Q3–Q4: the quality estimator on synthetic maps (2026-11-01)

Datasets `synthetic-quality-{fit-a,fit-b,test}-v11-2026-10-31` (`PROD`, seeds 600–749, four
twins, 5 layouts, 300 scored points per run): 2,945 runs placed, 55 refused for fewer than 3
SIFT suggestions, 883,500 points. Fit `georef-quality-q4-2026-11-01`: 1,470 fit runs (98 maps)
under 10-fold leave-map-out CV, 750 test runs and 725 stress runs scored once by the model
refitted on all fit runs. Errors are in blind pixels (km over the run's own km per pixel); a
factor is exp(median |log error|).

**Per map.** Forward selection picked six inputs, in order: `coastBendMaxPx`, `snapMisfitPx`,
`looAffineRmsPx`, `baselineChamferPx` (negative), `coastlineCoverage`, `inlierFraction`; CV
mean |log| 0.68 → 0.47. Two in-fit signals come first: how far the bend had to move the map and
how badly the coast still fits are the best evidence of error. The affine leave-one-out is
third; the control points' layout was never picked.

| Set | Model | factor | within 2× | rank vs IoU | rank in px | p90 covers |
|---|---|---|---|---|---|---|
| fit (CV) | `rmse_km` as reported | 1.84 | 0.56 | 0.42 | 0.17 | 0.54 |
| | constant | 1.77 | 0.58 | 0.43 | — | 0.82 |
| | `rmse_km` calibrated | 1.74 | 0.58 | 0.44 | 0.13 | 0.82 |
| | **estimator** | **1.45** | **0.77** | **0.64** | **0.71** | **0.85** |
| test | `rmse_km` as reported | 1.72 | 0.60 | 0.47 | 0.22 | 0.54 |
| | constant | 1.66 | 0.65 | 0.36 | — | 0.82 |
| | **estimator** | **1.52** | **0.77** | **0.59** | **0.63** | **0.85** |
| stress | `rmse_km` as reported | 2.42 | 0.40 | 0.28 | 0.15 | 0.25 |
| | constant | 4.46 | 0.14 | 0.31 | — | 0.36 |
| | **estimator** | **1.77** | **0.59** | **0.40** | **0.52** | **0.73** |

"Rank vs IoU" is the Spearman correlation of the predicted median km with 1 − snapped IoU over
runs; "rank in px" of the predicted with the true median in pixels (scale removed: the constant
cannot rank there). "p90 covers" is the share of the scored points within the predicted map p90.
`rmse_km` (in-sample on 96% of runs) ranks no better than the map's scale alone: the constant
ranks maps by km per pixel and gets as far. The estimator beats both everywhere.

Optimism (median true over predicted) is within 0.78–1.07 for every twin, layout family and
control-point count on the fit and test sets. On the stress twin, never seen, it is optimistic
by 1.68 overall and fails §4.3's bar in two slices: open layouts 2.04, 3–5 control points 2.18.

**Per point.** From the map's predicted median, selection added `coastMisfitPx` (missing, no
coast near, is itself an input), `pointsNearby` (negative), `shiftFromAffinePx`,
`coastDistanceRatio`, `insideHull` (negative); nearest-point distance and the nearby
leave-one-out were not picked. Factor 1.93 → 1.74 over the map's median alone; Spearman within a
map between predicted and true error, median over runs, 0.57 on every set. The point p90
(quantile regression) covers 0.90 of the points on fit and test, 0.88–0.92 by family, and 0.73
on stress (0.69 open, 0.77 protocol).

**How much it rests on the coast.** Refitted with the coast-reading inputs removed (the bend,
snapping, chamfer, inliers, coast coverage and displacement, the aligned clicks, which model
applied), selection keeps `looAffineRmsPx`, `nearestGapMedianRatio` and `cityShare`:

| Set | full: factor | rank in px | optimism | coast-free: factor | rank in px | optimism |
|---|---|---|---|---|---|---|
| fit (CV) | 1.45 | 0.71 | 0.97 | 1.57 | 0.55 | 1.00 |
| test | 1.52 | 0.63 | 0.92 | 1.52 | 0.51 | 0.98 |
| stress | 1.77 | 0.52 | 1.68 | 2.21 | 0.45 | 2.17 |

Without the coast it still ranks maps well above `rmse_km` (0.51 against 0.22 on test) and is as
close in size on the base twins; the coast inputs buy ranking, and most of the gain on stress,
where they are what sees the deformation. By thirds of coast coverage the full model is no worse
on the third with least coast (factor 1.44, optimism 1.06), but even that third has a coast
across the frame: no map here, or in the real corpus (coverage 0.005–0.011, mid-range), is
inland (§9).

**Reading.** On the twins it was fitted on, the estimator passes §4.3's synthetic half: it ranks
maps far better than `rmse_km`, its p90 covers 85% per map and 90% per point, and no family is
optimistic by more than 1.07. It is optimistic by about 1.7× on deformation it has not seen,
the stress twin, which is the case real maps are most likely to be in: Q6 decides. Fitting on
stress too would remove that number but leave nothing to measure the next unseen deformation
against.

### 10.11 Q5: one more click (2026-11-01)

Run `synthetic-addpoint-v11-2026-11-01` (`scripts/run_georef_add_point.py`, the Q4 model): seeds
700–749 (the test maps), four twins, layout 0; 186 cases (12 more had no candidate left). Each
case is placed by `PROD`, then again with one more click, as noisy as the layout's and the same
draw for every strategy, on a SIFT suggestion or one of the 40 largest cities, not already used,
near the zones. The gain is log(before / after) of the dense mean error: `1 − after / before`
is bounded for a gain and not for a loss, and a few losses made its means meaningless.

| Strategy | mean gain | median | beats random | losses > 25% | IoU |
|---|---|---|---|---|---|
| estimator (largest predicted error) | **+9.8%** | +5.0% | 109/179 | 5 | +0.013 |
| random | +3.7% | +2.2% | — | 4 | +0.008 |
| farthest from every control point | +8.7% | +5.3% | 110/179 | 7 | +0.011 |
| oracle (largest true error) | +12.6% | +11.0% | | 8 | +0.017 |

Estimator over random, mean log gains, 95% over maps: **2.75 (1.54–13.8)**. By twin: none 1.52
(1.00–3.0), field 3.4 (1.5–8.7), local: random loses on average, stress 1.47 (0.4–8.4). By
layout: open 3.7, protocol 2.1. The estimator's pick is in the true top 10% of candidates 41% of
the time (random 11%, farthest 36%).

**It passes §4.3's bar (1.5× random), but the estimator is not what passes it.** Clicking the
candidate farthest from every point, which needs no estimator, gets +8.7% against +9.8%; where
the two differ (131 cases), the estimator's pick is better in 57. Its edge is on the none and
field twins; on stress, farthest is better. Even the oracle gains only 12.6%: the largest error
is not always where one point fixes most.

**One click can make a map much worse.** 4–8 cases per strategy lost more than 25%, the oracle's
pick included. The worst, m00712/local (two clusters of SIFT points on a near-straight coast,
the bend refused, piecewise): one more correct city took the dense error from 10 to 94 km and
the snapped IoU from 0.75 to 0.37. The control-point affine improved (27 → 24 km); the second
alignment did it, fitting the coast (chamfer 15 → 2.3 px) with a sheared matrix (y scale 2.14)
that pulled the clicks 19 px RMS off (10 px without the added city). Guarded since config v23
(§10.12).

**Reading.** "Add a point here" is worth building, and "far from your points" is most of it; the
estimator can refine the suggestion (higher error near the coast misfit), not replace it. Before
the product suggests a click, the pipeline should not be able to lose this much from one.

### 10.12 Q6, and the second alignment's guard (2026-11-01)

**The guard (config v23).** Scratch probe `ablations/front-probe-2026-11-01.json`: every Q3 run
whose bend fell back to the piecewise step (255 applied the second alignment), and Q5's m00712
cases, placed again with the model going into the second alignment and coming out kept. On the
Q3 runs it is about neutral (dense error ×0.976 geometric mean; 94 better and 66 worse by more
than 5%), and its fronts are small: stretch (singular-value ratio) 1.014 median, 1.13 at p99;
the clicks, which the piecewise step pins, pulled off by 0.25% of the diagonal (RMS) median,
0.85% at p99, 1.32% at most. Four fronts stretched more than 1.3, and their shape does not say
which ones hurt:

| Run | stretch | corners moved (of the diagonal) | clicks pulled off | dense error |
|---|---|---|---|---|
| m00734/local l01 | 4.37 | 1.38 | 0.82% | 100 → 86 km |
| m00712/local l00 | 1.52 | 0.19 | 1.32% | 23.5 → 10.1 km |
| m00712/local l00, one more city (Q5) | 3.34 | 0.89 | **2.45%** | 20.2 → 94.0 km |
| m00712/local l00, another city (Q5) | 1.34 | 0.14 | 0.93% | 27.1 → 28.6 km |

How far it pulls the clicks does. `post_align_max_gcp_shift_ratio_of_diagonal` = 0.02 refuses
a front whose clicks' RMS rises by more than 2% of the diagonal, the first alignment's
`control_points_held` (5%) made tighter because this start already sits on the clicks. It
refuses none of the 255 runs, nothing on the real corpus (6 px at most, `corpus-step7-c6`), and
the m00712 front: that case now ends at 20.2 km. It rests on that one harmful front; the margin
is 1.5× above the largest pull seen and 1.2× below it.

**Q6.** Run `georef-quality-q6-2026-11-01` (`scripts/run_georef_quality_corpus.py`, the Q4
model, `PROD` at v22): 28 cases, 18 regression and 10 probes, among them
c0d9544d/protocol-iquique (the regression case with its wrong SIFT pair put back). The one inland
map, e14c0fdb (Mongolia), has no framing box and cannot run. 114 check points on 15 regression
cases.

Ranking the 18 regression cases (Spearman; few maps: 8, several cases each):

| | vs check-point median | vs check-point RMS | vs snapped IoU |
|---|---|---|---|
| estimator, map median | +0.39 | +0.45 | **+0.73** |
| `rmse_km` as reported | **+0.55** | **+0.67** | +0.25 |

At the check points it is **2.5× optimistic** (median measured / predicted; 2.7 on SIFT check
points, 2.4 on cities), within 2× on 39%, its p90 covering 54% (the bar: 80–95%; 20% on the
worst case). It ranks points across maps (+0.50) but hardly within one (+0.18). Two things
make up the gap, and neither is something the estimator can see:

- **The check points' own error.** 52a1aedc places at snapped IoU 0.98 and a predicted 2–3 km,
  yet the five check points three of its layouts share measure about 5, 23, 20, 4 and 23 km in
  each, while the placement changes from one layout to the next: that error belongs to the
  points. The control points disagree by about as much (leave-one-out median 12–19 km, ~12 px).
  Real clicks or pairings look noisier than the generator's 1–8 px (§9), so the check points
  cannot check anything below ~20 km here.
- **Drawing distortion inland.** On 44992611 the inland cities are off by 100–260 km (Chita,
  Nanchang, Zhengzhou, Shenyang), the same in all three layouts: the map draws them there.
  Predicted 10–35 km. No twin distorts a map's interior this much, and nothing blind reads it
  away from the clicks. The stress twin was 1.7× optimistic (§10.10); real maps are worse.

**Flagging a point.** The leave-one-out residual under the control-point affine, over the
median of the map's:

| ratio | synthetic: bad point flagged, and the largest | clean layouts with a flag | real regression cases with a flag |
|---|---|---|---|
| ≥ 2 | 0.39 | 0.61 | 12 / 18 |
| ≥ 3 | 0.24 | 0.24 | 5 / 18 |
| ≥ 4 | 0.10 | 0.09 | 2 / 18 |
| ≥ 6 | 0.04 | 0.02 | 0 / 18 |

On 2,832 synthetic layouts (189 with a bad point, a SIFT mismatch 20–80 px along the coast) a
flag catches bad points no more often than it flags clean layouts. The bad point has the
largest ratio in 48% of its layouts, a median 1.9. On c0d9544d/protocol-iquique the Iquique pair *is* the
largest, 412 km off, but at 2.7: five regression cases have a good point above that (up to
5.2 on f12f2ea4/minimal). Drawing distortion makes good points disagree with an affine as much
as a mismatch does.

**Reading.** The estimator does not pass §4.3's bar on real maps. It ranks maps by snapped IoU
better than `rmse_km` does, but its kilometres are 2.5× low, and the flag does not work. Per
point it is what Q5 used ("far from your points, near a poor coast fit"), and that does not
need km. Before a number is shown: measure real click noise (the `reclick` cases) and widen the
generator's noise and interior distortion until the twins are as optimistic as the real
corpus, then refit; or calibrate on real check points once there are more maps than 8.

### 10.13 Q8: whether to ask for a click at all (2026-11-01)

Q5's cases, by snapped IoU before the extra click (the "farthest" pick; the others alike):

| IoU before | cases | mean change | helped / hurt (by > 0.01) |
|---|---|---|---|
| < 0.60 | 30 | +0.051 | 19 / 1 |
| 0.60–0.75 | 32 | +0.012 | 11 / 3 |
| 0.75–0.85 | 45 | +0.003 | 15 / 10 |
| 0.85–0.90 | 28 | −0.001 | 6 / 8 |
| ≥ 0.90 | 51 | +0.000 | 5 / 2 |

So what to predict is whether a map is below ~0.75, not its km. Run
`georef-success-q8-2026-11-01` (`scripts/fit_georef_success.py`): the target is log(1 − snapped
IoU), on the Q3 runs, the same folds and selection as Q4, the stress twin held out. New inputs:
the extracted zones' sizes in pixels, known before placement (`quality.zone_sizes`: the
equivalent radius and 2·area/perimeter, about a long zone's width), and per zone Q4's point
model at the scored points inside it (`zone_errors`), over its size, and as a disc's IoU
(`disc_iou`). Selection kept two: **the mean over zones of predicted error over width**
(+0.866), and the median width (+0.113). IoU is the error relative to the zone, and nothing else
the run knows adds to that.

| | test (750 runs) | stress (725, held out) |
|---|---|---|
| median \|IoU error\| | 0.033 | 0.109 |
| median true − predicted | −0.006 | −0.100 |
| AUC, bad (< 0.75) against good: success model | **0.89** | **0.88** |
| … Q4's map median, px | 0.79 | 0.62 |
| … `rmse_km` as reported | 0.66 | 0.66 |

Asking on the test runs where the prediction is below a threshold:

| ask below | maps asked | bad maps caught | asks to maps ≥ 0.85 | bad among the rest |
|---|---|---|---|---|
| 0.75 | 15% | 46% | 11% | 13% |
| 0.80 | 28% | 74% | 9% | 8% |
| 0.85 | 47% | 97% | 12% | 1% |

On stress, where 75% of maps are bad, it is 0.10 optimistic but ranks as well: at 0.80 it asks
68% and catches 82% of the bad ones, 1% of its asks going to good maps.

**As a policy, on Q5's cases** (the "farthest" click, where the prediction says to ask):

| ask below | asked | mean IoU gain where asked | hurt where asked | gain kept (of asking every map) |
|---|---|---|---|---|
| 0.70 | 25 / 186 | +0.054 | 1 | 65% |
| 0.80 | 76 / 186 | +0.022 | 13 | 81% |
| 0.85 | 99 / 186 | +0.017 | 17 | 82% |
| everywhere | 186 | +0.011 | 24 | 100% |

**The real corpus** (`georef-success-q8-real-2026-11-01`, the corpus script with `--success`;
zones as extracted, Q4's point model at 300 pixels sampled inside them): rank against snapped
IoU **+0.86** on the 18 regression cases, real − predicted −0.012 median (−0.098 to +0.058).
The most optimistic are c0d9544d (0.851 predicted, 0.753 real) and 15df33d7 (0.837, 0.756;
its zones carry extraction error, §10.9), and the Iquique probe (0.844, 0.697): one wrong
point is invisible to it, as it is to the flag (§10.12). No regression case is below 0.75, so
the real corpus checks the ranking and the level, not the decision. Two probes without expected
zones would be asked at 0.75 (278e5083/ville2 0.67, vlle 0.70).

**Reading.** Unlike the km, this transfers: zone size carries most of the information, and the
error estimate only needs to be right relative to it. A threshold of 0.75–0.80 asks a fifth to a
third of maps and keeps most of the gain. Before Q7: the guarded rerun (§9, §10.14), so an ask
that goes wrong cannot ship a worse map; and more real maps with expected zones, below 0.75.

**In production since.** `quality.predict_quality` runs after every placement of the zones
(`MapPlacement.georeference`, before the check points are measured) and records
`errors.predictedQuality`: `iou`, `mapMedianPx` and `mapMedianKm` (Q4's median, its km 2.5× low
on real maps, §10.12), `zones`, `zoneErrorOverWidth`, `zoneWidthMedianPx` and `modelVersion`.
The models are `georeferencing/quality_model.json`, written from the two `model.json` by
`fit_georef_success.py --ship`; `MAP_FEATURES`, `POINT_FEATURES` and `zone_features` moved into
`quality.py`, so the fitting scripts and production read the same definitions. On the real
corpus the recorded IoU equals the run above to the fourth decimal on all 27 cases. An import
does not store it with the map yet: it is logged and in the task's result
(`predicted_quality`).

### 10.14 The guarded rerun (2026-11-01)

Runs `synthetic-addpoint-guard-2026-11-01` (seeds 700–749, Q5's maps, 186 cases) and
`synthetic-addpoint-guard-holdout-2026-11-01` (seeds 750–799, unseen, 174 cases); Q5's runner
with its `guard_` columns, the four twins, layout 0. A guard keeps the placement with the new
click, or falls back to the one without it, from what the run reads blind: the predicted IoU
before and after (`errors.predictedQuality`), the coast fit (`snapMisfitPx`), and how far the
new placement moves the map from the old one, in the old affine's pixels, at the new click, at
the old control points, and at zone pixels more than 15% of the diagonal from the click; and
how far the old placement put the click from where it was clicked (its "surprise"). Rules were
chosen on the first set and read on the second. The "farthest" click, where the predicted IoU
asks (< 0.80):

| guard | kept | mean IoU gain | hurt (> 0.01) | helped | worst |
|---|---|---|---|---|---|
| plain rerun | 1.00 / 1.00 | +0.022 / **+0.048** | 14 / 14 | 30 / 41 | −0.037 / −0.143 |
| predicted IoU not lower | 0.77 / 0.79 | +0.017 / +0.032 | 11 / 10 | 24 / 34 | −0.037 / −0.143 |
| coast fit not worse by 25% | 1.00 / 1.00 | as plain | | | |
| far change ≤ change at the click | 0.72 / 0.77 | +0.021 / +0.046 | **5 / 8** | 25 / 36 | −0.034 / −0.143 |
| old points move ≤ 2 px | 0.41 / 0.23 | +0.001 / +0.002 | 8 / 6 | 7 / 5 | |
| click surprise ≥ 12 px | 0.51 / 0.74 | +0.023 / +0.047 | **2 / 7** | 25 / 35 | −0.034 / −0.143 |

(design set / unseen set; 79 and 70 cases.) Over every case, and for the estimator's pick, the
same: no guard raises the mean gain on the unseen set, and none stops the largest losses.

- **No blind guard beats keeping the click.** The best two halve the maps that get worse at
  about 2–5% of the gain, and the threshold of the surprise rule (12 px) was chosen on the
  first set: on the second it removes half the losses, not six in seven.
- **The largest losses pass every guard.** m00786/stress (estimator's pick, −0.28) and
  m00763/stress (−0.14) keep the bend both times, the click is 15–23 px off the old placement,
  the dense error hardly changes, and the predicted IoU rises (0.25 → 0.46 on m00786): the
  zones move where the predictor sees no harm. About half of all losses come with a better
  dense error (5 of 24 on the first set, 13 of 24 on the second): the click improves the map
  on average and costs some zones.
- **The predicted IoU cannot referee its own click.** It rises by 0.002 (median) where the
  click hurts and 0.013 where it helps; the coast fit barely moves either way, so its guard
  never fires.
- What the guards do say: a click the old placement already agrees with (within ~12 px) adds
  little, and a change that reaches farther from the click than at it is suspect.

**Reading.** Asking where the predicted IoU is below 0.80 and keeping the click is still worth
it (+0.022 and +0.048 mean IoU where asked, 30–41 maps helped against 14 hurt); no guard
belongs in production on this evidence. What the losses need is the pipeline's, not a
referee's: why one correct click makes the bend move zones it should not (the stress twin, as
m00712/stress in §9), or a correction local to the new click instead of a refit (§9).

### 10.15 Why a click hurts, and the warm-started bend (2026-11-02/03)

**Why.** Scratch probes on the largest losses of §10.14, each placed three ways: as before the
click, placed again with it, and with the old alignment kept and the click only in the bend.
- **The loss is far from the click.** m00763/stress (−0.14): Indonesia, near the click, gains
  (0.625 → 0.681); Thailand (0.81 → 0.51) and Burma (0.72 → 0.02), at 0.74–0.86 of the
  diagonal from it, lose it. m00771/stress: the near zone −0.03, the far one −0.14. The dense
  error, weighted by area, hardly moves or improves (42 → 43 km, 53 → 37 km).
- **The click moves where the bend starts.** The alignment refits with the click; on a map an
  affine cannot follow, that trades the far side for the near one. The true coast misfit at the
  bend's start, more than half the diagonal from the click: m00763 20 → 36 px median, the share
  within the bend's first search radius (40 px) 0.87 → 0.69; m00771 88 → 118 px. The bend ends
  there at 9 → 23 px and 28 → 37 px: what starts out of reach is not matched, and the ridge
  keeps the correction small where nothing pulls.
- **Some losses are the click's noise.** m00712/local: the old placement is 0.5 km off at the
  new click's spot and the click 12 px off it (layout noise 5.4 px); anything that follows the
  click loses (−0.07 placed again).

**A bump at the click** (`synthetic-addpoint-local-2026-11-02`, seeds 700–749, every case):
the old placement kept, a Gaussian bump at the new click pulling it to where it was clicked,
over 5–25% of the diagonal, alone or held at zero on the old points. It loses to placing again
everywhere (asked, farthest pick: +0.004 at best against +0.022), its worst cases are worse
(−0.16 to −0.29 against −0.04), and the field and none twins lose most. The losses are the
click's noise: in the 15 worst, the old placement was 2–5 px off at the click and the click
9–18 px. A bump believes one click completely; placing again shares it among the points, and
the bend weighs it as a 4 px measurement. And most of what a click adds is global: on the field
and none twins it improves the affine everywhere, which no local correction can.

**The warm-started bend** (`synthetic-addpoint-warm-2026-11-02`, seeds 700–749, `--asked-only`,
79 cases): `bend_to_coast` on the old applied model, the new click among the control points.
The far coast starts where the old bend left it, the coast holds the map wherever it is seen,
the click weighs what the bend gives a click. Where it refuses (§5.5's safeguards), the old
placement; "warm, else rerun" places the map again there instead.

| pick | placement | mean IoU gain | hurt (> 0.01) | helped | worst | dense gain |
|---|---|---|---|---|---|---|
| farthest | plain rerun | +0.022 | 14 | 30 | −0.037 | +0.057 |
| farthest | warm | +0.028 | 3 | 41 | −0.024 | +0.106 |
| farthest | **warm, else rerun** | **+0.034** | 6 | 47 | −0.028 | +0.108 |
| estimator | plain rerun | +0.022 | 15 | 30 | −0.037 | +0.072 |
| estimator | warm | +0.028 | **0** | 41 | −0.010 | +0.109 |
| estimator | **warm, else rerun** | **+0.036** | 4 | 48 | −0.027 | +0.118 |

Dense gain: mean log(before / after). By twin (farthest, warm else rerun against the rerun):
none +0.030 / +0.024, field +0.002 / +0.000, local +0.013 / −0.004, stress +0.058 / +0.040.
The warm bend refuses on the big gains the rerun finds (m00712/none: it would move the map more
than 10% of the diagonal; placed again, +0.25), which is what the fallback is for.

**On unseen seeds** (`synthetic-addpoint-warm-holdout-2026-11-03`, seeds 750–799, 70 asked
cases, the rule fixed beforehand: warm, else rerun):

| pick | placement | mean IoU gain | hurt (> 0.01) | helped | worst | dense gain |
|---|---|---|---|---|---|---|
| farthest | plain rerun | +0.048 | 14 | 41 | −0.143 | +0.231 |
| farthest | warm | +0.040 | 4 | 44 | −0.053 | +0.218 |
| farthest | **warm, else rerun** | **+0.064** | 6 | 56 | −0.053 | +0.305 |
| estimator | plain rerun | +0.041 | 12 | 44 | −0.281 | +0.189 |
| estimator | warm | +0.037 | 3 | 45 | −0.053 | +0.190 |
| estimator | **warm, else rerun** | **+0.050** | 6 | 54 | −0.281 | +0.264 |

By twin (farthest, warm else rerun against the rerun): none +0.038 / +0.029, field +0.048 /
+0.032, local +0.040 / +0.033, stress +0.088 / +0.067. The warm bend refuses on 15–16 of 70.

- **It confirms.** A third more IoU gained than placing again, half the maps made worse, and
  the farthest pick's worst loss −0.05 instead of −0.14; better on every twin.
- **The warm bend alone is the safest and gains less** (3–4 hurt, worst −0.05), as on the
  first set: the fallback is where the gain is, and where what is left of the risk is.
  m00786/stress (estimator's pick, −0.28) is a refusal placed again: the same loss as §10.14.
- **Farthest beats the estimator's pick again** (§10.11), with the warm bend too.

**Reading.** "Add a point here" should bend the previous placement again with the new point,
and place the map again from scratch only where that bend refuses. In production that needs the
previous applied model kept with the map (it is in the run record, not in the database), and
the re-import to start from it; not built.
