# Georeferencing — history and reasoning

Why the pipeline is shaped the way it is: what was decided, on what evidence, what was tried
and dropped, and which numbers were later found to be wrong. Dated entries, oldest first. For
what the code does now, see [`georeferencing.md`](georeferencing.md); for the measurements,
[`georeferencing-testing.md`](georeferencing-testing.md).

This replaces five earlier documents (`georeferencing-current.md`, `-plan.md`,
`-experiments.md`, `-fixes.md`, `city-gcps.md`). Their full text, build logs included, is in
git history: `git log --diff-filter=D -- dev-docs/georeferencing-plan.md` gives the commit that
removed it, and `git show <that commit>^:dev-docs/georeferencing-plan.md` prints it.

**Numbers from before 2026-09-30 are not measurements of alignment** (see that entry). They are
kept only where the reasoning depends on them.

---

## Starting point: `main` before the branch (2026-09-19)

- The user matched ≥ 3 SIFT keypoints (suggested on a render of the reference coastline) to
  their map; one **affine** was fitted pixel → EPSG:3857 by least squares; zone vertices near
  the coastline were snapped onto it; zones were clipped to land; output in EPSG:4326.
- **An earlier thin-plate spline had been replaced by that affine**, according to the old
  `AffineTransformation` docstring: the spline passed exactly through every control point but
  extrapolated wildly outside their hull and distorted map corners. Any non-rigid model must
  answer this (see the roadmap's smoothed warp).
- The land mask was, and still is, built by polygonising the coastline with the world boundary
  and marking faces containing an ocean seed point as ocean (there is no land polygon file).
- Quirks found then, all fixed since: the reported error was in Mercator units and per
  coordinate component (`pip_7sift`'s "10,979 m" is 9.09 km of ground), and 0 with exactly 3
  points; the framing box was collected and thrown away; nothing about a map's
  georeferencing was stored; the snap tolerance depended on where the zones sat.
- One test case, `pip_7sift`, IoU ≈ 0.94.

## The goal and the principles (2026-09-19)

**The question:** does adding reference-coastline evidence to the user's control points
improve placement over the control points alone? The two are **complementary, never
alternatives**: control points are sparse but certain and spread over the map; the coastline is
dense but exists only along the coast. The shipped fit uses both. A coastline-only fit exists
only as a diagnostic (the probe).

**Principles:**

- **Non-regression.** The control-point affine is the floor; alignment must pass checks to be
  used and falls back otherwise.
- **Measurable before clever.** No algorithm change without a number from the harness.
- **Forward-compatible shapes, not forward-built features.** Adopt a shape now when
  retrofitting it would touch every call site (per-point weights, a regularizer argument, one
  versioned config dataclass, a structured run record); do not build the feature until needed.

## Steps 0–3: plumbing that changed no output (2026-09-19 → 20)

- **A direct script** (`scripts/run_georef_alignment.py`, `georef-dev` service) and a
  **structured run record**: an IoU number cannot say which stage moved it, and the record is
  what any later tuning consumes.
- **Store the inputs, not the fitted matrix** (`maps.georef_inputs`): refitting is cheap, and
  what was actually lost after an import was the clicks.
- **Honest units:** km on the ground, `1/cos φ` at the framing box centre, RMS of point
  distances; error unknown, not 0, with exactly 3 points.
- **Framing box and a separate water pipette** reach the backend. Water is separate because
  zones and sea are often the same hue (Leclerc: blue Nouvelle-France, white Atlantic).
- **Reference rasters: the rasterizer was rewritten.** The old one dropped out-of-box vertices
  instead of clipping, so a line leaving and re-entering the box was joined by a straight
  phantom segment: harmless for SIFT suggestions, poison for a distance field that cannot tell
  an invented edge from a coast.
- **Lake interiors count as land** (land = not ocean, right for clipping); a water comparison
  needs `water = ocean | lakes`.
- **Straight lines are down-weighted, not deleted** (neatlines, graticules, frames are the main
  wrong-feature attractors; a real coast can run straight for a while).
- **OCR is mandatory for alignment.** Masking OCR boxes removed ~50% of the edge pixels on the
  test map: half the "evidence" was place names. Masked text is treated as **no data**, not as
  empty space: deleting glyphs punches holes in the coastline under labels, and the distance to
  the next surviving edge would be a structured error (p95 ≈ 76 km there). Keeping components
  only partly under a label was tried and rejected: a letter touching the coast merges with it.
- **Toponym water cues** (*Baie*, *Lac*, *Mer*) were cut entirely: on a map with an unpainted
  sea there is simply no water evidence.
- **Dependencies:** an image rebuilt with a newer numpy changed `pip_7sift`'s IoU by 0.0008,
  the size of the effects being measured. numpy, OpenCV and others were pinned. Torch and
  transitive dependencies still drift; a lockfile is the real fix.

## Step 4: curve alignment (2026-09-20 → 23)

**Design**, still the design today ([`georeferencing.md` §5.2](georeferencing.md#52-curve-alignment)):

- **Tukey, not Huber.** On schematic maps a large share of the drawn outline matches nothing
  real; Huber down-weights outliers, Tukey rejects them, which is what is needed past ~30%
  outliers. scipy has no Tukey, so it is hand-written.
- **Annealed chamfer** from a wide blur to a sharp one, to have a basin of attraction.
- **ICP inside the first version, not later.** Straight-line suppression catches only ~22% of
  edge pixels; what remains is long curved linework with no reference counterpart (rivers,
  roads, borders following watersheds). Only an orientation test separates those from a coast.
- **A probe**, the same fit without control points, as an independent trust measure: you
  cannot check a fit against the points it was fitted to.
- **Named gates, all logged on every run**, and a **recovery ladder** whose main response is a
  dial (raise the control-point weight), not a switch. Rungs 4–6 (similarity, water-only arcs,
  regional acceptance) were never built: no case could exercise them.

**The first number was noise.** Alignment measured +0.003 IoU with blind snapping still on.
Translating one transform by a few pixels showed why:

| shift (px) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 |
|---|---|---|---|---|---|---|---|---|
| snapping on | .9414 | .9408 | .9412 | .9410 | .9403 | **.9289** | .9392 | .9377 |
| snapping off | .9260 | .9265 | .9267 | .9264 | .9259 | .9250 | .9237 | .9203 |

Snapping corrects transform error after the fact: it flatters the baseline and hides
improvements. Rule ever since: **judge placement before cleaning.** That became the raw score
(2026-10-03); snapping itself was later shown to help the shipped output (2026-10-04).

**Coastline first, rivers out.** On a second map the starting transform was too far off for
the chamfer to reach the coast. Alignment was staged (coastline alone with a much wider
schedule, 64 px blur / 400 px cutoff, then lakes, then ICP), rivers were dropped as evidence
(thin, dense, often schematic), and `curve_fit_engaged` was added: a fit that never moved had
passed every gate, because nothing drifted.

**Switched on in the app, off in the suite**, so the app could be judged by hand while the
suite kept measuring the floor and stayed fast (OCR per case). Per-run debug dumps were added
for the same manual evaluation, as throwaway.

## Step 5: cities as control points (2026-09-22 → 23)

- **The source is on every point**, and a city carries its GeoNames id: needed to weight by
  source, report error by source, run one source alone, and refuse the same city twice.
- **σ is configuration, not data**, and **equal for both sources.** The plan assumed cities an
  order of magnitude noisier; but a SIFT point is a user matching an abstract coastline shape,
  and which source is noisier is for residuals to say. Per-source error is reported for that.
- **Cities pin the piecewise correction** too (they are trusted equally).
- **The gazetteer is a SQLite file queried by the framing box** (`cities15000`, alternate names
  in Latin script): loading geonamescache's whole JSON into every process was the
  alternative. Pinned like reference data, because its version changes the cities.
- **Unknown names return nothing** (the plan said to fall back to a manual click): a city not
  in the box is not on the map, and a historical name the gazetteer lacks is simply not used.

## Keypoint suggestions: farthest-point sampling (2026-09-23)

The keypoint finder kept the strongest keypoints at least D px apart: one radius trying to both
spread the points and fill the request, and failing at one or the other. It now seeds with the
strongest and repeatedly takes the candidate farthest from those chosen. On a Quebec box: closest
pair 33 → 103 px, mean nearest 107 → 165 px. Clustered control points make the affine badly
conditioned.

## Piecewise affine (2026-09-23)

Added as a model choice: the affine plus a Delaunay correction pinned at each control point and
decaying to zero on a frame around the map. Continuous everywhere, and plain affine outside the
frame, which is what the old spline got wrong. On `Quebec_1791` (6 points), leave-one-out:
affine 172 km, piecewise 157 km; on Italy the reverse (43.6 vs 47.4 km). Known from the start:
it interpolates rather than averages, so it reproduces a bad click. It was made the default
during the "tryhard" runs (config v13), together with neutralised gates, `inpaint` text fill
and wide ICP values, **without a measurement**; that is why the first corpus run tested it.

## 2026-09-30 — Three bugs that shaped every earlier number

1. **One robust loss for two kinds of residuals.** Control points and curve samples went
   through one scipy `loss` with one scale sized for the curve samples, so a control point was
   "an outlier" past `cutoff × sqrt(n_gcp / n_samples)`: 0.7 px in the fine stages. On
   historical maps the control points disagree with any affine by 10–24 px, so they exerted no
   pull at all: the "joint" fit was a coastline-only fit, and ladder rung 3 (raise the control
   point weight) made them drop out sooner. **Fix:** control points are plain least squares;
   only the curve term is Tukey (`tukey_residual`, `loss="linear"`).
2. **Reference samples off the image read the border.** Lookups clamped to the nearest pixel,
   so the map's drawn frame attracted every off-map sample, and inlier fractions counted samples
   nobody could see. Two obvious fixes were wrong and the tests caught both: costing unseen
   samples 0 lets the fit push the whole coast off the map; costing them the outlier constant
   lets it pull off-map coast into view. **Fix:** a frozen set of samples in view per annealing
   level (as ICP does with correspondences); fractions over samples in view.
3. **Piecewise:** its reported leave-one-out held the base affine fixed, and that base had been
   fitted with the held-out point (30–40% too optimistic, ≈0 km with 3 points); its frame
   enclosed the zones only, so a control point beyond them broke continuity; long edges were
   not densified. All three fixed; the error kind is now labelled.

Also: ICP back to 40 → 5 px / 30° / 20 px (the wide "tryhard" values had been compensating for
bugs 1–2, and 60° lets crossing lines through); run record schema 2; three old cases migrated
(they had been running with **no** control points).

**After the fixes**, at equal weights the joint fit stayed within ~1 px of the control-point
affine on every case: **the coastline weight became the real dial.** The probe agreed far better
with the clicks (UK 53.5 → 5.6 px). **Invalidated:** every alignment number before this date,
including the +0.004 IoU of Step 4, the Quebec_1791 gate failures, and the "tryhard" runs.

## 2026-10-02 → 03 — The test plan and its tooling

Details in [`georeferencing-testing.md`](georeferencing-testing.md) §3–§7. The decisions:

- **Check points are a separate list, not a role on control points**, so no fitting stage can
  ever see one by a missed filter. SIFT pairs can be check points too.
- **Boundary distance on outlines only, in 3D.** Measuring holes made lakes the pipeline cuts
  out look like 30 km border errors on a zone whose border was 4 km off.
- **Lakes and ocean:** the pipeline cuts both out of zones and that stays (production
  behaviour); expected zones are cut by the same mask before the shipped output is scored. The
  raw output is scored against the zones as drawn, for placement.
- **Expected zones from Natural Earth borders**, loaded and cut by hand in the editor. The
  older idea of identifying zones automatically by OCR was not needed for a first corpus.
- **Regression cases only offer the cleaning switches** in the UI; anything else belongs to
  exploration cases, so a regression best stays comparable.

## 2026-10-04 — First corpus run

Twelve cases on four modern maps, every variant, then a coastline weight sweep. Full results and
verdicts: [testing §8](georeferencing-testing.md#8-results). In short: alignment helps and ships;
the weight helps up to ×30, but mostly at the coast; ICP earns its place; snapping helps the
shipped output; piecewise does not beat the affine, so the expected change is affine by default
with piecewise chosen per map by leave-one-out; colour collisions distort zone metrics on maps
that reuse colours.

## 2026-10-05 — One pipeline, fallbacks and tests trimmed

- **One pipeline core** (`extraction_steps.place_map`): the import task, the dev-test task,
  the CLI and the variant runner had each assembled "select points, align, georeference"
  themselves. The dev-test task now runs a case from its `config.json` and the test's stored
  image instead of receiving every input and the image bytes as task arguments. A re-run of
  the variant runner reproduced all 90 compared metrics of the corpus run exactly.
- **Fallbacks for inputs that are now always present removed:** a framing box derived from
  the control points, a reference latitude from the control points, a snap tolerance from the
  zones' extent, alignment without OCR boxes, city detection without a frame, pipette picks
  without a kind, probes replaying without a legend answer, georeferencing failures turned
  into unplaced features, and the replacement of best runs from score version 1.
- **About 330 tests trimmed to about 85**, keeping those that pin stored-data contracts, bugs
  that happened, and the core geometry; the regression suite covers the pipeline end to end.

## Considered and set aside

| Idea | Why not |
|---|---|
| Toponym water cues | Cut from the plan; accepted consequence: a map with an unpainted sea has no water evidence |
| Keeping glyph components partly under a label | A letter touching the coast merges with it |
| Rivers as alignment evidence | Thin, dense, often schematic; loaded but unused |
| Persisting the fitted matrix | Refitting is cheap; the inputs were what got lost |
| Homography (8 parameters) | Inputs are digital renders, not photographs: the extra freedom would absorb drawing noise |
| A full planar arrangement for zones | Zones are already an exact pixel partition; shared borders can be made at vectorising time |
| A synthetic test corpus | More effort than the project can spend; real maps with borders as ground truth came first |
