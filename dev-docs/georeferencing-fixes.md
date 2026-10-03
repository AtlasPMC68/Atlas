# Georeferencing — bug fixes and the state they leave

Written 2026-09-30 on `georef-exp`. Three bugs in the georeferencing code went unnoticed
through Steps 4–5 and the experiments that followed. Each one made the code do something
other than what the plan and the docstrings said it did, and two of them shaped every
alignment number measured so far. This document explains each bug, the fix, how the fix
was checked, what it changed on the real cases, and what the pipeline does now.

Companion documents: [`georeferencing-plan.md`](georeferencing-plan.md) (the design these
bugs departed from), [`georeferencing-experiments.md`](georeferencing-experiments.md) (the
measurements they affected).

---

## Summary

| # | Bug | What it did | Fix |
|---|---|---|---|
| 1 | Control points and curve samples shared one robust loss | Control points were rejected in the fine stages, so the "joint" fit was a coastline-only fit; recovery rung 3 did the opposite of its purpose | Control points are plain least squares; Tukey applies to the curve term only |
| 2 | Reference samples off the image read the border | Coastline outside the map pulled the fit toward the image frame; the inlier fraction counted samples nobody could see | Off-image means "unseen"; each annealing level fits a frozen set of visible samples; fractions count samples in view |
| 3 | Piecewise model: optimistic error, misplaced frame, no densification | Reported leave-one-out error was 30–40% too low (≈0 km with 3 points); a control point outside the zones broke continuity; long edges were not bent by the correction | Honest leave-one-out; frame around image + zones + points; geometries densified before a piecewise warp |

Also in this change: the ICP settings go back to their pre-"tryhard" values, the run record
names its models unambiguously, three old-format test cases are migrated, and the tests that
were failing on the config defaults are fixed.

---

## 1. One robust loss for two kinds of residuals

### What the code did

The alignment objective has two terms ([plan §8.1](georeferencing-plan.md#81-alignment--staged)):
control points, which should always pull, and thousands of curve samples, which should be
robust because much of a drawn coast is invented. Both went into a single
`scipy.optimize.least_squares` call with `loss=tukey_loss` and one `f_scale`.

scipy applies that loss to **every** residual. The `f_scale` was sized for the curve term
(`cutoff × sqrt(w_curve / n_samples)`), while the control-point residuals were scaled by
`sqrt(w_gcp / n_gcp)`. So a control point was treated as an outlier as soon as its error
exceeded `cutoff × sqrt(n_gcp / n_samples)`:

| Stage | Curve cutoff (px) | Effective control-point cutoff (6 points, ~4,000 samples) |
|---|---|---|
| Coarse | 400 → 110 | 15.6 → 4.3 px |
| Fine | 70 → 18 | 2.7 → **0.7 px** |

On the historical maps the control points disagree with any affine by 10–24 px, which is the
map being drawn wrong rather than bad clicking. They were rejected from the first level on.
Beyond the cutoff Tukey's derivative is exactly zero, so they exerted no pull at all.

Consequences:

- **The joint fit was a curve-only fit.** It started from the control-point affine and was
  then pulled by the coastline alone. That is why, in every run record, the aligned model sat
  close to the probe (which ignores the control points by design) and far from the clicks.
- **Recovery rung 3 was inverted.** "Raise the control-point weight ×8" multiplied their
  residuals by √8, which shrank their effective cutoff by √8, so they dropped out sooner.
- **The probe gate compared the curve-only fit with a second curve-only fit.**

### The fix

The control-point term is now plain least squares: every point pulls in proportion to its
error, however large. The curve term alone is robust. It goes through
`tukey_residual(r, c) = c · sqrt(2 · ρ((r/c)²))`, whose square is exactly the Tukey cost, and
the solver runs with `loss="linear"`. This is how two terms get two different losses inside
one `least_squares` call. ([align.py](../Backend-Atlas/app/utils/georeferencing/align.py),
`tukey_residual`, `_residuals`, `_gcp_term`)

The weighting is unchanged: each term is normalised by its own count, and control points are
weighted by `(median σ / σ)²` within theirs. `weight_gcp` and `weight_curve` are now genuine
relative weights rather than being overridden by the cutoff. Rung 3 now pulls harder, as
designed.

---

## 2. Reference samples off the image

### What the code did

The framing box is usually larger than the scanned map, so many reference coastline samples
project outside the image. The objective looked up the distance field and the validity field
for every sample with clamping to the nearest pixel. A sample 200 px off the map therefore
read the distance at the closest border pixel. Map scans usually have a drawn frame there, so
the frame became an attractor for every off-map sample. The neatline-suppression work
(plan §7) exists precisely to stop that kind of pull.

The inlier fraction also divided by **all** samples, so a correct fit on a map that showed
half its framing box reported ~50% "inliers". The 0.09 on Quebec_1791
([experiments §4](georeferencing-experiments.md)) was mostly this.

### The fix, and two fixes that were wrong first

- **Validity is 0 on the image border**, ramping to 1 over 3 px inwards. Lookups still clamp,
  so anything off the image now reads "unseen", and the ramp keeps the objective smooth.
- **What an unseen sample costs matters, and both obvious answers are wrong.** Each was
  tried, and the tests caught both:
  - Cost **0** (what the old `d · v` did under labels): the cheapest fit is to push the whole
    reference coast off the map. The test fit did exactly that, ending with no sample in view.
  - Cost **= the saturated outlier cost**: the cheapest fit squeezes off-map coast *into* view
    wherever it can land on any line. That drifted 11 px with a shear on a perfect start.
- **The fix that holds is a frozen active set per annealing level**, which is what ICP
  already does with its correspondences. The samples in view at the start of a level are the
  evidence for that level. An active sample that leaves view during the solve costs the
  outlier constant, and an inactive one is not in the objective at all. Neither hiding samples
  nor recruiting new ones changes the cost. The set is recomputed at the next level. The curve
  term is normalised by the active count, so it does not weaken against the control points
  just because the framing box is wide.
- **Inlier fractions are over samples in view**, for the chamfer and for ICP. Both phases
  report `samplesInView`.

---

## 3. The piecewise model

### a. The reported error was not leave-one-out

The pipeline always handed the piecewise model its base affine, and a supplied base is held
fixed in every leave-one-out fold. That base had been fitted with all points, *including the
one being held out*, so each "held-out" point had already shaped the affine it was measured
against. Measured on the cases (km, ground):

| Case | Affine LOO | Piecewise LOO, honest | Piecewise as reported (fixed base) |
|---|---|---|---|
| `test-5-sift-points-peut-etre` | 172.3 | 156.9 | **101.9** |
| `test_piece_wise_affine` | 224.6 | 208.2 | **130.6** |
| `test_with_lake` | 279.2 | 240.4 | **179.8** |
| `italy_test_tryhard` | 43.6 | 47.4 | **39.3** |

With exactly 3 points the base passes through every point, so the reported error was ~0 km.
That is the false confidence `rmse_status` was introduced to prevent, and it was one of the
10 failing tests.

The comparison in [experiments §6](georeferencing-experiments.md) (172.3 vs 156.9 km) was
computed separately and honestly, and it stands. What was wrong was the number every run
reported: the run record, `rmse_km` on each feature, and the per-source error in the dev tool.
Note that the honest numbers do **not** favour piecewise everywhere: on the Italy map it is
worse than the affine.

**Fix:** when the base is the control-point affine, the piecewise model refits it itself
(identically) and every fold refits it without the held-out point. When the base is the
aligned model, it cannot be refitted without the image and the whole alignment, so it stays
fixed and the error is labelled `leave_one_out_fixed_base`. Every model and run record says
which kind it reports (`rmse3857Kind`, `gcpRmseKind`).

### b. The frame did not enclose the control points

The correction is pinned to zero on a padded frame. That frame was padded around the
**zones'** extent. With zones covering part of the map and a control point beyond them, the
triangulation reached past the frame, and the model jumped from "corrected" to "plain affine"
at the hull: a seam, exactly what piecewise was chosen to avoid. **Fix:** the frame pads the
union of the image, the zones and the control points.

### c. Long edges were not bent

Only vertices are warped. A straight edge crossing several triangles stayed straight and cut
across the correction. The model's own docstring said to densify first, but nothing did.
**Fix:** before a piecewise warp, geometries are segmentized to 1% of the image diagonal
(`piecewise_densify_ratio_of_diagonal`). The affine maps lines to lines and is not densified,
so its output is unchanged.

---

## 4. Also in this change

- **ICP back to its reference values:** search 40 → 5 px, orientation tolerance 30°, cutoff
  20 px. The v13 values (100 px, 60°, 100 px) were set during the "tryhard" runs, while bugs 1
  and 2 were active, and were compensating for them. At 60° the orientation filter lets most
  crossing lines through, and that filter is the reason ICP exists. The wide values are a test
  variant, not the reference.
- **The gates are still neutralised**, and the config now says so accurately. What can still
  reject an alignment: a mirrored transform, a non-converged optimiser, and `curve_fit_engaged`
  at 0.0, which fails only when the coastline chamfer got *worse*. Every gate is logged on
  every run; whether to keep them is for the test results to decide.
- **Run record schema 2.** `models.gcp_affine` (the control-point baseline, always),
  `models.aligned_affine` (when alignment used the curves) and `models.applied` (what the
  features were placed with). Schema 1 stored the applied model under the misleading name
  `stage2_affine`, plus a duplicate `chosen`, and never the baseline. The records on disk were
  migrated once; the baseline was refitted from each record's own control points.
- **Three cases migrated** from the old `imagePoints` / `worldPoints` format to
  `controlPoints` (all SIFT): `italy_test_tryhard`, `test_on_uk_map_tryhard`,
  `test_with_lake`. They had been running with **0 control points**. They are also the only
  cases with alignment runs on record.
- **Tests.** The 10 tests failing on the config defaults now pass. The gate tests run under
  the designed thresholds explicitly, since the defaults are neutralised. 14 new tests pin the
  three bugs; all 14 fail on the pre-fix code.
- `CONFIG_VERSION` 13 → 14.

---

## 5. What changed on the real cases

Every runnable case, aligned with the pre-fix code and v13 ICP values (what the app ran),
then with the fixed code and the reference ICP values. All distances are in image pixels,
measured against the user's control points.

| Case | Control-point affine | Aligned, before | Aligned, after | Probe, before | Probe, after | Coast moved, before → after |
|---|---|---|---|---|---|---|
| `italy_test_tryhard` | 19.99 | 30.89 | 19.92 | 36.02 | 21.46 | 22.8 → 2.9 |
| `test-5-sift-points-peut-etre` | 10.32 | 16.99 | 10.28 | 23.06 | 11.02 | 14.2 → 1.9 |
| `test_piece_wise_affine` | 15.74 | 21.68 | 15.59 | 20.03 | 19.10 | 14.0 → 2.3 |
| `test_with_lake` | 23.72 | 35.28 | *rejected* | 39.77 | 27.43 | 19.0 → — |
| `ville2` | 23.51 | 31.67 | 22.98 | 43.16 | 25.96 | 16.0 → 4.1 |
| `vlle` | 22.12 | 80.57 | 21.72 | 68.62 | 26.14 | 58.0 → 4.1 |
| `1st` | 18.37 | 53.96 | 17.34 | 51.89 | 31.35 | 44.5 → 5.9 |
| `bite` | 3.99 | 22.21 | 4.00 | 20.57 | 7.18 | 24.6 → 0.3 |
| `test_on_uk_map_tryhard` | 2.35 | 5.79 | 2.51 | 53.54 | 5.62 | 4.9 → 0.9 |

"Probe" is the curve-only fit (no control points). "Coast moved" is the median distance the
reference coastline moved from the control-point affine. *Rejected*: the chamfer got worse,
so `curve_fit_engaged` sent the run to the control-point affine.

How to read it:

- **Before, the aligned model followed the probe**, not the clicks: 1.4–5.6× the
  control-point error, and up to 58 px of movement. That was bug 1.
- **After, the joint fit stays within about 1 px of the control-point affine**, moving the
  coast 0.3–6 px. With `weight_gcp = weight_curve = 1` and control points that disagree with
  the map by 10–24 px, the control points now dominate. How much the coastline *should* be
  allowed to move the map is a weighting question (`weight_curve`), and now a real one.
- **The probe agrees far better with the clicks** (UK 53.5 → 5.6 px, `vlle` 68.6 → 26.1 px).
  The probe has no control points, so this comes entirely from bug 2: off-map coastline had
  been dragging it toward the image frame.
- **None of these numbers measures quality.** Distance to the control points is in-sample:
  those points are in the fit. Whether the map got better needs check points or ground truth.

**What this invalidates:** every alignment conclusion before this change.

- The +0.004 IoU of [plan §8c](georeferencing-plan.md) was a curve-only fit.
- The gate failures in [experiments §4](georeferencing-experiments.md) were measured on a
  curve-only fit with border-dragged samples.
- The "tryhard" probe runs (Italy, UK, `test_with_lake`) moved the map by the amounts in the
  "before" column for the same reason.

Output of runs **without** alignment and with the `affine` model is unchanged. The
`piecewise_affine` output changes wherever the frame or densification differs.

---

## 6. The state now

### The flow

Unchanged in shape (see [plan §8b, "What the pipeline does now"](georeferencing-plan.md)):

1. Fit the control-point affine.
2. Optionally align against the coastline (probe, joint fit, gates, ladder).
3. Optionally apply the piecewise correction on whichever affine came out.
4. Snap, clip to land, cut out lakes, convert to EPSG:4326.

What each step now does:

| Step | Now |
|---|---|
| Joint fit | Control points pull with plain least squares; curve samples are Tukey-robust; each annealing level fits a frozen set of samples in view; off-image and under-label samples cost an outlier constant |
| ICP | 30° orientation filter, 40 → 5 px search, 20 px cutoff on the point distance; inlier fraction over samples in view |
| Probe | Curve evidence only, same frozen-set rule; still starts from the control-point affine |
| Piecewise | Frame around image ∪ zones ∪ control points; geometries densified to 1% of the diagonal; honest leave-one-out on the control-point base, `leave_one_out_fixed_base` on the aligned one |
| Run record (schema 2) | `gcp_affine`, `aligned_affine`, `applied`; `gcpRmseKind` says which error is reported |

### Defaults (config v14)

| Setting | Value | Note |
|---|---|---|
| `enable_curve_alignment` | off in the file, **on** in `backend` and `celery-worker` via `GEOREF_ENABLE_CURVE_ALIGNMENT` | unchanged |
| `snap_to_coastline` | on | unchanged; judge alignment with it off |
| `transform_model` | `piecewise_affine` | unchanged; the honest numbers do not favour it on every map |
| `text_fill_method` | `inpaint` | unchanged |
| Gates | neutralised except determinant, convergence, chamfer-got-worse | now documented as such |
| `weight_gcp` / `weight_curve` | 1 / 1 | the balance that now decides how far alignment moves the map |

### Still open, by decision rather than oversight

- **The ladder cannot recover from its main gate**: the probe is computed once, so
  `probe_gcp_disagreement` has the same value on every rung. Also, the multi-start rotates
  around pixel (0, 0) rather than the image centre. Both are unreachable while the gates are
  neutral. Fix them only if the gates are kept.
- **The probe starts from the control-point affine**, so with weak coastline evidence it
  stays near the clicks and "agrees" with them. It measures drift, not independent agreement.
- **Piecewise after alignment re-pins every click**, undoing the coastline fit near each
  control point. A design question for the tests.
- **Lakes are cut out of zones** in the pipeline (`subtract_lakes`), contrary to plan §6b. A
  convention to settle, and to apply to ground truth too.
- **`pip_7sift`, the only scored case, has no framing box or legend answer** and stays
  blocked until someone completes it ("Compléter les entrées" on its result page keeps its
  SIFT points). Several probe cases have no legend answer; they replay with a warning.
- **`ville2`'s control points fold the map**: the piecewise correction is refused there and
  that case runs on the affine.

### Verification

- 349 backend tests pass (`tests/test_georef_cases.py` excluded: it replays cases and writes
  to them).
- The 14 new tests fail on the pre-fix `align.py`, `pipeline.py` and `piecewise.py`, and pass
  on the fixed ones.
- The "before" column of §5 reproduces the committed run records exactly (e.g. Italy
  19.99 / 30.89 / 36.02 px), so before and after are measured the same way.
- Not done here: IoU on a scored case (none is runnable) or check-point error (the
  control-point role does not exist yet). Those are the test plan's job.
