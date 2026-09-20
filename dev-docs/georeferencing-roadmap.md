# Georeferencing — Roadmap and Method Framework

Everything past the proof of concept: the remaining runtime stages, and the method-level
framework that governs how the system's parameters are chosen, validated and eventually
learned.

Companion documents: [`georeferencing-current.md`](georeferencing-current.md) (what exists
today) and [`georeferencing-plan.md`](georeferencing-plan.md) (Steps 0–5, the PoC).

**Status: none of this is committed work.** It is conditional on the PoC's go/no-go —
does adding coastline evidence to the user's control points improve placement over those
points alone (the two are complementary, never alternatives). The sections below exist so
that PoC implementation decisions can be made with the destination in view, and so the
reasoning behind those decisions is recoverable later.

---

## 1. Purpose of this document

Two distinct things live here, and they should not be confused:

- **Runtime stages** (§4) — further pipeline work, executed per map. (§3 has moved into the
PoC; the section is kept as a pointer so cross-references still resolve.)
- **Method framework** (§5–§8) — how the constants in that pipeline get chosen at all.
  These are not per-map computations; they are the discipline that keeps the pipeline from
  being a pile of hand-tuned magic numbers.

The second is the part that is easy to skip and expensive to retrofit, which is why several
PoC decisions in the plan are marked `[fwd]` and point here.

---

## 2. What the PoC must deliver before any of this

- An alignment model with a fit/apply/inverse interface that accepts per-point weights and
  a regularizer object (plan §3).
- Explicit, orientation-filtered curve correspondences from ICP (plan §8.1, Phase B), frozen
  once converged so model selection (§5) has a fixed dataset to work on.
- Cached reference layers and distance transforms over a framing box (plan §6).
- A structured per-run record (plan §4) — the seed of §8.
- A gate framework of named, individually-logged checks (plan §8.2).

If the PoC is a no-go, §5–§8 still apply to whatever replaces it; only §4 is specific to the
chamfer/ICP approach — §3 has moved into the PoC itself.

---

## 3. Stage 5 — normal-search ICP — *moved into the PoC*

**This stage now lives in [`georeferencing-plan.md`](georeferencing-plan.md) §8.1 as Phase B of
Step 4.** It is no longer conditional on the go/no-go; it is part of what the go/no-go measures.

The move was driven by a measurement, not a preference. Step 3 found that straight-line
suppression down-weights only 22.3% of surviving edge pixels, because it can only catch what is
straight. What remains on a real map is long, curved, high-contrast linework with no reference
counterpart — drawn rivers and reservoir outlines, road corridors, the curved watershed-following
sections of a province border. A plain chamfer cannot distinguish those from a coast, so running
the PoC without orientation filtering would have measured the idea at its worst and risked a
false no-go.

Its content is unchanged: directed search along curve normals with a shrinking radius,
orientation filtering at ~30° tolerance, confidence weighting applied at correspondence time
rather than left to the robust loss, and explicit correspondences that slot into the same
weighted system as the GCPs.

Sequencing note preserved from the original: coarse chamfer remains ICP's initialisation, so the
two are built in sequence and a number is taken at each — Stage 2 affine, + chamfer, + ICP — so a
regression can be attributed to one half or the other.

---

## 4. Stages 7–9 — final fit, snapping, and confidence

### 4.1 The final objective

```
E = w_gcp   * Σ ρ(||T(p) - q||)            GCP term
  + w_curve * Σ w_i ρ(||T(s_i) - c_i||)    curve correspondence term
  + λ_sim   * E_local_similarity            regularizer  (see §6 — becomes a field)
  + barrier(det J <= 0)                     fold prevention
```

Weights derived as `1/σ²` from expected error magnitudes — click precision for GCPs,
drawing sloppiness for curves — rather than hand-tuned constants. This is why GCP records
carry `source` and `sigma_px` from Step 1 (plan §5, §9): a city GCP and a coastline keypoint
have genuinely different σ, and a single `w_gcp` constant cannot express that.

Anneal λ down and tighten the robust cutoff as the fit converges.

**Regularization everywhere, not only inside zones.** Control points outside a zone still
influence it through basis support, and the dense coastline correspondences live outside the
zones. Left unregularized there, the warp satisfies them through local contortions that
propagate inward as distortion the user never drew. A nonzero baseline term is what makes
the system well-posed; see §6 for why the original "3× inside zones" multiplier is the wrong
formulation of this.

### 4.2 Fold prevention and the adjacency guarantee

Zone adjacency survives the warp only if the warp is a continuous bijection — hence the
`det J <= 0` barrier. §6.3 covers a real trap here: the standard analytic guarantee assumes
a uniform control grid, and adaptive refinement breaks that assumption. **Decision taken:
prefer adaptive refinement and adapt the guarantee** — enforce positive Jacobian determinant
by sampling rather than by the analytic control-point displacement bound.

### 4.3 Stage 8 — hydrography-driven snapping

Zone boundary segments lying consistently close to warped reference rivers or coasts were
probably *meant* to follow them. Promote those to high-weight constraints and refit, inside
the annealing loop with a tightening threshold so early errors do not lock in.

This is the one place zone geometry becomes *data* rather than *prior*, and it is the most
original piece of the pipeline. It is also what motivated adding the rivers layer, though
that layer is pulled forward into PoC Step 2 because more reference signal means fewer
alignment failures (plan §10.1).

It supersedes the current blind vertex snapping
([current §7](georeferencing-current.md#7-stage-e--coastline-snapping)), which is this idea
without orientation filtering, without confidence weighting, and applied before any
alignment has happened. **Turn `ENABLE_COASTLINE_SNAPPING` off as soon as PoC Step 4 begins**
— it will actively fight the alignment.

Worth noting for sequencing: once the PoC lands, a confidence-weighted, orientation-filtered
version of snapping may deliver more value than the non-rigid warp, for a fraction of the
work, since a crude version already ships. That is more true now than when it was written —
with ICP inside the PoC (§3), the normal search, the orientation test and the confidence
weights all already exist by the time this stage starts; only the promote-and-refit loop is
new.

### 4.4 Stage 9 — confidence and targeted input

- **Confidence field** from distance to the nearest active constraint, combined with local
  warp displacement magnitude. Overlay it on the map.
- **Report the accuracy floor in kilometres.** "This map is schematic; placement accuracy
  ≈ ±80 km" beats a silently confident wrong answer. §5.1 covers how that number is actually
  obtained — it must be measured, not asserted.
- **Active GCP suggestion.** Point at the worst region, ask for a click, rank candidates by
  expected error reduction, refit live. Converts extrapolation into guided interaction with a
  visible stopping criterion: the user stops when the map stops being red.
- **Fidelity slider** exposing λ — rubber-sheet onto reality at one end, respect-the-drawing
  at the other. A product decision, not a technical one.

---

## 5. Stage 6 — model selection, the accuracy floor, and the candidate registry

### 5.1 The accuracy floor must be measured, not assumed

"±80 km" is a placeholder that has been repeated enough to look like a finding. It is not.
Four ways to obtain a real number, cheapest first:

1. **Leave-one-out on the user's GCPs.** Fit without point *i*, measure error at *i* in km.
   Seven points gives seven samples — noisy, but it directly estimates "how well can any
   model predict an unseen location on this map", and for models linear in their parameters
   it is closed-form PRESS, so it costs one fit.
2. **Spatial block CV on the curve correspondences** — §5.2. Gives the plateau.
3. **Model-ladder saturation.** Plot held-out error against DOF. The floor is where the
   curve flattens; if it never flattens, you are not at the floor and what looks like noise
   is still signal.
4. **Synthetic ground truth** (§7.2) — the only route to *absolute* truth, and the only one
   that separates the method's error from the map's error.

### 5.2 Cross-validation must be spatially blocked

Coastline samples are strongly autocorrelated. Random k-fold holdout puts training points
three pixels from every test point and reports absurdly optimistic error. Hold out
contiguous arcs or frame blocks instead; five blocks is enough.

Use closed-form leave-one-out where the model permits it. Similarity, affine and a fixed-λ
FFD are all linear in their parameters, so PRESS/GCV needs one fit rather than k. Only
genuinely nonlinear candidates need real folds.

### 5.3 The discrimination rule — when is a candidate worth having

This is the decision rule, and it can be written down today:

> Two models are distinguishable only when the difference in their held-out error exceeds
> the standard error of that difference.

Concretely: with block CV over B blocks, take per-block differences
`d_b = err_A(b) − err_B(b)` and compare `mean(d)` against `sd(d)/√B`. If it does not clear,
take the simpler model. A paired test over blocks, costing nothing beyond fits already
performed.

**The corollary that matters.** Over a 2500 km framing box, Mercator and Lambert conformal
conic differ by roughly 5–15 km. If the accuracy floor is anywhere near 80 km, **no single
map can ever resolve that choice.** Distinguishing projection families requires corpus-level
evidence (§7) — which is an argument for the offline track arriving from a completely
different direction than hyperparameter tuning does.

The same reasoning applies to the gate checks in plan §8.2: which check actually
discriminates real failures is a corpus-level question, answered by aggregating run records
(§8), not by reasoning about one map.

### 5.4 The candidate registry

Keep the candidate set as a **registry in code**, not as prose in a document. Prose rots;
a registry the eval harness can iterate over does not.

Each entry carries:

| Field | Meaning |
|---|---|
| `name` | e.g. `affine`, `affine_lat_stretch`, `lcc` |
| `dof` | parameter count |
| `linear_in_params` | whether PRESS/GCV applies, or real folds are needed |
| `enabled` | in the active set right now |
| `admission_condition` | what evidence would turn it on — §5.3 |
| `rationale` | why it might matter, and why it is off |

**PoC-era active set**, deliberately small: `affine`, `affine + latitude y-stretch`,
`FFD 4×4`, `FFD 8×8`. All linear in their parameters, so all get closed-form LOO.

**Registered but disabled**, with admission conditions recorded:

| Candidate | Why it might matter | Why it is off |
|---|---|---|
| `similarity` (4 DOF) | fewer DOF for badly drawn maps; already used as recovery rung 3 (plan §10.2) | nested inside affine; admit if it wins the §5.3 test on schematic maps |
| `homography` (8 DOF) | genuine perspective, if inputs turn out to be photographs of maps rather than digital renders | inputs are digitally rendered, so projective DOF would absorb drawing noise as a spurious global tilt |
| `equirectangular`, `mercator`, `lcc` | the map really was drawn in a projection, and fitting it is the principled model | differences are below the expected floor on one map — needs §7 corpus evidence |
| `FFD 16×16` and beyond | genuinely complex local warps | superseded by adaptive refinement, §6.2 |

**Stopping rule, which applies regardless of candidate:** stop refining when held-out
residual plateaus. Drawing error is not a warp — there is no displacement field that
explains a badly drawn peninsula. Chasing it with more DOF is overfitting, and the
contortion propagates into the zones as distortion the user never drew.

Counterintuitive and load-bearing: **worse-drawn maps need fewer DOF and more
regularization, not more flexibility.**

---

## 6. Parameter tiering, adaptive regularization, adaptive refinement

### 6.1 The tiering

A useful way to see that the parameter count is not the problem it looks like.
Dimensionality only hurts when you have to *enumerate*.

| Tier | What | How resolved | Scale |
|---|---|---|---|
| **1** | Continuous model parameters — the affine's 6, an FFD's hundreds of displacements | optimization, never search; smooth with gradients | ~500-dim, and fine |
| **2** | Per-map discrete choices — base model, refinement depth, λ | cheap selection: CV, plateau read-off | genuinely small |
| **2.5** | **Per-map, derived from measurement** | estimated, neither searched nor frozen | small |
| **3** | Method hyperparameters — annealing schedules, weight ratios, tolerances, refinement thresholds | tuned once across a corpus, then frozen | ~10, and the reason §8 exists |

**Tier 2.5 is an addition to the original framing**, and it matters because it shrinks
Tier 3. Some parameters are per-map but should be *measured* rather than searched or frozen:

- **σ for the GCP term** — estimate it from click dispersion, or from a per-source prior in
  pixels converted through the current scale. Do not tune it. Plan §9 covers why it differs
  by source.
- **The distance-transform blur starting value** — derive it from the Stage 2 affine's
  uncertainty. "How blurred must the DT be for the truth to lie inside the basin" is
  answerable from the GCP residuals, not a constant someone picked.

Deriving beats both searching and freezing wherever a measurement exists.

### 6.2 Adaptive regularization — λ as a field

Replace the scalar λ with:

```
λ(x) = λ₀ / (1 + k · ρ_data(x))  ·  (1 + α · 1_zone(x))
```

Evidence density drives the main term; zone membership survives only as a secondary factor.

**This is a genuine improvement over a flat "3× inside zones" multiplier.** The actual
principle is *be stiff where you have no data*; "be stiff in zones" was a proxy for it, and
a proxy that is wrong in an important case — a zone sitting on a well-constrained coast
should be allowed to flex.

Three implementation notes:

- **It remains linear in the parameters.** λ(x) is fixed given the current correspondences,
  so PRESS/GCV and the closed-form selection machinery all survive. This property is
  load-bearing; do not let an implementation quietly break it.
- **Recompute λ(x) once per annealing level, not per inner iteration.** ρ_data is estimated
  from correspondences that change every ICP iteration; updating the stiffness field inside
  the inner loop invites oscillation.
- It introduces `k` and the ρ_data kernel width as new Tier 3 hyperparameters. The claim
  that this "replaces the combinatorial question with about four hyperparameters" is roughly
  honest, but the count does creep.

### 6.3 Adaptive mesh refinement — and the adjacency trap

Start from a coarse uniform grid, fit, then subdivide only cells where residual is high
**and** local evidence is dense. Refit. Repeat until no cell qualifies.

This is standard — octree and hierarchical/THB-spline FFDs are normal in medical
registration — and it replaces the discrete resolution sweep with a local criterion. **The
conjunction is the whole point:** high residual with sparse evidence is drawing noise, and
refining there is precisely the overfitting to be avoided.

Two caveats.

**The trap.** Stage 7's adjacency guarantee comes from the fold barrier via the
control-point displacement bound — the Choi–Lee style result — and **that bound assumes
uniform control-point spacing.** Adaptive refinement breaks its precondition. Doing both
without noticing means the guarantee being relied on for zone adjacency is not actually in
force. Two ways out:

1. keep refinement uniform *within* each hierarchical level, so the bound applies level-wise; or
2. drop the analytic bound and enforce `det J > 0` by sampling on a fine grid.

**Decision taken: option 2.** Adaptive refinement is preferred, and the adjacency guarantee
is adapted to it rather than the reverse. The sampled check is more expensive and gives a
numerical rather than analytic guarantee; that trade is accepted for the local flexibility.

**Minor.** "FFD resolution is no longer a discrete sweep" is true of grid *structure*, but
you still choose when to stop refining, which is the same plateau read-off as §5.4 — local
and greedy now, not eliminated.

### 6.4 One correction: GCV is not closed form

A claim worth flagging before it gets written into code: **GCV does not give the optimal λ
in closed form from a single fit.** It gives a *criterion* that is cheap to evaluate at any
λ, because for a linear smoother the hat-matrix trace is obtainable without refitting from
scratch. Minimising it is still a 1-D search — tens of cheap evaluations, typically over a
log grid. Practically small; conceptually worth fixing before someone writes
`lambda = compute_gcv_optimal(...)` expecting a formula.

**The sharper problem:** GCV assumes independent residuals, and §5.2 establishes that
coastline samples are autocorrelated. That is the same violation that motivated spatial
block CV in the first place, and GCV under correlated noise characteristically
*undersmooths* — it will choose λ too small, producing exactly the local contortions the
regularizer exists to prevent.

**Therefore:** use GCV as a fast initialiser, read the final λ off the block-CV curve. Do
not let the closed-form story push block CV out of the loop.

---

## 7. Corpora

Three corpora, each answering something the others cannot. None of them is optional if the
Tier 3 numbers are ever to be defensible.

### 7.1 Corpus A — country/province zone maps (automated ground truth)

**The idea:** find many maps whose zones *are* real administrative units — countries,
states, provinces. Ground truth then comes free from the name: Natural Earth `admin_0` and
`admin_1` layers (same family and licence as the existing reference files) supply the true
border polygon. No hand-drawing at all.

**Why it is the highest-leverage corpus.** Hand-authoring expected zones is the bottleneck
on every other form of evaluation. This removes it, which is what makes corpus-scale
questions — projection families (§5.3), which gate checks discriminate (§8), learned priors
(§8.2) — answerable at all.

**Pipeline:**

1. Collect thematic/atlas maps with colour-coded administrative zones.
2. Identify which unit each zone is, **by name**: OCR labels and legend entries, matched
   against a gazetteer, the same pattern `cities_validation.py` already uses for cities.
3. Load the true border polygon for that name as the expected zone.
4. Run the pipeline, score IoU as the harness already does.

**Critical constraint — do not close the loop.** It is tempting to identify a zone by
warping candidate country polygons through the *fitted* transform and taking the best IoU.
That is circular: it uses the output to define the ground truth, and it will report success
regardless of whether the transform is right. Identification must come from the *name*.
Assisted labelling with human confirmation is fine; automatic labelling by geometric match
is not.

**Known limitations, all worth recording:**

- **It measures the whole pipeline, not georeferencing alone.** A zone whose colour
  extraction is poor scores badly no matter how good the transform is. Report GCP-holdout
  error (§5.1) alongside IoU as a georeference-only metric.
- **Modern borders are not historical borders.** Restrict this corpus to maps whose zones
  genuinely are contemporary administrative units. A 1755 map of Nouvelle-France has no
  modern equivalent.
- **It over-represents the easy regime.** Such maps tend to be cleanly drawn, in a known
  projection, with graticules — which is precisely *not* the schematic, high-outlier regime
  that Tukey and the recovery ladder exist for. Excellent for volume and for rendering
  variety; poor for tuning the robust-loss behaviour.

### 7.2 Corpus B — synthetic generation

Render maps from the reference vectors under randomised projections, palettes, line weights
and label placement, plus a known random warp and simulated drawing error. Ground truth is
exact by construction, per component, in kilometres.

**The caveat that determines whether this is useful or misleading:** rendering your own
reference vectors under a known warp tests the *optimizer*, not the *problem*. What makes
real historical maps hard is not noise — it is that the geometry is wrong in **structured,
coherent** ways: a peninsula from a bad survey, a coast copied from an earlier erroneous
map, a region deliberately flattened into a schematic. Gaussian vertex noise does not
produce outliers of that shape.

A synthetic corpus built on noise alone will calibrate basin-of-attraction and annealing
schedules well, while **overstating accuracy and never exercising the regime Tukey exists
for.** The generator must inject coherent lies: displace a whole coastal arc rigidly,
invent a peninsula, collapse a region to a straight line, truncate an unexplored territory.

### 7.3 Corpus C — historical maps, hand-labelled

Small, expensive, and the only one drawn from the actual target regime. Leclerc belongs
here (plan §4 defers adding it; that deferral is time-boxed, not permanent). Rough ground
truth is acceptable — for A/B comparison, systematic ground-truth error largely cancels in
the delta.

### 7.4 What each corpus is for

| Question | Corpus |
|---|---|
| Does the method converge, and from how far off? | B |
| What is the method's own error, absent map error? | B |
| Does it survive real rendering variety at scale? | A |
| Which projection family wins? | A |
| Which gate checks actually discriminate? | A, then C |
| Does it work on the maps we actually care about? | C |
| Can Tier 3 be tuned and ablated? | A + B |

---

## 8. Offline tuning track, and ML

### 8.1 Track B — the second thing to build

The pipeline described so far is entirely a runtime system. Tier 3 implies a second one:
an offline track that tunes the frozen hyperparameters — annealing schedules, weight ratios,
tolerances, refinement thresholds — against ground-truth error across a corpus.

This is not polish. Without it every Tier 3 number is a guess someone handed you, with no
way to defend or ablate any of them. With it they are empirically chosen, and the same
apparatus yields the km-error benchmark that otherwise does not exist.

The structured per-run record from PoC Step 0 (plan §4) is the input format. That is the
entire reason it is built on day one rather than retrofitted.

### 8.2 ML targets, in priority order

All of these are gated on having a corpus, which makes §7 the actual bottleneck.

1. **λ₀ and refinement thresholds predicted from map appearance.** The most defensible in
   principle: cross-validation observes one map, a trained model has seen thousands, so it
   can encode a prior over exactly what CV cannot see. Needs Corpus A at scale; training on
   synthetic alone would learn the generator's biases.
2. **Projection classifier.** Well-scoped and self-contained. Its value scales with corpus
   diversity — and since the goal is a *flexible* tool rather than one region and era, the
   input distribution really is broad, so a learned prior over projection has something to
   predict. Corpus A supplies both the variety and the labels.
3. **Predicted refinement map** — where the grid will need to be fine, before iterations
   discover it. Saves compute, not accuracy. Lowest priority.

Note what is *not* on this list: predicting the per-map configuration wholesale. §6.1 shows
the per-map discrete choice is tiny, so there is little to predict.

---

## 9. Zone topology

Stage 1 of the original plan called for zones as a true planar arrangement — one labelled
subdivision with shared edges stored once — so that adjacency and containment survive the
warp by construction.

**A cheaper route almost certainly suffices.** `build_exclusive_masks_by_nearest_center()`
already assigns every pixel to exactly one colour by nearest ΔE
([current §5.1](georeferencing-current.md#51-relationship-to-the-other-extraction-tools)),
so zones are *already* an exact partition and adjacency is already exact in raster form.
The property is lost only at `mask_to_geometry()`, which runs `find_contours` independently
per mask, producing neighbouring rings with slightly different vertices along shared edges.

Since a continuous bijective warp (guaranteed by the fold barrier, §4.2) preserves adjacency
whenever shared vertices are numerically identical, the fix is to **snap/dedupe boundary
coordinates across masks with a spatial hash** after extraction — roughly fifty lines,
rather than a half-edge/DCEL data structure.

Build the real arrangement only if shared-edge *editing* is ever required. Recorded here so
the shortcut is a decision with a reason, not an oversight.

---

## 10. Cut from the plan

**Toponym water cues** — parsing labels for *Baie*, *Lac*, *Mer*, *Golfe*, *Rivière*,
*Océan* to infer water regions where colour fails. Removed entirely, not deferred.

Consequence, accepted knowingly: on a map whose ocean is unpainted, the water pipette yields
nothing and there is no water evidence at all. This is why the GCP-based gate is primary and
the water-IoU gate is secondary (plan §8.2), and why the recovery ladder (plan §10.2) cannot
depend on a water mask existing.
