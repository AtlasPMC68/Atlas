# Georeferencing — roadmap

What to do next, ranked by what the measurements say. Each item states why (with evidence
where there is any), what it would be, and what result would justify it. Nothing here is
built unless it says so. How the pipeline works today: [`georeferencing.md`](georeferencing.md);
the evidence: [`georeferencing-testing.md` §8](georeferencing-testing.md#8-results); earlier
reasoning: [`georeferencing-history.md`](georeferencing-history.md).

Rewritten 2026-10-05, after the first corpus run. The earlier roadmap (written before any
testing) is in git history; its still-valid ideas are folded in below.

---

## 1. Before the pull request

Listed in [`georeferencing.md` §10](georeferencing.md#10-before-the-pull-request): settle the
production defaults, make CI and the dev-test UI run that same configuration, remove the debug
dumps, and remove what only served experiments. The two default changes expected from the
first run are items 2 and the coastline weight (×30, pending item 3's test on historical maps).

---

## 2. Transform model: affine by default, piecewise by leave-one-out

**Why.** Piecewise does not beat the affine on the modern corpus (6 better, 5 worse) and makes
alignment worse (`B3` < `B2` on 8 of 12). It should still win where a map has real local
distortion and enough points, which is the historical case. So: affine by default, and
piecewise only where the map's own control points show it predicts better.

**What.** For a map with n control points:

1. For each point, fit without it and measure how far the model places it (leave-one-out).
   Piecewise already computes this; the affine's is closed form (PRESS), one fit.
2. Use piecewise only if its leave-one-out RMS is clearly lower, e.g. 20% lower, **and** n is
   at least ~8. Otherwise the affine.
3. Record both numbers and the choice in the run record.

**It will not always choose right.** With 5–10 points the estimate is noisy and one bad click
swings it; it measures error where the control points are (coasts, cities), not where the
zones are; and a point on the hull, once left out, has to be extrapolated, the hardest case for
both models. Hence the margin and the minimum: when unsure, the affine, which is today's floor.

**Proof.** An `AUTO` variant in the runner, judged on city check points across the corpus,
historical maps included: it must do at least as well as always-affine. Two models are only
distinguishable when the difference in held-out error exceeds the standard error of that
difference; take the simpler one otherwise.

---

## 3. A smoothed non-rigid warp driven by the coastline

**Why.** One affine cannot fit a map's coast and interior together when the map is distorted:
at a high coastline weight, coastal check points improve a lot (116 → 45 km) and inland ones
barely (108 → 100 km), with individual cities going either way and central africa's zones
losing IoU. A warp that can follow the coast **locally** would let the coastline fix the coasts,
the cities fix the interior, and smoothness fill between them. East asia (no affine fits, 20–60
km in-fit error) needs a smooth global model of the same family.

**What.** After alignment, starting from the aligned affine, fit a smoothed thin-plate spline
(or a grid-based warp) to the control points **and** the coastline correspondences ICP already
produces, with a bending penalty λ:

- λ → ∞ gives back the affine exactly, λ = 0 interpolates every point; λ is chosen from the
  data, so noise-like residuals give the affine;
- bend at a coarse grid of knots (~8×8), not at every sample;
- stiffness can vary with evidence (stiff where there is no data, flexible along a
  well-constrained coast), the λ(x) field of the old roadmap.

**What makes it different from a control point.** A coastline sample only constrains the
direction across the coast, not along it (it can slide along a smooth coast), its pairing is
recomputed every iteration, and neighbouring samples are not independent: 30,000 samples carry
roughly the information of a few hundred points, all on the coast.

**Safeguards**, each falling back to the affine (the earlier spline was dropped for wild
extrapolation; [history](georeferencing-history.md#starting-point-main-before-the-branch-2026-09-19)):

1. too few control points (fewer than ~6–8): no correction at all;
2. λ by cross-validation over **contiguous blocks** of coastline, not random samples (coastline
   samples are autocorrelated, so random folds and GCV pick λ too small and undersmooth; GCV is
   fine only as a starting value);
3. a cap on displacement (a few % of the map);
4. no fold: `det J > 0` checked on a fine grid;
5. the correction fades to zero away from the evidence.

**The new risk:** the map's own drawing errors. A simplified or misdrawn bay gets "fixed" by
bending the land around it. City check points are the judge.

**Proof.** Inland (city) check points improve without coastal ones getting worse, on modern and
historical maps. A global smooth model (2nd-order polynomial, or fitting in a conic projection)
should be tested on east asia first: it is the cheapest member of the family.

---

## 4. Zones that touch stay touching

**Why.** Neighbouring zones are vectorised and snapped independently, so a drawn border line
leaves a gap between two zones and snapping can move one side only. Maps like Maghreb tile
countries against each other.

**What, in order:**

1. **Fix gap fill** (`zone_gap_fill`, built, off). Likely cause of its bad score: it vectorises
   pixel by pixel and keeps every isolated speck. Drop tiny components before vectorising, then
   rerun `E2`.
2. **Keep shared borders through cleaning:** simplify the zones as one set (already done on the
   gap-fill path), snap only edges facing the coast, never a shared border, and clip the set as
   a whole.
3. **A fidelity check after cleaning:** compare each shared border with its transformed pixel
   version, and put the pixel version back where cleaning damaged it, gated by their
   similarity. This repairs topology, not placement: the output border *is* the pixel border
   transformed, so comparing the two cannot correct the transform. Correcting placement from
   inner borders needs an independent reference (a modern borders dataset), so it would only
   work on modern maps.
4. **An adjacency metric:** for zones that touch in the expected zones, the gap and overlap
   area between them in the output.

**Proof.** The adjacency metric improves and boundary distance does not get worse.

---

## 5. Extraction: colour collisions

**Why.** Countries the user did not pick, painted in a picked colour, are classified into the
picked zone (Sudan into "Algérie"). It is a production bug, and it dominates zone metrics on
Maghreb and east asia ([testing §8.6](georeferencing-testing.md#86-colour-collisions-distort-zone-metrics)).

**What.** Tie a zone to where it was picked: keep the connected regions that contain or touch a
pick (a zone made of several pieces gets several picks), or let the user exclude a region.
Possibly a minimum piece size.

**Proof.** The extracted→expected boundary direction drops to the level of the other direction
on Maghreb and east asia.

---

## 6. The gates and the ladder

**Why.** Neutralised since config v13; every corpus run settled at rung 0, and alignment made no
case worse, so the gate values have nothing to predict. By the decision rule they do not earn
their place yet.

**What.** Decide before the PR: remove them (with ladder rungs 1–3), or keep them logged-only
until historical maps give them failures to predict. If kept: compute the probe per rung
(today it is computed once, so the main gate cannot change between rungs) and multi-start
around the image centre, not pixel (0, 0).

---

## 7. Snapping that knows what it snaps to

**Why.** Snapping helps the shipped output (9 of 12) but is blind: nearest point, no
orientation, no confidence. A zone edge near a graticule or a parallel coast snaps just as
readily.

**What.** Promote zone edges that run consistently close to the warped coastline (or rivers) to
constraints, with the ICP orientation test and confidence weights that already exist, and
refit; or simply add an orientation test to today's snap. Worth doing after items 2–3, since a
better transform leaves snapping less to fix.

---

## 8. Telling the user how good the result is

- **An accuracy estimate per map, in km**, from the leave-one-out of item 2 ("placement ≈ ±40
  km") instead of a silent answer.
- **A confidence overlay**: distance to the nearest constraint combined with how much the warp
  moved things there.
- **Active control-point suggestion**: point at the worst region and ask for one more click
  there; the user stops when the map stops being red.
- A **fidelity slider** exposing λ (rubber-sheet to reality ↔ respect the drawing) is a product
  decision, not a technical one.

---

## 9. Smaller items

- **σ per source from residuals.** Equal today. Before making them differ, normalise the
  control-point term by the sum of weights rather than count and median σ.
- **Constants on small maps.** The coarse schedule (64 px blur, 400 px cutoff) is wider than a
  602×375 map. A ~4× smaller schedule was suggested on `Quebec_1791` before the bug fixes and
  never tested after them.
- **Separate the water filter's effect:** a variant with `edge_water_filter` off.
- **Gazetteer reach:** historical and small places (GeoNames `PPLH`/`PPLQ`); suggesting the
  city step's names from OCR.
- **Keypoint finder:** decide on the always-on lakes "testing modification".
- **A lockfile** for transitive dependencies (numpy drift once moved IoU by 0.0008).

---

## 10. Further out: corpora, offline tuning, learning

- **Corpora.** Modern maps with borders as ground truth now exist (the old "Corpus A", built by
  hand in the editor rather than by OCR). **Historical maps with check points** are the next
  and most important corpus: the target regime. A synthetic corpus (rendered maps under known
  warps) was set aside as too costly; if ever built, it must inject coherent errors (a shifted
  coastal arc, an invented peninsula), not just noise, or it tests the optimiser rather than
  the problem.
- **Offline tuning.** Every annealing schedule, tolerance and threshold is still a guess. The
  run record and the variant runner are the inputs for tuning them as a set against
  check-point error.
- **Learning**, only with a large corpus: predict λ or refinement from the map's appearance;
  classify the map's projection. Not before the methods above have been tested.
