# Georeferencing — Rework Plan (Proof of Concept)

The plan for replacing GCP-only affine georeferencing with coastline-driven alignment.
Covers **Steps 0–5**, which is everything up to and including a usable proof of concept.

Prerequisite reading: [`georeferencing-current.md`](georeferencing-current.md) — every
"today" reference below points there. Everything past Step 5 lives in
[`georeferencing-roadmap.md`](georeferencing-roadmap.md), which also holds the method
framework (parameter tiering, model selection theory, corpora, ML).

---

## 1. Goal and go/no-go

Today the warp is determined entirely by ~7 hand-clicked control points. A reference
coastline exists and is used only for a crude post-hoc vertex snap
([current §7](georeferencing-current.md#7-stage-e--coastline-snapping)).

The PoC answers one question:

> **Does adding reference-coastline evidence to the user's control points improve zone
> placement over those control points alone?**

Measured as IoU delta on the dev-test harness: same ground truth, same pipette picks, same
GCPs. Baseline is today's GCP-only affine; treatment is the joint fit. Only the transform
changes.

**This is not a contest between coastline and GCPs, and the two are never alternatives.**
They are complementary evidence with different error characteristics and different
coverage — GCPs are sparse but semantically certain and spread across the whole map;
coastline is dense but exists only along the coast. The production model uses **both**,
weighted by `1/σ²`. The GCPs additionally supply the initialisation without which chamfer
has no basin of attraction to converge in, so they remain load-bearing even where the
coastline dominates the final fit.

A coastline-only fit is run as a *diagnostic* (§10.3) and an ablation that measures how
much information each source carries independently. It is never the shipped model.

Everything in Steps 0–3 is plumbing and instrumentation that does not change output.
Step 4 is the experiment. If Step 4 shows no improvement, Steps 0–3 are still worth
keeping (they are inputs, records and reference layers), and the roadmap is abandoned
cheaply.

---

## 2. Principles

**Non-regression at every commit.** The GCP-only affine remains the floor. Any new
alignment must pass a gate to be used, and falls back to today's behaviour otherwise
(§10). At no point does the pipeline get worse than it is now.

**Measurable before clever.** No algorithm change ships without a number from the
dev-test harness. See [current §10](georeferencing-current.md#10-the-dev-test-harness).

**Forward-compatible shapes, not forward-built features.** Several PoC decisions look
over-engineered in isolation and are justified by a specific later stage. Each is marked
**[fwd]** with the reason. The rule: adopt the *shape* now when retrofitting it later
would touch every call site; do not build the *feature* now.

---

## 3. Architecture change (lands with Step 1)

Today the transform is fitted and applied inline inside the Celery task, and never
persisted ([current §9, limitations 4 and 7](georeferencing-current.md#9-known-limitations-and-quirks)).
Every later stage swaps the model class (affine → affine+stretch → FFD), and every
consumer needs the same warp. Without an abstraction the call sites get rewritten once
per stage.

Split `georeferencingSift.py` into a package:

```
app/utils/georeferencing/
    models.py       fit / apply / inverse / serialize — one interface per model
    reference.py    framing box -> reference raster + distance transform, cached
    evidence.py     user-side edge map, water mask
    align.py        coarse alignment, gates
    config.py       frozen hyperparameters as one versioned dataclass
    records.py      structured per-run record
```

Four interface decisions, all **[fwd]**:

- **The model has an inverse.** Chamfer needs reference samples pushed *into* pixel space;
  today's `AffineTransformation` is pixel→3857 only. Trivial (`np.linalg.inv` on the 3×3)
  but absent.
- **`fit()` takes a per-point weight vector**, not a scalar. Uniform in the PoC.
  *[fwd: Stage 7 weights GCPs by `1/σ²`, and σ differs per GCP source — see §9.]*
- **`fit()` takes a regularizer object**, not a scalar λ. `None` in the PoC.
  *[fwd: Stage 7 uses a spatially varying λ(x) field, not a constant — roadmap §6.]*
- **Hyperparameters live in one versioned dataclass**, not as defaults scattered across
  function signatures. This deliberately deviates from the surrounding style
  (`extract_colors` carries ~10 inline defaults). *[fwd: the whole point of the offline
  tuning track is to tune these as a set and ablate them, which is impossible when they
  are spread across call sites — roadmap §8.]*

The fitted model is **persisted with the map** so re-runs and later feature edits reuse it
instead of refitting.

Also fold in the cheap correctness fixes from
[current §9](georeferencing-current.md#9-known-limitations-and-quirks) while touching this
code: the `1/cos(φ)` unit error (1), the false-zero RMSE at exactly 3 points (2), and the
shapes-path flag (7).

---

## 4. Step 0 — make it debuggable (½ day)

**Deliverables**

1. **A direct script entry point.** Loads a case, builds reference rasters once, runs only
   alignment. Today's loop is `docker compose run --rm test-backend pytest`, which boots a
   container, collects every test, and runs a task containing literal `time.sleep(2)` calls.
   Step 4 means re-running dozens of times a day while tuning annealing schedules; seconds
   versus minutes compounds across the whole build.

2. **A structured per-run record** (`records.py`) written next to `report.json`:

   ```
   inputs      GCPs (+ source, sigma), framing box, pipette picks, reference layer versions
   models      affine after Stage 2, affine after chamfer, chosen model + parameters
   gates       every check: name, value, threshold, applicable, passed
   errors      GCP residuals, chamfer residual, IoU per zone
   timing      per phase
   config      the hyperparameter dataclass, versioned
   ```

   Three reasons: you cannot debug an IoU regression from an IoU number — if 0.94 becomes
   0.71 you need to know which stage moved it; the gate is only tunable if its inputs are
   logged even when it passes; and **[fwd]** this record *is* the dataset the offline tuning
   track consumes (roadmap §8). Twenty lines now, or re-running everything later.

**Explicitly deferred: new test cases.** Leclerc and other hard maps will be used to drive
development **manually** — run, look at the overlay, iterate — without authoring expected
zones. This is a deliberate time trade.

The cost, recorded so it is a known risk rather than a surprise: the one existing case sits
at IoU ≈ 0.94, the case with the least headroom, where extraction noise alone may swamp the
chamfer signal. Step 4's go/no-go number will therefore be weak evidence, and manual visual
comparison carries the decision.

**Future task — add Leclerc as a test case.** When time allows. Note for whoever does it:
for an A/B you are comparing IoU *delta* between two algorithms against the same ground
truth, so systematic ground-truth error largely cancels. **Rough hand-drawn zones are
sufficient**; they do not need to be accurate, only consistent. That makes it roughly an
hour of clicking, not a project. See also roadmap §7 for the automated corpus idea, which
supersedes hand-authoring at scale.

---

## 5. Step 1 — inputs and data model (1 day)

No algorithm change. IoU must be unchanged afterwards — that is the test.

**The framing box reaches the backend.** `worldAreaBounds` already exists in
`ImportView.vue` and is already sent to `/projects/coastline-keypoints`; it is simply not in
the `/upload` FormData. Add it to both upload routes and persist it into dev-test
`config.json` under `georef.frameBounds`. This gives the working extent for every reference
layer in Step 2.

**Water gets pipetted separately.** Add `kind: "zone" | "water"` to the imposed-color
entries. [`imposed_colors.py`](../Backend-Atlas/app/utils/imposed_colors.py) is shared by
the production and dev-test routes and round-trips through
`imposed_colors_to_config_entries`, so one parser change covers upload, dev-test and case
persistence. Frontend: the pipette step asks for water colors as a separate prompt.

Separate because zone fill and water are routinely the same hue — on the Leclerc map blue
is Nouvelle-France while the Atlantic is white. Colour alone cannot disambiguate them, and
the user can in one click.

**GCPs become records, not tuples.** Each control point carries:

```
{ pixel: (x, y), geo: (lon, lat), source: "sift" | "city" | "manual", sigma_px: float }
```

**[fwd]** Retrofitting per-point weights into a least-squares fit touches every call site,
and §9 (cities) introduces a source whose positional uncertainty is an order of magnitude
different from a coastline keypoint. Costs nothing now; `sigma_px` is a per-source constant
until Stage 7 uses it.

**Units become honest.** Report kilometres with the `1/cos(φ_center)` correction applied,
φ from the framing box centre. Keep fitting in EPSG:3857 — it is conformal, therefore
locally isotropic, so shape is already correct; only absolute scale was wrong. A local
LAEA/TM projection is the principled version but needs `pyproj` and buys nothing at PoC
scale.

---

## 5b. What landed — Steps 0 and 1

Numbered `5b` rather than `6` on purpose: both this document and
[`georeferencing-roadmap.md`](georeferencing-roadmap.md) cross-reference sections by number,
and renumbering would silently rot every one of them.

Implemented on branch `georef-exp`. Output is **byte-identical** to the previous pipeline —
see [§5b.4](#5b4-verification).

### 5b.1 Step 0 — debuggability

**`Backend-Atlas/scripts/run_georef_alignment.py`** — the direct entry point. Loads a case
config, runs colour extraction, fits and applies the transform, evaluates, prints control-point
RMSE in kilometres, IoU and per-phase timings. Flags: `--test-id`, `--case-id`, `--no-cache`,
`--no-write`, `--assets-root`.

Two additions beyond the plan, both in service of the same goal:

- **Colour extraction is cached on disk** (`Backend-Atlas/.georef_cache/`, gitignored), keyed
  on image mtime/size plus the zone pipette picks. Colour extraction is by far the slowest
  phase and does not change while alignment is being tuned, so the second run onwards is
  alignment-only — which is what the plan actually asked for ("builds reference rasters once,
  runs only alignment") once Step 2's rasters exist.
- **A `georef-dev` compose service** that depends on no broker, no database and no backend.
  The script is useless if running it still means `docker compose run --rm test-backend`, and
  `scripts/` was in neither the image nor any mount. The Dockerfile now `COPY`s it and
  `test-backend` mounts it too.

**`records.py`** — `RunRecord` and `GateCheck`. Written as `run_record.json` next to
`report.json` by both the dev-test task and the script, carrying inputs (control points with
source and sigma, framing box, water pick count), models, gates, errors (GCP residuals, IoU
per zone) and per-phase timings, plus the versioned config. `GateCheck` is populated by nothing
yet — Step 4 fills it — but the shape and the "log every check, even the ones that passed and
the ones that did not apply" rule are in place.

`RunRecord.write()` never raises, and `phase()` accumulates rather than overwriting. Diagnostics
must not be able to fail a run.

**Deferred as planned:** no new test cases. The one existing case (`pip_7sift`) remains the
only ground truth, and the §4 caveat about its thin headroom stands unchanged.

### 5b.2 Step 1 — inputs and data model

**The package split.** `app/utils/georeferencingSift.py` is gone, replaced by
`app/utils/georeferencing/`. The layout deviates from §3 in two places:

| Module | Status |
|---|---|
| `config.py` | as planned — `GeorefConfig`, frozen, versioned, with `with_overrides` |
| `models.py` | as planned — `ControlPoint`, `AffineModel`, `Regularizer` protocol |
| `records.py` | as planned |
| **`projection.py`** | **added** — EPSG:3857 maths and the km conversion, needed by models, pipeline and (soon) `reference.py`; it did not belong in any of the planned modules |
| **`frame.py`** | **added** — framing-box parsing, shared by both upload routes the way `imposed_colors.py` is |
| **`inputs.py`** | **added** — what a map was georeferenced from, built and parsed for the `maps.georef_inputs` column |
| **`snapping.py`** | **added** — the coastline vertex snap, lifted out so it can be deleted in one piece when Step 4 turns it off |
| **`pipeline.py`** | **added** — the fit → snap → clip → EPSG:4326 orchestration. §3 lists no home for it; `align.py` is Step 4's and means something else |
| `reference.py`, `evidence.py`, `align.py` | not created — they belong to Steps 2, 3 and 4 and empty stubs are noise |

`georeference_features()` returns a `GeorefResult` (collections + model + record) rather than a
bare list, so the caller can persist the fit and read the record without a second call.

**The four `[fwd]` interface decisions are all in.** `AffineModel.inverse()` returns the
EPSG:3857 → pixel model; `fit()` takes a `weights` vector (weighted least squares by row
scaling, tested, off by default because turning it on would move output); `fit()` takes a
`regularizer` object implementing `augment(design, target)`; and `GeorefConfig` is one frozen
versioned dataclass.

**The georeferencing *inputs* are persisted — not the fitted transform.**
`maps.georef_inputs JSONB`, added by `db/04_add_georef_inputs_to_maps.sql`, built by
`inputs.build_georef_inputs()` and written by the upload route before it dispatches the task.
It holds the control points with their source and sigma, the framing box, and the pipette
picks, in a shape that mirrors the dev-test `config.json`.

This deviates from §3, which says to persist the fitted model. §3's two justifications do not
survive contact with the code:

- *"Re-runs reuse it instead of refitting"* — the fit is `lstsq` on a 14×6 matrix from 7
  points. A re-run also re-uploads the image and redoes colour extraction, which is seconds.
  The refit is not measurable against that.
- *"Later feature edits reuse it"* — feature edits are lon/lat GeoJSON round-trips through
  `update_feature.py` and never touch pixel space. The image overlay takes its bounds from
  `default_bounds_from_image`, a ±8° placeholder unrelated to the fit.

Nothing in the codebase reads any georeferencing output property — not `transform_method`,
not `rmse_km`, not even `is_georeferenced`.

More decisively, **there is no refit today at all**: `process_map_extraction` is dispatched
from exactly one place, `POST /projects/upload`, and there is no re-extraction endpoint.
Georeferencing runs once at import and its zones are the permanent record. The refit the plan
alludes to is roadmap §4.4's active GCP suggestion ("rank candidates by expected error
reduction, refit live") — and that loop refits *by construction*, so a stored output matrix is
the wrong artifact for it.

What that loop needs, and what was actually missing, is the inputs. Before this change the
control points, framing box and pipette picks of a production map existed only as arguments to
the Celery task; once it returned they were gone, and the only way to georeference a map
differently was to re-import it and re-click every point by hand. That is precisely the problem
`config.json` was invented to solve on the dev-test side, and production had no equivalent.

With the inputs stored you can refit *anything*, including a better model later; with a stored
matrix you can only re-apply the same affine. `AffineModel.serialize()`/`deserialize()` are
kept — they cost nothing and the run record already exercises them — but nothing writes the
matrix to the database.

**The framing box reaches the backend.** `frame_bounds` is a form field on both
`POST /projects/upload` and `POST /dev-test-api/upload`, parsed by `frame.parse_frame_bounds`,
threaded to both Celery tasks, and persisted into dev-test `config.json` under
`georef.frameBounds`. On the frontend `worldAreaBounds` now travels in the upload payload from
`ImportView.vue` through both import composables. Longitudes may wrap the antimeridian
(`west > east` is accepted); `south >= north` is rejected.

**Water gets pipetted separately.** `imposed_colors.py` entries carry
`kind: "zone" | "water"`, with a missing `kind` meaning `zone` so every payload and every
stored config written before this change still parses. `split_imposed_colors_by_kind()` does
the separation once, in the routes; zone picks drive colour extraction exactly as before and
water picks travel to the task as their own arguments.

In `ColorPickerModal.vue` the pipette gained a Zones / Eau toggle, a per-row badge, and a
confirm button that requires at least one *zone* colour. The duplicate-colour check is now
scoped to the current kind — rejecting a water pick because a zone already has that hue would
break the exact case the feature exists for.

**Water picks are carried but not consumed.** They are logged and counted in the run record,
and nothing else. Feeding them to colour extraction would change output, and Step 1's test is
that output does not change. Step 3 builds the water mask from them.

**GCPs became records.** `ControlPoint(pixel, geo, source, sigma_px)`, built by
`ControlPoint.from_pairs()`. Default sigmas: `sift` 6 px, `manual` 8 px, `city` 40 px. The
city figure is a placeholder for §9 and deliberately an order of magnitude off the keypoint
one; nothing reads it yet.

**Units became honest, and changed meaning.** `rmse_meters` is gone from feature properties,
replaced by `rmse_km` plus `rmse_status`. Two separate corrections, and the second was not
anticipated in the plan:

1. The `1/cos(φ)` WebMercator correction is applied, φ from the framing-box centre, falling
   back to the mean control-point latitude and then to `None`.
2. **The old number was RMS per coordinate *component*, not per point *distance*** — it divided
   by `2n` where `n` points give `n` distances. The new figure is RMS point distance, which is
   what §8.3 means by "RMS distance to the held-out GCPs", and it is larger than the old one by
   exactly `sqrt(2)` before the latitude correction.

On `pip_7sift` the old code reported `10979` (labelled metres); the same fit now reports
**9.09 km**.

`rmse_status` is `"ok"`, `"no_redundancy"` or `"no_reference_latitude"`. With exactly 3 control
points `AffineModel.rmse_3857` is `None` rather than `0.0`: the fit is exact by construction, so
a zero residual is *no evidence*, not perfect confidence (limitation 2).

**The cheap fixes.** Limitation 1 (units) and 2 (false-zero RMSE) as above. Limitation 7: both
producers now share one `GEOREF_CONFIG`, so `ENABLE_COASTLINE_SNAPPING` actually governs the
shapes path too. Limitation 8 was also taken since it is free and provably identical — the
per-point Python loop converting EPSG:3857 back to lon/lat is now vectorised like its forward
counterpart.

Limitations 9 and 10 were left alone deliberately: both would move output. Each is now
documented at the code that causes it.

### 5b.3 Other changes made along the way

- `build_extraction_task_args_for_case` became **`build_extraction_task_kwargs_for_case`** and
  returns a dict. The task has gained four optional arguments and will gain more; a positional
  list silently misaligns when one is inserted in the middle. `tests/test_georef_cases.py`
  calls `.apply(kwargs=...)` accordingly.
- `_load_case_config` / `_parse_extraction_inputs` are now public and
  `parse_extraction_inputs` returns a `CaseExtractionInputs` dataclass instead of a
  six-tuple — the script needs them, and the tuple had grown to ten fields.
- **`tests/test_georeferencing.py`** — 36 unit tests over the model interface, the honest
  units, the framing box parser, the pipette kinds and the run record. They need neither cv2
  nor Celery nor a database, so they run in under a second.
- `dev-docs/dev-test-tool.md` updated for `run_record.json`, the new `config.json` fields and
  the fast loop.

### 5b.4 Verification

- **Geometry is unchanged.** The pre-split `georeferencingSift.py` was restored from git and
  run side by side with the new pipeline on the `pip_7sift` control points over two test
  polygons, with snapping and land clipping on. Both outputs satisfy `equals_exact(1e-9)` with
  a symmetric difference of exactly `0.0`. The fitted matrix matches to `atol=0`. This is a
  stronger check than "IoU unchanged", and it is pinned by a regression test.
- 36/36 unit tests pass.
- `vue-tsc -b` reports no errors in any touched frontend file. The ten pre-existing errors
  elsewhere (`GeoRefSiftWorldMap.vue`, `WorldAreaPickerModal.vue`, `mapDrawing.ts`,
  `AddCityModeService.ts`, `ImportPreview.vue`, `Profile.vue`) are untouched and unrelated.
- **The dev-test case itself was not re-run**: Docker Desktop was not running on the machine
  this landed on, and colour extraction needs `cv2`, which is not in the host environment.
  Given byte-identical geometry from identical pixel features, IoU cannot have moved — but
  someone should confirm with `docker compose run --rm georef-dev` before building on this.

### 5b.5 Caveats and follow-ups

1. **The `maps.georef_inputs` column only appears on a fresh database volume.** The repo's
   migration mechanism is `Backend-Atlas/db/*.sql` mounted into
   `docker-entrypoint-initdb.d`, which Postgres runs only when initialising, so an existing dev
   database will not have the column. The write is wrapped so it logs a warning rather than
   failing the import, but on an older volume the inputs are silently not stored. Apply it by
   hand without rebuilding anything:

   ```
   docker compose exec db psql -U postgres -d atlas      -c "ALTER TABLE maps ADD COLUMN IF NOT EXISTS georef_inputs JSONB;"
   ```
2. **Nothing reads `georef_inputs` yet.** There is no re-georeference endpoint to consume it;
   this stores the inputs so that one becomes possible. Writing an endpoint that refits a map
   from its stored inputs is the obvious small follow-up, and it would also give the dev-test
   harness a production counterpart.
3. **The existing `pip_7sift` case has no framing box.** It predates the field, and the box the
   user originally drew was never recorded. Step 2 needs an extent for its reference layers, so
   it must decide what to do when `frameBounds` is absent — deriving one from the control-point
   bounding box with padding is the obvious fallback, but it is Step 2's call and is not
   implemented here.
4. **`water_colors_names` and `water_sampling_radii` are accepted and unused** in both tasks.
   Deliberate: they are Step 3's inputs and it is cheaper to plumb them once.
5. **[`georeferencing-current.md`](georeferencing-current.md) is now partly stale.** Its §6-§8
   describe `georeferencingSift.py`, which no longer exists, and its §9 limitations 1, 2, 7 and
   8 are fixed. It was left alone on purpose: it is the record of what the PoC is measured
   against. Re-describe it after the Step 4 go/no-go, not before.

---

## 6. Step 2 — reference layers (1 day)

Given a framing box, produce and cache:

| Layer | Source | Built with |
|---|---|---|
| Coastline raster | `ne_coastline.geojson` | existing `draw_geojson_features()` |
| Lakes raster | `ne_50m_lakes.geojson` | same |
| **Rivers raster** | **`ne_50m_rivers_lake_centerlines.geojson` (new)** | same |
| Land/water mask raster | `load_land_mask_from_coastline_and_ocean_points()` | rasterize existing vector mask |
| Signed distance transform + gradient | the above | `scipy.ndimage.distance_transform_edt` |

Most of this already exists pointed at another problem.
`draw_geojson_features()` / `draw_coastline()` in
[`sift_key_points_finder.py`](../Backend-Atlas/app/utils/sift_key_points_finder.py) already
take bounds plus width/height and rasterize coastline *and* lakes. Promote them into
`reference.py`. The land mask is already built as a vector geometry by the polygonize +
ocean-seed flood fill ([current §8.1](georeferencing-current.md#81-building-the-land-mask));
it only needs rasterizing through the same mapping. Cache with the existing `lru_cache`
on `(path, mtime)` pattern, extended with the framing box.

**Adding hydrography (rivers).** A new Natural Earth layer,
`ne_50m_rivers_lake_centerlines`, dropped next to the existing files; same family, same
licence, same loader pattern. Coastline constrains only the boundary of the landmass, so
anywhere inland the warp is weakly determined. Rivers supply interior structure, and
historical boundaries frequently *follow* them (St. Lawrence, Ottawa, Richelieu). They also
add orientation diversity — a regional coast often runs in one dominant direction, leaving
the perpendicular poorly constrained.

Honest expectation: lakes are already loaded and lake shorelines are closed curves that
provide interior anchors, and Quebec is lake-dense — so the marginal value of rivers may be
smaller for the first target maps than it would be elsewhere. It is cheap, it strictly adds
signal, and more signal means fewer alignment failures (§10), so it goes in at Step 2 rather
than waiting for the snapping stage that motivated it.

**Raster resolution.** At a ~2500 km framing box, a 1024-px-wide raster is ≈2.5 km/px — two
orders of magnitude below the expected accuracy floor. Resolution is not a precision
constraint here; do not over-spend. Match the existing `find_coastline_keypoints` defaults.

**Deliverable:** debug PNG dumps of every layer. Visually verifiable, no pipeline change.

---

## 7. Step 3 — user-side evidence (1 day)

What the map itself offers to align *against*.

**Edge map.** Canny over the user's map, with text regions masked and dilated 5–10 px first.
`text_regions` already flows through the production task and
`filter_text_overlapping_contours` already exists in
[`shapes_extraction.py`](../Backend-Atlas/app/utils/shapes_extraction.py).

**Straight-line suppression.** Detect long straight segments with `cv2.HoughLinesP` and
down-weight them in the edge map. Graticules, neatlines, inset frames and legend boxes are
straight; coastlines are not. These are the dominant attractors for wrong-feature lock, and
this is roughly fifteen lines. See §10 — this is the cheapest single anti-failure measure in
the plan.

**Water mask.** From the water pipette of Step 1. Largest border-connected component is
ocean (`cv2.connectedComponents`); interior components are lakes.

**Not doing: toponym water cues.** Parsing labels for *Baie*, *Lac*, *Mer*, *Golfe*,
*Rivière*, *Océan* to infer water where colour fails has been **cut from the plan entirely**,
not deferred. Consequence, accepted knowingly: on a map like Leclerc with a white Atlantic,
the water pipette yields nothing and **there is no water evidence at all**. That is exactly
why the GCP-based gate below must be primary rather than supplementary. A secondary benefit
is that text extraction does not need enabling in the dev-test path
([current §10](georeferencing-current.md#10-the-dev-test-harness)).

**Deliverable:** debug overlays.

---

## 8. Step 4 — coarse alignment and the gates (2–3 days) — *the PoC*

### 8.1 Alignment

Two fits, with different jobs (§10.3). Both optimise the affine's 6 parameters; `D_user` is
the distance transform of the user edge map, and `T` maps reference → pixel space (hence
the inverse from §3). Samples `s_i` are reference coastline, lake and river points inside
the framing box.

**Production fit — joint.** This is what ships:

```
E = w_gcp * Σ ρ(||T(p_j) - q_j||)  +  w_curve * Σ ρ(D_user(T(s_i)))
```

with `w_gcp` from the per-GCP `sigma_px` of Step 1. The GCP-only affine of Stage 2 supplies
the initialisation.

**Probe fit — curve only.** `E = Σ ρ(D_user(T(s_i)))`, GCPs held out. Its transform is
discarded; only its disagreement with the held-out GCPs is kept, as the independence
measurement in §8.2.

- **Robust loss: Tukey**, not Huber. Schematic maps carry huge outlier fractions — on a map
  like Leclerc a large share of the drawn outline is invented (the *Territoire non exploré*
  fade, a notional Louisiana boundary). Huber down-weights outliers; Tukey rejects them
  outright, which is what is needed past roughly 30% outliers.
  Implementation note: `scipy.optimize.least_squares` has no built-in Tukey — its `cauchy`
  is redescending but never reaches exactly zero, which defeats the point. It *does* accept
  a callable `loss` returning `[rho, rho', rho'']`, so Tukey is available, just hand-written.
- **Levenberg–Marquardt**, annealed: heavy distance-transform blur first for a wide basin of
  attraction, sharpening as it converges; Tukey cutoff tightens on the same schedule.

### 8.2 The gates

Three available signals, with distinct roles:

| Signal | Role | Why |
|---|---|---|
| Chamfer residual | diagnostic and convergence only — **never a gate** | a fit locked onto the wrong feature has *low* residual by construction |
| GCP disagreement **of the probe fit** | **primary gate**, always available | the probe never sees the GCPs, so this is genuinely independent of the curve objective — and it measures whether the coastline evidence is trustworthy, which is the thing actually in doubt |
| Water-mask IoU | **secondary gate**, when a water mask exists | area overlap is a different measurement from curve distance, so it catches different failures |

Both gates must pass. Plus a transform-sanity bound (§8.3). Implement as a **list of named
checks**, each returning `(name, value, threshold, applicable, passed)`, with **all of them
logged every run** whether or not they applied — that is what later reveals which check
actually discriminates, which is a corpus-level question (roadmap §5).

### 8.3 What counts as failure

- **GCP disagreement** — RMS distance from the **probe fit** to the held-out GCPs > ~1.5–2×
  the GCP RMS of the Stage 2 affine, or above an absolute km bound derived from click
  precision. Read as: coastline-only alignment landed somewhere the user's points say is
  wrong, so the curve correspondences should not be trusted at full weight.
- **Water IoU** < ~0.7, when applicable. Loose on purpose: this catches catastrophic failure,
  it does not measure precision.
- **Transform sanity** — negative determinant (mirror/fold), scale drift beyond ~±25%, or
  rotation beyond ~±15° relative to Stage 2. A fit that slid a whole feature-width usually
  shows up here first.
- **Optimizer health** — LM did not converge, converged on the boundary of the search region,
  or the Tukey inlier count collapsed below ~20% of samples, meaning the "fit" rests on a
  handful of points.

Known causes, worth naming because they are what will actually be hit: lock onto a parallel
coast segment, a graticule line, a neatline, an inset frame or a legend edge; insufficient
coastline inside the framing box; a framing box drawn well off the true extent; one mispaired
GCP dragging Stage 2 outside the basin of attraction; and the genuinely schematic map where
the drawn coast corresponds to nothing real and Tukey correctly rejects almost everything.

### 8.4 Outcome

Result carries `alignment: "joint" | "joint_gcp_weighted" | "gcp_only"`, the recovery rung
reached (§10.2), and the probe's agreement score, plus the failed check
names, so the UI can tell the user what happened and ask for more points.

**Deliverable:** IoU delta on the harness, plus manual visual comparison on Leclerc. This is
the go/no-go for the entire roadmap.

---

## 9. Step 5 — cities as GCPs (post-PoC, well-specified)

Coastline keypoints are positionally sharp but semantically hard to match — the user is
matching an abstract shape. Cities are the opposite, and most maps have them.

**The data already exists.**
[`cities_validation.py`](../Backend-Atlas/app/utils/cities_validation.py) loads the full
`geonamescache` gazetteer at import into a normalised-name →
`[{name, lat, lon, country, population}]` map. Filtering by the framing box is a list
comprehension. No endpoint, no new dependency, no new file.

**Flow.** User indicates their map shows cities → types the names they can read → we
fuzzy-match against the gazetteer filtered to the framing box → user picks the right
candidate → user clicks the matching spot on their map. Identical downstream to a SIFT GCP.

**Two design constraints, both already accommodated by Step 1:**

- **σ differs by source.** A city on an old map is *semantically* unambiguous but
  *positionally* sloppy — old maps place cities wrong, which is the premise of the whole
  project. A coastline keypoint is the reverse. So a city GCP's σ reflects drawing error, a
  keypoint's σ reflects click error, and they differ by an order of magnitude. This is why
  GCP records carry `source` and `sigma_px` from Step 1 — and it is what makes Stage 7's
  `1/σ²` weighting meaningful rather than decorative.
- **Historical naming.** The gazetteer is modern; Ville-Marie, Stadacona and much of a 1755
  map will not match. The user must be the arbiter: they type what they see, we offer
  candidates, they confirm. **The gazetteer must never reject a name** — a failed lookup
  falls back to a manual click on the reference map.

Additional benefit: more GCPs, better spread, means a better Stage 2 initialisation, which
is the single largest determinant of whether Step 4 lands in the right basin (§10).

---

## 10. Designing against failure

Falling back to the GCP-only affine means having coastline data and not using it. That is
the outcome to minimise, not merely to handle gracefully. Failure is therefore treated as a
**ladder of recoveries**, not a binary.

### 10.1 Prevention (cheapest, do these first)

1. **Straight-line suppression** in the edge map (§7). Graticules and neatlines are the
   dominant wrong-lock attractors, and they are trivially separable from coastline by
   straightness.
2. **More reference signal** — rivers and lakes alongside coastline (§6). More correct
   structure to lock onto, and interior structure where coastline offers none.
3. **Better initialisation** — cities as GCPs (§9). Most failures are basin-of-attraction
   failures; a better starting affine prevents them outright.
4. **Restrict reference samples to the framing box** and, where a water mask exists, prefer
   coastline arcs adjacent to detected water. Confidence weighting before the robust loss
   ever sees the sample.

### 10.2 Recovery ladder (on gate failure, in order)

**The default is already the joint fit** — GCP term plus curve term in one objective,
weighted by `1/σ²`. The ladder below is what happens when that fit fails its gates, and
every rung except the last still uses the coastline. Descending the ladder means
progressively distrusting the *curve* evidence while the GCP evidence stays constant.

| # | Recovery | Rationale |
|---|---|---|
| 1 | Re-anneal wider — heavier initial blur, more levels, looser initial Tukey cutoff | the commonest failure is basin-of-attraction, and it is fixable by starting smoother |
| 2 | Multi-start — a small grid of perturbations around the Stage 2 affine (±rotation, ±scale, ±translation), keep the best gate-passing result | chamfer is fast; a handful of restarts costs little and escapes local minima |
| 3 | Raise the GCP weight — tighten `w_gcp` relative to `w_curve` so coastline can only refine *within* GCP tolerance | cannot lock onto a distant wrong feature, because the GCPs pin it; a continuous dial, not a mode switch |
| 4 | Reduce DOF — fit a 4-parameter similarity instead of a 6-parameter affine | fewer parameters is a smaller space to go wrong in; if the GCPs are good the coastline only needs to supply a small correction |
| 5 | Restrict evidence — use only coastline arcs adjacent to detected water, or within a radius of GCPs | trades coverage for reliability |
| 6 | Regional acceptance — keep the curve-driven correction only where evidence supports it, relaxing back towards the GCP-only affine elsewhere | anticipates the λ(x) field of roadmap §6: low evidence ⇒ stiff ⇒ stays at affine |
| 7 | GCP-only affine — today's behaviour, flagged, with a prompt for more points | the floor, never silently worse than now |

Rung 3 is the important one and deserves emphasis: because `w_gcp` and `w_curve` are
continuous, "trust the coastline less" is a dial rather than a binary fallback. Most
failures should be absorbed by turning that dial, not by discarding the coastline.

### 10.3 The independence tension, and how it is resolved

The production fit uses the GCPs, so the GCP residual is not an independent check *of that
fit* — you cannot verify a model against data it was fitted to.

Resolution: run **two fits with different jobs**.

- **Probe — free chamfer.** Fitted to the curve evidence alone, GCPs held out entirely.
  Its only output is a number: how far does coastline-only alignment disagree with the
  held-out GCPs? **Its transform is discarded.**
- **Production — joint fit.** GCP term plus curve term, `1/σ²` weighted. This is always
  what ships.

The probe is a **trust measurement on the curve evidence**, not a candidate model. Good
agreement means the coastline correspondences are independently corroborated, so the joint
fit runs at full curve weight. Poor agreement means the curve evidence is suspect, and the
response is to descend the ladder in §10.2 — starting by turning the `w_gcp`/`w_curve` dial
rather than by abandoning the coastline.

Two consequences worth stating plainly, because the earlier draft of this document got them
wrong:

- **Passing the probe is not a reason to ship the probe's transform.** Even when
  coastline-only alignment agrees with the GCPs, the better estimator uses both — they are
  independent measurements with different error characteristics, and discarding either
  throws away information. Coastline-only is unconstrained in the interior where there is no
  coast; GCP-only is unconstrained between the points.
- **The probe's agreement score is naturally continuous**, so the eventual refinement is to
  derive `w_curve` from it directly rather than thresholding it into pass/fail. The PoC may
  start with a threshold for simplicity; the continuous version is the intended destination.

### 10.4 Reporting, not silence

Every failure path records which checks failed and which recovery was used. A fallback is a
prompt ("automatic alignment found insufficient geography — add a few more points"), never a
silent downgrade. Aggregated across runs, these records are what tell us which prevention in
§10.1 is worth extending.

---

## 11. Explicitly out of scope for the PoC

| Item | Where it goes |
|---|---|
| Normal-search ICP with orientation filtering | roadmap §3 |
| FFD / non-rigid warp, local-similarity regularizer, fold barrier | roadmap §4, §6 |
| Model selection and cross-validation | roadmap §5 |
| Hydrography-driven boundary snapping | roadmap §4 |
| Confidence field, active GCP suggestion, fidelity slider | roadmap §4 |
| Corpora and offline hyperparameter tuning | roadmap §7, §8 |
| Toponym water cues | **cut entirely** — §7 above |
| Zones as a true planar arrangement (DCEL) | roadmap §9 — a vertex-dedup shortcut is expected to suffice |

---

## 12. Summary

| Step | Duration | Changes output? | Deliverable |
|---|---|---|---|
| 0 | ½ day | No | Direct script, structured run records |
| 1 | 1 day | No (verify IoU unchanged) | Framing box + water pipette plumbed, GCP records, honest units, package split |
| 2 | 1 day | No | Cached reference rasters incl. rivers, distance transform |
| 3 | 1 day | No | Edge map with straight-line suppression, water mask |
| 4 | 2–3 days | **Yes, gated** | Chamfer alignment + gates + recovery ladder → **go/no-go** |
| 5 | post-PoC | Yes | Cities as GCPs |

Steps 0–4 is roughly a week and answers the only question that matters. Everything in the
roadmap is conditional on that answer.
