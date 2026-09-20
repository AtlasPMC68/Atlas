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

## 5b. Steps 0–1 — what changed, and what it costs later

Both steps landed as written in §4 and §5, so this records only what departs from the plan,
the one reported number that moved, and what later steps now inherit.

### Deviations

| Decision | Plan said | Why, and what it changes |
|---|---|---|
| Persist the georeferencing **inputs** (`maps.georef_inputs`) | §3: persist the fitted model | Below. Makes a re-georeference endpoint possible; the fitted matrix would not have. |
| Package also has `projection.py`, `frame.py`, `inputs.py`, `snapping.py`, `pipeline.py` | §3 lists six modules | §3's list has no home for projection maths, the framing box, or the fit→snap→clip orchestration. `reference.py`/`evidence.py`/`align.py` are created by the steps that own them, not stubbed. |
| Colour extraction cached to disk by the dev script | — | Colour extraction is the slow phase and does not change while alignment is tuned, so runs after the first are alignment-only. This is what makes Step 4's "dozens of runs a day" actually cheap. |
| A `georef-dev` compose service | — | `scripts/` was in neither the image nor any mount, so the Step 0 script was unrunnable as delivered. Depends on no broker, database or backend. |
| `build_extraction_task_kwargs_for_case` returns kwargs | positional args | The task gained four optional arguments in Step 1 and will gain more; a positional list misaligns silently when one is inserted mid-list. |

**On inputs vs the fitted transform.** §3's two justifications do not hold: refitting is `lstsq`
on 14×6 from 7 points, and feature edits are lon/lat round-trips that never touch pixel space.
Nothing in the codebase reads any georeferencing output property. More decisively there is no
refit at all today — `process_map_extraction` is dispatched only from `POST /projects/upload`,
and there is no re-extraction endpoint. The refit the plan gestures at is roadmap §4.4's active
GCP suggestion, which refits *by construction*, so a stored matrix is the wrong artifact for
it. What was actually missing is the inputs: control points, framing box and pipette picks
existed only as task arguments and were gone when it returned, so the only way to
re-georeference a map was to re-import and re-click. `AffineModel.serialize()` is kept;
nothing writes a matrix to the database.

### The number that moved

`rmse_meters` is replaced by `rmse_km` + `rmse_status`. Two corrections, and the second was not
anticipated by the plan:

1. The `1/cos(φ)` WebMercator correction, φ from the framing-box centre.
2. **The old value was RMS per coordinate *component*, not per point *distance*** — it divided
   by `2n` for `n` points. The new one is RMS point distance, which is what §8.3's gate means,
   and is larger by exactly `sqrt(2)` before the latitude correction.

On `pip_7sift` the old code reported `10979` "metres"; the same fit is **9.09 km**.
`rmse_status` is `ok`, `no_redundancy` or `no_reference_latitude` — with exactly 3 points the
RMSE is `None`, not `0.0`, because an exact fit means *no evidence*, not perfect confidence.

### Inherited by later steps

- **Water picks are carried, logged and not consumed.** Feeding them to colour extraction would
  have moved output. Step 3 builds the water mask from them.
- **`GateCheck` exists and nothing populates it.** Step 4 fills it. The "log every check, even
  the ones that passed or did not apply" rule is already enforced by the record.
- **`fit()` accepts weights and a regularizer, and uses neither.** Turning weights on changes
  output; Stage 7 is where they start mattering.
- **Nothing reads `georef_inputs`.** There is no re-georeference endpoint to consume it. Writing
  one is the obvious follow-up and would give production the counterpart of the dev-test
  harness's `config.json`.

### Verification

Geometry is byte-identical: the pre-split `georeferencingSift.py` was restored from git and run
side by side with the new pipeline on `pip_7sift`, with snapping and land clipping on. Both
outputs satisfy `equals_exact(1e-9)` with symmetric difference exactly `0.0`, and the fitted
matrix matches at `atol=0`. That is stronger than "IoU unchanged", and a regression test pins
it. `vue-tsc` is clean on every touched frontend file.

### Operational note

`Backend-Atlas/db/*.sql` is mounted into `docker-entrypoint-initdb.d`, which Postgres runs only
when initialising a volume, so an existing database does not get `georef_inputs`. The write logs
a warning rather than failing the import. To add it without rebuilding anything:

```
docker compose exec db psql -U postgres -d atlas \
  -c "ALTER TABLE maps ADD COLUMN IF NOT EXISTS georef_inputs JSONB;"
```

`app/` is bind-mounted, so code changes need only `docker compose restart celery-worker`
(the backend auto-reloads; the worker does not).

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

## 6b. Step 2 — what changed, and what it costs later

Landed as written in §6: `reference.py` builds coastline, lakes, rivers, land and distance-
transform layers over a framing box, cached on the box plus each source file's mtime, with a
debug PNG per layer. `ne_50m_rivers_lake_centerlines.geojson` added to `app/geojson/`
(the backend reads reference data from there, not from `Frontend-Atlas/public/geojson/`).

**No pipeline change.** Nothing consumes the layers until Step 4, so `process_map_extraction`
does not build them — paying ~2 s per production import for an unused artifact is waste. The
dev script builds them behind `--reference`.

### The one real deviation: the rasterizer was rewritten, not promoted

§6 says to promote `draw_geojson_features` / `draw_coastline`. Promoted verbatim they would
have poisoned the distance transform.

`draw_coastline` **drops** out-of-bounds vertices instead of clipping. A line that leaves the
framing box and re-enters loses its crossing vertices, and `cv2.polylines` then joins the
surviving runs with a straight segment that exists nowhere on Earth. That is harmless when all
you want is SIFT corner responses off the render, and ruin for a distance transform, which
cannot tell an invented edge from a real coast — wrong-feature lock being the failure mode all
of §10 is written against. It also drew a 3 px antialiased stroke, which widens the curve and
flattens the field beside it.

Measured on a line crossing out of a box and back: the old logic marks an 11-pixel phantom edge
where nothing exists and marks **nothing** where the real clipped geometry belongs; the new one
does exactly the opposite. A test pins this, and was itself checked to fail against the old
logic — a test that passes both ways pins nothing.

`sift_key_points_finder.py` keeps its own copy deliberately: rasterizing differently would move
the keypoints suggested to users, and that path has no test coverage. Unifying them is a
follow-up needing its own before/after check.

### Smaller decisions

| Decision | Why |
|---|---|
| No cv2 in the package — numpy rasterization, matplotlib (lazy) for debug PNGs | Keeps the module's tests runnable without the image stack: 41 tests in ~5 s on a bare host. |
| Signed distance is signed against the **coastline only**, not all curves | Lakes and rivers sit inside land; signing against the union would carve meaningless sign flips through the interior. |
| Antimeridian framing boxes work (two clip boxes, +360 shift) | `parse_frame_bounds` has always accepted `west > east`; leaving a silently wrong raster for a case the parser permits is worse than the ~10 lines. |
| Curve samples come from the rasterized curves, not source vertices | Uniform density in image space rather than whatever vertex spacing Natural Earth used. Step 4 consumes these. |

### Resolved from §5b

The existing `pip_7sift` case predates the framing box. `frame_bounds_from_geo_points()` derives
one from the control points padded outwards 25% — the points sit *inside* the mapped area, so
their bounding box is systematically too tight. The run record logs `frameBoundsSource` so a
derived box is never mistaken for a drawn one.

### Owed to Step 3: lake interiors count as land

The land mask is built from coastline linework plus ocean seed points, and lakes are not in the
coastline layer — so a lake's interior falls inside the land face. `land` therefore means
"not ocean", not "not water".

This is *correct* for clipping zones to land (a territory includes its lakes, and punching holes
in zones would be wrong), and it is what production already does. It breaks the water-mask IoU
gate of §8.2, because the user's blue pipette selects lakes *and* ocean while the reference side
can currently only offer ocean. Measured, comparing a user water mask of `ocean | lakes` against
a reference mask of `ocean`:

| Framing box | ocean | lakes | water-mask IoU |
|---|---|---|---|
| Quebec + Gulf | 32.6% | 1.2% | 0.966 |
| Interior Quebec | 0% | 3.5% | **0.000** |
| Great Lakes | 0% | 23.4% | **0.000** |

So the error is negligible where there is coast and total where there is not — and a box with no
coastline is exactly where alignment is weakest and the gate matters most. Since §8.3 requires
both gates to pass, a 0.0 here would fail a run whose primary GCP gate passed, sending it down
the recovery ladder to the GCP-only affine: §10's "outcome to minimise", triggered by a
measurement artifact.

Step 3 should add a filled `lake_interior` raster and derive `water = ocean | lakes` from it,
keeping `land` unchanged. Lakes are already loaded and the point-in-polygon machinery already
exists, so it is small. It also gives the reference side the same ocean/lake split §7 already
specifies on the user side (largest border-connected component is ocean, interior components are
lakes), so the gate compares like with like. Independently, the gate should report
`applicable: false` when neither side has any water at all.

### Also worth revisiting

**Rivers are thin** — 0.20% of the Quebec raster against the coastline's 1.10%. §6 predicted
this ("the marginal value of rivers may be smaller for the first target maps"). Step 4 should
measure whether they contribute before more is invested in hydrography.

### Verification

87 unit tests pass (41 new). Debug PNGs inspected: land fill matches the coastline, Hudson Bay
and the Gulf are water, the St. Lawrence channel is correct, and the signed field changes sign
exactly at the coast. Output is unchanged because no production path calls any of this.

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
