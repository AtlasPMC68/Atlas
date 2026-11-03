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

## 2026-10-07 — Alignment on everywhere, and the checks redesigned

- **Alignment on in every container, at ×10.** The suite, the dev-test UI and the CLI now run
  the production configuration, so a regression `best` measures what ships. ×10 rather than the
  ×30 the sweep favoured: it takes most of the gain (10 of 12 cases better, the 2 worse within
  0.7 km) and leaves the control points more say inland, where ×30 helps least.
- **Alignment needs an identified coastline.** The question that matters is whether the curves
  being matched are the right ones. The water filter answers it (only edges on the water/land
  boundary), so alignment now runs only with water picks and a water mask covering at least 1%
  of the image. Before, a map without them aligned on every edge left, borders and rivers
  included, with only the robust loss in the way. Every corpus case already had a water pick
  (Mongolie, landlocked, is a probe), so no measured result depended on that path.
- **The probe, eight gates and the recovery ladder removed; four lenient checks instead.**
  They were designed when the shared-loss bug made alignment a coastline-only fit that could
  wander off (2026-09-30); after the fix, every corpus run passed at the first attempt, the
  gates were neutralised, and the probe cost a second full fit per import (0.4–2.8 s, as much
  as the alignment) for a gate that could not fail. Kept: the mirror check and "the coast did
  not get worse". Added: water agreement relative to the control-point affine (an absolute
  0.7 would have been a coin flip on central africa at 0.73) and how far the fit moves the
  user's clicks. Thresholds set far beyond anything measured (clicks: 5% of the diagonal
  against a measured +0.4–3.6 px), because the precondition does the real work.
- **The chamfer stays.** With the coastline identified, its role is reach, and the ICP-only
  variants (`B7`/`B8` then, now `B9`/`B10`; `enable_chamfer` off) showed it is needed: ICP alone was worse on 9 of
  14 cases at ×10, most on clustered control points, where the coast away from the points
  starts beyond ICP's radius ([testing §8.9](georeferencing-testing.md#89-icp-only-2026-10-07)).
- **Also removed:** the rivers layer (loaded, never used), the `label` text fill (worse on every
  case), unused switches. SIFT keypoint suggestions prefer the coastline and use lakes only to
  fill where the coast leaves the frame uncovered (a map may omit a lake, never its coast).

## 2026-10-08 — Local piecewise between two alignments

- **Local piecewise.** `piecewise_regularization: local` lays zero-correction anchors wherever
  the nearest control point is far, so a point's correction fades out instead of reaching
  across the map. It beat plain piecewise on top of alignment (`B3La/b/c` vs `B3`); reach
  0.175 of the diagonal was the most even across maps, 0.25 about the same as `none`.
- **Align again after the correction** (`align_after_piecewise`, `post_align.py`): an affine
  fitted in front of the piecewise model. A gain over the same piecewise without it (`B7` vs
  `B3Lb`), and the ×10 coastline weight helps it as it helped `B2` (`B7a/b`).
- **New defaults (config v20):** `B7b`, align → local piecewise → align at ×10, the best mean
  raw IoU of every variant: 14 cases better than `B2`, 3 worse, with the largest gains on the
  maps placed worst. The losses (about 0.01 IoU) are on maps the affine already fits; `auto`
  is the switch to try for gating them away.
- **Merged with `main`.** The second alignment ran on the recovery ladder's staged fit, which
  `main` had removed (2026-10-07); it now uses the same `gates.fit_stages` as the first
  alignment, so it also follows `enable_chamfer`. The ICP-only variants were renamed `B9`/`B10`
  to free `B7`/`B8` for the variants above.
- **Telea text inpainting removed.** It split ink by brightness and filled it with
  `cv2.inpaint`, a weighted average that can blend two zone colours; the palette repaint did
  better consistently. With it went `text_inpaint_algo` and `text_inpaint_radius_px`.

## 2026-10-27 — The synthetic corpus, step 1

The generator of [`georeferencing-synthetic.md`](georeferencing-synthetic.md) §3, built in one
pass (generator v1) and revised four times after looking at its maps and its first pilot. What
it is now is in that document; what changed, and why, is here, so the current values are not
argued again.

| Was (v1) | Now (v5) | Why |
|---|---|---|
| Longitude span 4°–40° (median 12.6°) | 5°–90° (median ~21°) | Most maps looked zoomed in next to the real corpus (~20°–50°) |
| Land 20–85% of the image, sea ≥ 5% | No minimum; coast amounts recorded | Every map is centred on a coast; the minimum rejected maps for nothing |
| Mercator drawn 50% of the time (~12% easy maps) | 30% (~7%) | Too many easy maps |
| Image 900–2000 px | 500–2000 px | The real corpus goes down to 602 px, and the coarse schedule is suspected too wide for small maps |
| Framing box padded 5–20% per side | 5–10% | Closer to how a user frames; a wider box puts fewer suggestions on the map |
| Countries only, zones from 1% of the image | Countries or provinces from what the map shows; zones from 0.1% | Countries alone rejected regional maps of large countries; at 1% a map of East Asia lost Japan and Korea |
| Provinces always merged by Natural Earth group | Merged only when too small to pick | Canada's groups lump three territories into "Northern Canada" |
| 3–15 points, a uniform share of cities | At least 3 SIFT pairs (from 60% of the suggestions to all), cities none 60% of the time, else 1–6 | The import requires 3 SIFT pairs and makes cities optional; a uniform share made a third of layouts mostly cities |
| Soft concentration: a centre anywhere, weights `exp(−(d/r)²)` | A hard circle, centred where suggestions are dense, radius 30%–100% | Soft weights spilled clustered layouts over the whole map; a random centre could hold no suggestion; from 15%, a quarter of layouts were clipped to exactly 3 points (median 4 SIFT pairs) |
| Bad point on 15%: a random 15–30 px jump, or a wrong city | 5%: a SIFT pair matched to the neighbouring feature, 20–80 px along the drawn coast | A random jump models nothing; a wrong city almost never happens; a mismatched cape is the realistic gross error |

Building it also found two pipeline defects, the two entries below.

## 2026-10-27 — The keypoint finder lost most of its detections

Found by the first synthetic maps ([`georeferencing-synthetic.md`](georeferencing-synthetic.md)),
which call the finder exactly as the import does: on regional frames it suggested 0–2 points,
and the import requires 3 pairs, so a user framing Portugal to Morocco could not get past the
SIFT step. Three defects, all in `sift_key_points_finder.py`:

- **The mask.** SIFT could only place keypoints on the Canny outline of the drawn 3 px line,
  1 px wide, and SIFT centres a keypoint on what it finds, rarely exactly there. On 52
  synthetic frames: a median of 10 detections per frame, 20 frames under 6. With the outline
  widened by 5 px: a median of ~460, none under 6. Every synthetic map now gets 5–13
  suggestions inside its image.
- **Phantom lines.** The finder had its own rasterizer, the one `reference.py` replaced in
  Step 1: it dropped vertices outside the box and joined what was left, drawing a straight line
  from where a coast leaves the frame to where it comes back. With few detections this rarely
  mattered; with hundreds, farthest-point sampling would pick exactly such isolated, invented
  lines. Lines are now clipped to the box with the reference grid.
- **Off the curve.** A keypoint sits anywhere on the drawn line, up to half its width off the
  curve, and its lon/lat becomes the control point's true position (1.5 px is ~6 km on a 40°
  frame). Each suggestion is now snapped onto the vector curve.

Stored cases keep the lon/lat their SIFT pairs were clicked with; only new suggestions change.
Known since: tiny isolated islands (Bermuda, Malta, the Bonin Islands) are strong SIFT blobs
and farthest-point sampling favours them, though a map may well omit them.

## 2026-10-27 — Alignment is biased by the coastline's drawn width

Found by the synthetic generator's convention test
([`georeferencing-synthetic.md` §3.5](georeferencing-synthetic.md#35-the-metric)): a map with
no deformation and exact clicks, aligned (affine, no piecewise). With the coast drawn 1 px
wide, alignment leaves it exactly in place (0.00 km). Drawn 2 px wide, it moves it by 1.4 px on
average (11.7 km at 8.2 km/px): a 0.1–0.3% scale change plus a shift, up to 2.7 px at a corner.
A graticule on the same map changed nothing (11.66 km without it).

The cause: the water filter keeps only the edges on the water/land boundary, which for a thick
coastline is its **sea-side** edge, while the reference coastline is the line's centre. The fit
pulls the map so the reference sits on that edge, about half the line's width seaward. Scanned
maps draw coasts 2–5 px wide, so production alignment carries the same systematic error, a few
km on a typical map: small next to the tens of km measured on the corpus, but systematic, and
larger on small-scale maps.

**Measured, then fixed (config v21).** Canny does find both flanks of the drawn line; the water
filter keeps edges within `edge_water_margin_px` (3) of the water, and from a 2 px line on, the
land-side flank lies beyond it (at +4–5 px for 2 px, +6–7 px for 3–4 px). The fix
(`evidence.centre_drawn_coast_lines`) pairs each kept edge with the nearest edge whose grey
gradient along the coast's normal has the opposite sign, and puts the evidence at their
midpoint, the line's centre whatever the blur or the Canny thresholds. Three things went wrong
on the way, each found by measuring the evidence against the true drawn coast:

- **The land-side flank paired as well.** When the line is thin, both flanks pass the water
  filter; the land-side one, left unclaimed, paired with whatever lay further inland and pulled
  the evidence landward. Now an edge whose opposite flank is on its *sea* side is a land-side
  flank and is dropped.
- **Marching along the normal missed flanks**: a ray slips between the diagonal pixels of an
  8-connected edge. Replaced by a nearest-pixel distance transform per gradient sign.
- **Merged strokes.** Where coast strokes merge into a dark mass 9–15 px wide (dense islands,
  deltas, narrow channels), a quarter of the sea-side flanks at 3–4 px found no partner within
  8 px and stayed on the sea side. An edge whose opposite flank is landward but beyond the
  line's width (up to twice it) is now dropped: neither side of that mass is the coast.

Midpoints falling on a half pixel mark the pixels on both sides, rather than rounding every
point of a straight run the same way.

On the undeformed synthetic map, aligned (affine), error in px:

| Coast drawn | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Sea-side flank (before) | refused | refused | 0.97 | 1.23 | 1.35 |
| Both flanks, margin 8 (`L3`) | refused | refused | 0.63 | 1.29 | 1.35 |
| Line centre (v21) | 0.21 | 0.24 | 0.35 | 0.28 | 0.30 |

**The earlier "0.00 km at 1 px" was alignment refused**, not alignment holding: on a map whose
clicks are exact, the old evidence made the chamfer slightly worse than the clicks did, so
`curve_fit_engaged` failed and the exact-click affine was used. With the line's centre,
alignment engages at every width. The 0.2–0.35 px left is the fit's own floor on this map (the
chamfer at the true position is ~0.55 px), not a bias: the evidence's median offset from the
drawn coast is −0.4 to +0.2 px at every width, against −0.8 to −2.8 px before. Widening the
water margin to keep both flanks (`L3`) is not a fix: the chamfer then settles on either flank.

The generator now draws the coast 0–4 px wide (v6; it drew 1–2), so the synthetic corpus has
coasts drawn as a colour change and thick ones.

**On the real corpus it is neutral** ([testing §8.10](georeferencing-testing.md#810-the-coast-lines-centre-2026-10-27)):
`B5b` against the same configuration on the sea-side flank, 5 cases better and 6 worse on check
points, median +0.04 km; `PROD`, 6 and 5, +0.01 km. Those maps draw their coasts 1–2 px wide
(median flank gap 2.2–3.0 px), where the bias was already under a pixel. Kept because scanned
and historical coasts are thicker, and because the synthetic corpus needs evidence that is
right at every width; it costs ~0.3 s per aligned run.

## Considered and set aside

| Idea | Why not |
|---|---|
| Toponym water cues | Cut from the plan; accepted consequence: a map with an unpainted sea has no water evidence |
| Keeping glyph components partly under a label | A letter touching the coast merges with it |
| Rivers as alignment evidence | Thin, dense, often schematic; the layer was removed (2026-10-07) |
| Persisting the fitted matrix | Refitting is cheap; the inputs were what got lost |
| Homography (8 parameters) | Inputs are digital renders, not photographs: the extra freedom would absorb drawing noise |
| A full planar arrangement for zones | Zones are already an exact pixel partition; shared borders can be made at vectorising time |
| A synthetic test corpus | Set aside until the configuration space outgrew the real corpus; built 2026-10-27 ([`georeferencing-synthetic.md`](georeferencing-synthetic.md)) |
