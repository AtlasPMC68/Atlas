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

**Done in Step 3** — see §7b. `lake_interior` is a raster, `water = ocean | lakes` is a
derived property, and `land` is unchanged. The gate should still report `applicable: false`
when neither side has any water at all, which is independent and remains Step 4's.

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

## 7b. Step 3 — what changed, and what it costs later

Landed as written in §7: `evidence.py` produces the Canny edge map with text masked out, the
straight-line weighting, and the water mask split into ocean and lakes. Toponym water cues stay
cut. No pipeline change — the dev script builds evidence behind `--evidence`.

Visually confirmed on the one test map: suppression marks the neatline, the title box, the
scale-bar frame and the straight Quebec–Labrador border, while keeping coastline, lakes and
rivers. 14 straight lines found, 14.4% of edge pixels down-weighted.

### The lake fold, as agreed

`ReferenceLayers` gained `lake_interior` (filled lake surfaces) and two derived properties:
`ocean` (`~land`) and `water` (`ocean | lake_interior`). **`land` is unchanged** — it still
means "not ocean", which is what clipping zones needs, since a territory includes its lakes.

The §8.2 gate must compare against `water`, not `ocean`. Measured, comparing a user mask of
`ocean | lakes` against a reference mask of `ocean` alone:

| Framing box | ocean | lakes | water-mask IoU |
|---|---|---|---|
| Quebec + Gulf | 32.6% | 1.2% | 0.966 |
| Interior Quebec | 0% | 3.5% | **0.000** |
| Great Lakes | 0% | 23.4% | **0.000** |

Negligible where there is coast, total where there is not — and a box without coastline is
exactly where alignment is weakest and the gate matters most. Step 4 should still report the
gate as `applicable: false` when neither side has any water, which is independent of this.

### Decisions

| Decision | Why |
|---|---|
| `evidence.py` is **not** re-exported from the package `__init__` | It is the only module needing cv2. Re-exporting would drag the image stack into every consumer and break the other 92 tests on a bare host. Import it directly. |
| Straight lines are down-weighted to 0.15, not deleted | A real coast can run straight for a while, and a neatline sitting on a coast should not take the coast with it. |
| The length threshold is a fraction of the image diagonal | So it means the same thing on a 900 px scan and a 6000 px one. |
| Ocean is the largest *border-touching* component | The sea runs off the edge of a map; a lake does not. A sea cut in two by a peninsula at the frame edge contributes its smaller piece to `lakes` — harmless for a gate comparing total water. |
| Water uses CIELAB + CIEDE2000, same as zone extraction | A water pick then behaves exactly like a zone pick; it simply never becomes a zone. |

### Owed to Step 4

- **Text masking is not optional, and it is bigger than it looks.** Measured on the one test
  map: masking OCR regions removes **49.7% of edge pixels** (100,547 → 50,578; the mask covers
  17.7% of the image). Without it, half the "evidence" a chamfer fit would see is place names,
  which correspond to nothing geographic.

  This was invisible at first because the dev-test task skips text extraction, so the dev loop
  built its edge map with `text_regions=None` and the debug dump wrote an all-black
  `text_mask.png` that read as a broken file rather than as "no OCR ran". Both are fixed: the
  script has an `--ocr` flag that runs EasyOCR once (~135 s/map on CPU) and caches the regions,
  and empty masks are no longer written at all.

  **Production defaults `enable_text_extraction` to `False`**, so the production
  georeferencing path has no text regions either. Decided: georeferencing must run OCR
  regardless of that flag. It is not optional evidence.

- **Masked text must be treated as *no data*, not as empty space.** Deleting the glyphs
  punches holes in any coastline that ran under a label: 16.4% of the removed edge pixels
  (8,205 px across 55 components) belong to long components the mask cut rather than to
  glyphs. Where that happens, `D_user` does not return "unknown", it returns the distance to
  the nearest *surviving* edge — mean 20.8 px, p95 63 px, max 135 px, which at this map's
  1.203 km/px is a p95 bias of **76 km**, the same order as the accuracy floor the project is
  trying to beat. Worse, the error is structured rather than random: labels sit on the
  features they name, so holes fall preferentially on the coastline and rivers we most want to
  match, and the distance gradient inside a hole points *along* the coast instead of across it.

  **Rejected: preserving connected components that are only partly inside the mask.** The idea
  was that a glyph is wholly inside the mask while a coastline passing under a label is mostly
  outside, so keeping the latter would heal the holes. It does not survive contact with the
  data: a letter whose stroke touches the coast merges into one 8-connected component, that
  component is overwhelmingly coastline, and the letter rides along. Measured, 4 of 96 text
  regions keep ≥50% of their own edge pixels under this rule (worst: 79%) and 17 keep ≥15%.
  No refinement fixes it either — a letter fused to a line genuinely looks like part of the
  line locally, so any pixel classifier is guessing.

  **Decided instead:** keep deleting everything under the mask, so no glyph can ever pollute
  `D_user`, and carry the text mask forward as a **validity mask**. A reference sample
  projecting into an unknown region gets weight zero in the curve term rather than a large
  spurious residual:

  ```
  E_curve = Σ  v(T(s_i)) · ρ( D_user(T(s_i)) )        v = 0 under a label
  ```

  Measured cost: of 9,015 reference curve samples, 6,586 project inside the image and 1,212 of
  those (18.4%) land under a label, leaving **5,374 usable samples** to constrain 6 affine
  parameters. That loss is free in practice, and the samples are now *absent* rather than
  *wrong*. Losing evidence beats fabricating it. This is also the first instance of the
  "confidence weighting before the robust loss" that roadmap §3 already called for.

  Implementation note: a hard 0/1 validity makes the energy discontinuous as `T` moves and
  samples cross the mask boundary. Blur the validity so `v` lands in [0, 1] at the edges and
  the objective stays smooth for LM.

  Optionally recoverable later: bridging a *small* gap between two confident coastline
  endpoints is interpolation between real observations, which is defensible — unlike
  preserving a merged glyph, which is fabrication. A refinement to reach for if 18% sample
  loss ever bites, not the baseline.
- **The one test case has no water picks**, so the water gate cannot be exercised on it at all.
  Adding a case with water pipetted is worth more than it sounds: it is the only way to test
  the secondary gate before Step 4 depends on it.
- **The Tier 3 constants are guesses.** `straight_line_weight`, `water_delta_e`, the Hough
  thresholds and the Canny pair are all in `GeorefConfig` (now version 2) so the offline track
  can tune them as a set, but none has been tuned against anything.

### The dependency problem found on the way

Running the dev loop against the test suite exposed something pre-existing and more serious
than anything in Step 3.

`opencv-python-headless` and `numpy` were **unpinned** in `requirements.txt`. The `backend` and
`test-backend` images were built a week ago; the new `georef-dev` image was built today. They
got OpenCV 4.13.0.92 vs 5.0.0, and numpy 2.4.4 vs 2.5.3. Consequences, both observed:

1. OpenCV 5.0 changed `HoughLinesP`'s return shape from `(N, 1, 4)` to `(N, 4)`, so the new
   code crashed in the dev loop while its own tests passed in the older image.
2. **numpy 2.5.3 produced different zone geometry** — the same map scored IoU 0.9406 instead of
   0.9414, with 30 polygon parts instead of 28. Pixel-space extraction was identical; the
   divergence appears downstream, in the shapely snapping and land-clipping stage.

The second is the one that matters. The whole PoC is an IoU *delta* measured on this harness,
and a silent 0.0008 drift from a rebuild is the same order as the effect Step 4 is trying to
detect. It also breaks the dev-test tool's stated premise that a report can be diffed between
branches.

Both are now pinned to the versions production already runs (`opencv-python-headless==4.13.0.92`,
`numpy==2.4.4`), and with them pinned the script and the Celery task produce **byte-identical**
geometry and exactly the same IoU. `normalize_hough_output()` accepts either OpenCV layout
regardless, with tests for both.

The dev script's colour-extraction cache also now keys on the library versions. It had served a
result computed under OpenCV 5 after the image was rebuilt on 4.13 — a measurement harness
handing back a silently stale number is worse than having no cache at all.

Six more were then pinned to the versions production already runs — `Pillow==12.2.0`,
`python-multipart==0.0.24`, `sqlalchemy==2.0.49`, `matplotlib==3.10.8`,
`email-validator==2.3.0`, `geonamescache==3.0.1`. The last of those is the one that matters:
**geonamescache 3.0.2 carries 1,562 more cities than 3.0.1** (34,006 vs 32,444), a 5% shift in
the gazetteer that drives city detection today and is the entire data source for §9. It is
reference data wearing a library's clothes, and it should be pinned like the Natural Earth
files are.

`geoalchemy2` was **removed** rather than pinned: it has no imports anywhere, no `Geometry`
column, and `Feature.data` is a plain `JSON` column. It had drifted 0.18.4 → 0.20.0, the widest
semver gap in the list, on a dependency that does nothing.

**Still unpinned, deliberately:** `torch`, `torchvision`, `easyocr`. Their wheels come from the
pytorch CPU index, which prunes old builds, so a hand-pinned `torch==2.11.0+cpu` will eventually
fail to resolve; the three also have tight mutual constraints. They only affect the optional
text-extraction path. They did drift hard (torch 2.11 → 2.14), so this is a deferral, not a
dismissal — the right fix is a lockfile.

**The transitive deps drift too** — cryptography 46 → 50, click 8.3 → 8.5, greenlet, cffi,
contourpy. Pinning direct requirements stops what you can see. Genuine reproducibility needs a
lockfile generated from a known-good image (`pip freeze > requirements.lock`, installed with
`-c`), which would also resolve the torch problem by recording whatever resolved rather than
guessing.

### Verification

115 tests pass in both containers (23 new for evidence). The dev script and the Celery task
produce identical geometry and IoU 0.9414069377250001 — the unchanged baseline. Overlays
inspected.

---

## 8. Step 4 — alignment and the gates (4–6 days) — *the PoC*

### 8.1 Alignment — staged

> Updated after manual testing; see §8d. This section originally described two phases over
> coastline, lake **and river** samples together. It is now three stages, coastline first, and
> rivers are no longer used as evidence.

`D_user` is the distance transform of the user edge map, `T` maps reference → pixel space
(hence the inverse from §3), and samples `s_i` are reference curve points inside the framing
box. Every stage optimises the same affine 6 parameters.

**The stages, in order:**

| Stage | Evidence | Schedule |
|---|---|---|
| A1 coarse chamfer | **coastline only** | wide: 64 px blur, 400 px cutoff |
| A2 fine chamfer | coastline + lakes | 8 px blur, 70 px cutoff |
| B normal-search ICP | coastline + lakes | shrinking search radius |

Coastline goes first and alone because it is the most distinctive structure on a map and the
one a user is most likely to have drawn faithfully; it should set the transform before anything
finer is allowed to pull on it. Rivers are loaded but off (`use_rivers_for_alignment`).

Every curve term carries the validity weight `v` of §7b: samples projecting under a text label
contribute nothing rather than a spurious residual.

**Stages A1 and A2 — chamfer.** Get the map into the right neighbourhood. A1 runs on
coastline alone with the wide schedule; A2 repeats with lakes admitted and a sharper one.

```
E = w_gcp * Σ ρ(||T(p_j) - q_j||)  +  w_curve * Σ v(T(s_i)) · ρ( D_user(T(s_i)) )
```

with `w_gcp` from the per-GCP `sigma_px` of Step 1. The GCP-only affine of Stage 2 supplies the
initialisation.

- **Robust loss: Tukey**, not Huber. Schematic maps carry huge outlier fractions — on a map
  like Leclerc a large share of the drawn outline is invented (the *Territoire non exploré*
  fade, a notional Louisiana boundary). Huber down-weights outliers; Tukey rejects them
  outright, which is what is needed past roughly 30% outliers.
  Implementation note: `scipy.optimize.least_squares` has no built-in Tukey — its `cauchy`
  is redescending but never reaches exactly zero, which defeats the point. It *does* accept
  a callable `loss` returning `[rho, rho', rho'']`, so Tukey is available, just hand-written.
- **Levenberg–Marquardt**, annealed: heavy distance-transform blur first for a wide basin of
  attraction, sharpening as it converges; Tukey cutoff tightens on the same schedule.
- **`D_user` is built from a weight map, not a binary one.** Straight-line suppression (§7)
  leaves edges at weight 0.15 rather than deleting them, and `distance_transform_edt` needs
  binary input. Build two transforms and combine: `D = min(D_strong, D_weak + penalty_px)`, so
  a suppressed edge behaves as if it were some pixels further away instead of vanishing or
  counting in full.

**Stage B — normal-search ICP.** Turns the neighbourhood into explicit correspondences.
Moved here from roadmap §3; the reasoning is below.

- **Directed search along curve normals.** For each reference sample, search along its normal
  rather than in all directions, with a radius that shrinks per iteration.
- **Orientation filtering (~30° tolerance) is the point of the stage.** A chamfer distance
  cannot tell a coastline from a political border crossing it — both are just "nearby edge
  pixels". Requiring the matched edge's local orientation to agree with the reference curve's
  rejects those outright.
- **Confidence weighting at correspondence time**, before the robust loss: the §7b validity
  weight, plus a preference for coastline arcs adjacent to detected water. A coastline segment
  next to detected water is trustworthy; a zone edge with no adjacent water may well be
  invented. Weight it then rather than hoping Tukey sorts it out afterwards.
- **Output is explicit correspondences** `c_i`, so the curve term becomes
  `Σ w_i ρ(||T(s_i) - c_i||)` and slots into the same weighted system as the GCPs — which is
  why the fit interface takes a weight vector (§3). Run to convergence, then freeze the
  correspondences.

**Why ICP is inside the PoC and not after it.** The original split put chamfer in the PoC and
ICP in the roadmap, on the assumption that straight-line suppression would handle wrong-feature
lock well enough to get an honest go/no-go. Step 3's measurements say otherwise: suppression
down-weights only **22.3%** of surviving edge pixels, because it can only catch what is
*straight*. What it leaves behind on a real map is not noise — it is long, curved, high-contrast
linework with no reference counterpart: drawn rivers and reservoir outlines, road corridors, and
the curved watershed-following sections of a province border. Those are precisely the features a
plain chamfer mistakes for a coast, and orientation filtering is the only thing in the plan that
separates them. Shipping the PoC without it would measure the idea at its worst and risk a
false no-go.

**Measure at each stage anyway.** Each stage initialises the next, so they are built in sequence
regardless, and taking a number at each costs nothing:

| | |
|---|---|
| Stage 2 affine | the GCP-only baseline |
| + chamfer (A1+A2) | does coastline evidence help at all? |
| + ICP (B) | does orientation filtering pay for itself? |

That keeps §2's "measurable before clever" intact: if the joint result is worse, these three
numbers say which half caused it. Bundling them into one measurement would not.

**Probe fit — curve only.** `E = Σ v · ρ(D_user(T(s_i)))`, GCPs held out, run through the same
phases. Its transform is discarded; only its disagreement with the held-out GCPs is kept, as the
independence measurement in §8.2.

### 8.2 The gates

Three available signals, with distinct roles:

| Signal | Role | Why |
|---|---|---|
| Chamfer residual, *magnitude* | diagnostic only — **never a gate** | a fit locked onto the wrong feature has *low* residual by construction |
| Chamfer residual, *improvement* | convergence gate (`curve_fit_engaged`, added in §8d) | a fit that never moved passes every sanity check, since nothing drifted, and returns the baseline wearing a success label. Asking whether the residual *improved* is a convergence question, not a correctness one |
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
- **Curve term never engaged** — the trimmed coastline chamfer did not improve by at least
  ~2% between the baseline and the aligned model. Read as: the fit could not reach the real
  coastline, usually because the starting transform was too far off for the annealing schedule.
  Descending to a wider anneal (rung 1) or multi-start (rung 2) is the intended response.
- **Optimizer health** — LM did not converge, converged on the boundary of the search region,
  or the Tukey inlier count collapsed below ~20% of samples, meaning the "fit" rests on a
  handful of points. After Stage B, the count of samples surviving *orientation filtering* is
  the same kind of signal and a more specific one: a collapse there says the curve evidence
  matched nothing of the right orientation, which is wrong-feature lock caught in the act.

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

## 8b. Step 4 — what changed, and the go/no-go number

Landed as written in §8: annealed chamfer, normal-search ICP with orientation filtering, the
probe fit, the named gates, and the recovery ladder. New modules `align.py` (distance field,
Tukey, chamfer, ICP), `gates.py`, `recovery.py` (the ladder) and `runner.py` (image → gated
alignment, the one entry point the Celery task and the dev script share).

### The number

> **Superseded — see §8c.** Everything in this subsection was measured with blind coastline
> snapping still on, which puts a ±0.012 step function into the metric. The deltas below are
> smaller than that artifact and mean nothing. The corrected measurement is in §8c. The rest of
> §8b (decisions, ladder coverage, what is owed) still stands.

Measured on `pip_7sift`, same ground truth, same pipette picks, same GCPs, transform the only
thing changing:

| | IoU | delta |
|---|---|---|
| Stage 2 affine (baseline) | 0.941407 | — |
| + chamfer | 0.944855 | **+0.003448** |
| + chamfer + ICP | 0.944291 | +0.002884 |
| | | *ICP alone: −0.000564* |

All gates pass at rung 0. The probe fit — curve evidence alone, GCPs held out entirely —
lands **9.5 px** from the held-out control points against a 7.6 px GCP-only baseline, well
inside the 2× threshold. That is the most encouraging number here: coastline-only alignment,
with no knowledge of the user's points, independently agrees with them.

**What this does not establish.** One case, at IoU 0.94, is the case with the least headroom,
exactly as §4 warned when it deferred new test cases. The deltas are ~0.003 and ~0.0006. §5.3's
own discrimination rule says two models are distinguishable only when the difference exceeds
the standard error of that difference — and with n = 1 there is no standard error to compare
against. So: chamfer shows a small positive delta, ICP a small negative one, **and neither is
resolvable at this sample size.** This is not a go, and it is not a no-go.

Taking a number at each phase is what makes that statement possible at all; a single bundled
figure would have shown +0.0029 and hidden that ICP moved it the wrong way.

### 8c. Correction: the earlier numbers were noise, and snapping is why

Everything in §8b's table was measured with blind coastline snapping still on. It should not
have been, and the plan said so: roadmap §4.3 already required turning
`ENABLE_COASTLINE_SNAPPING` off as soon as Step 4 began. Leaving it on to "keep the baseline
comparable" was the wrong call, and measurement now shows why.

**The metric had a cliff in it.** Translating the *same* transform by a few pixels and
re-scoring, on `pip_7sift`:

| dx (px) | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | spread |
|---|---|---|---|---|---|---|---|---|---|
| snapping **on** | .9414 | .9408 | .9412 | .9410 | .9403 | **.9289** | .9392 | .9377 | 0.0125 |
| snapping **off** | .9260 | .9265 | .9267 | .9264 | .9259 | .9250 | .9237 | .9203 | 0.0063 |

With snapping on the score is non-monotonic and spikes 0.012 downward at 5 px. With it off it
falls smoothly and monotonically, as a placement metric should.

**Blind snapping corrects whatever the transform got wrong**, after the fact and without
orientation filtering. It therefore does two damaging things at once: it flatters the baseline
(0.941 vs 0.926 here) and it hides any improvement a better transform makes, because the error
it would have fixed was already papered over. That is what roadmap §4.3 meant by "it will
actively fight the alignment".

**So §8b's deltas — chamfer +0.0034, ICP −0.0006 — were inside a ±0.012 artifact and meant
nothing.** Re-measured with the confounder removed:

| | IoU |
|---|---|
| Stage 2 affine, no snapping | 0.926047 |
| + chamfer + ICP, no snapping | **0.930054** |
| | **+0.004007** |

The noise floor with snapping off is about 0.0001 over the first 4 px, so this delta is real on
this case — still one case, still not a go/no-go, but for the first time it is a number rather
than an artifact.

`GEOREF_ENABLE_COASTLINE_SNAPPING` now switches it, defaulting to `true` so nothing changes
silently. The dev script takes `--no-snap`. **Judge alignment with snapping off.**

### 8d. Coastline-first staging, and rivers dropped

Driven by manual testing on a second map, where the result was poor and the diagnosis was that
the starting transform was too far off for the chamfer to reach the real coastline.

- **Rivers are no longer alignment evidence** (`use_rivers_for_alignment=False`). They are still
  loaded, rasterized and available; they simply contribute a lot of thin dense linework that a
  reader does not recognise on the map, much of it drawn schematically or omitted entirely.
- **Alignment is staged**: coastline alone with a wide annealing schedule, then a finer stage
  admitting lakes, then ICP. Coastline is the most distinctive structure on a map and the one
  most likely to be drawn faithfully, so it sets the transform before anything finer pulls on it.
- **The coarse stage starts far wider** — 64 px blur, 400 px Tukey cutoff, against 16/120 before.
  A map that starts a hundred pixels out is invisible to a 16 px blur.

**And a gap the reported failure exposed: there was no check that alignment did anything.** A
fit that never moved passes every sanity gate — scale drift zero, rotation zero, optimizer
"converged" — and returns the baseline wearing a success label. `curve_fit_engaged` now compares
the trimmed coastline chamfer before and after and fails when it did not improve, which sends
the run down the recovery ladder (wider anneal, then multi-start) instead of silently reporting
success. It is a *convergence* check, not a correctness one: residual magnitude is still never a
gate, because a fit locked onto the wrong feature scores well by construction.

### 8e. Per-run debug dumps

An IoU number cannot tell you *why* a map placed badly, so every run can write a folder of
diagnostics instead of adding to the logs. `GEOREF_DEBUG=true` (already set on `backend` and
`celery-worker`) writes to `Backend-Atlas/debug_runs/<timestamp>_map<id>/`, bind-mounted to the
host, gitignored, capped at the newest 20 runs.

| File | What it answers |
|---|---|
| `summary.txt` | leads with **DID IT ACTUALLY ENGAGE?** — chamfer before/after, % improvement, how far the coastline moved, layers used. Then per-GCP residuals, every gate with value *and* threshold, evidence and reference stats, both matrices |
| `06`/`07`/`08_reference_*` | the real coastline drawn through the transform onto the map — baseline red, aligned green. **If these do not sit on the drawn coast, that is the answer** |
| `09_control_points` | yellow circle = where the user clicked, red cross = baseline prediction, green = aligned. Line length is the residual |
| `04_edges_over_map` | green = edges used, red = suppressed straight lines |
| `10_icp_correspondences` | what ICP matched, and to where |
| `01`–`03`, `05` | raw edges, weight map, text mask, water (water only when pipetted) |
| `alignment.json`, `zones.geojson` | machine-readable gates and phase matrices; the actual output |

`GEOREF_DEBUG_KEEP` changes retention. The dump is written by `runner.align_map`, the only place
holding the reference layers, the evidence and the result at once.

This is deliberately throwaway: it is diagnostics for the PoC, not a feature, and it should be
deleted or hidden behind a proper debug flag before any of this is considered finished.

### How it is switched, and where it is on

`GeorefConfig.enable_curve_alignment` defaults to False, but `tasks.py` overrides it from the
environment so the running application can be evaluated by hand:

```
GEOREF_ENABLE_CURVE_ALIGNMENT   default "true"   -> backend, celery-worker
                                set to "false"   -> test-backend, georef-dev
```

So **alignment is live in the app** and off in the regression suite. That split is deliberate:

- The app has it on because a single dev-test case cannot decide this and manual evaluation on
  real maps is what §4 said would carry the decision.
- The suite has it off because it measures the GCP-only floor §2 promises never to fall below,
  and because with alignment on the dev-test task runs EasyOCR per case (~135 s on CPU), which
  took the suite from 90 s to over four minutes.
- `georef-dev` has it off because the script drives alignment explicitly with `--align`, and one
  run should not silently mean two different things.

**This is a switch for evaluation, not a verdict.** +0.003 on one case is not the number §2
asks for. If manual testing on other maps does not clearly help, the default should go back to
false.

Verified all the way through: with it off the harness reproduces 0.9414069377250001 exactly;
with it on the Celery task and the dev script produce byte-identical results
(0.9442911484509129 from both), so the production path and the measurement path cannot drift.

### What the pipeline does now

Alignment runs **once per map**, after text extraction and before either feature producer, so
shapes and colors are georeferenced with the same transform. It needs the OCR regions, which is
why it sits immediately after that step; when `enable_text_extraction` is off it runs its own
OCR, and when it is on the existing regions are reused at no extra cost.

The task result carries an `alignment` block — method, rung, whether curve evidence was used,
failed check names, the probe's agreement in pixels, and every gate with its value and
threshold — which is what §8.4 asked for so the UI can tell the user what happened. Each
georeferenced feature also carries `alignment_method` and `alignment_rung` in its properties.

### Decisions taken while building it

| Decision | Why |
|---|---|
| Residuals in **image pixels** for both terms | One robust cutoff then means the same thing to the GCP term and the curve term. Each term is normalised by its own count first, so seven control points are not drowned by 4,481 curve samples. |
| Tukey hand-written as a scipy `loss` callable | Confirmed `rho'` reaches exactly 0.0 at the cutoff — past it a sample contributes nothing. scipy's `cauchy` never reaches zero, which defeats the purpose. |
| Numeric Jacobian | 6 parameters, so a numeric Jacobian costs 6 extra evaluations per iteration of a cheap bilinear lookup. Analytic derivatives through an inverted affine are a correctness risk for no measurable speed. |
| Validity blurred, not hard 0/1 | Samples crossing a text-mask boundary would otherwise make the energy discontinuous and LM would stall on it. |
| `align.py`, `gates.py`, `recovery.py` need **no cv2** | They consume the arrays `evidence.py` built and do their own gradients with scipy, so 27 Step 4 tests run on a bare host in ~1.5 s. Only `evidence.py` and `runner.py` touch cv2. |
| ICP normals come from the gradient of a blurred curve raster | Blurring a one-pixel curve gives a ridge whose gradient is the normal by construction, and it works for coastline, lakes and rivers alike without special-casing. |
| `AffineModel.measure_against()` added | A model from the optimiser arrives with no residuals and reported its error as "unknown". It now gets measured against the control points on the way into the pipeline. |
| Georeferencing runs OCR regardless of `enable_text_extraction` | Recorded in §7b as decided; now implemented in the task. Costs ~135 s/map on CPU, only when alignment is on. |

### The ladder: what is implemented, and what is not

Rungs **1 (re-anneal wider), 2 (multi-start), 3 (raise `w_gcp`)** and **7 (GCP-only)** are
implemented. On this case none is exercised, because rung 0 passes.

Rungs **4, 5 and 6 are not implemented**, and that is a real gap rather than an oversight:

- **4 — reduce DOF to a 4-parameter similarity.** Needs a second model class. Cheap, and worth
  doing when a map appears that fails rungs 0–3.
- **5 — restrict evidence to arcs near detected water.** Needs a water mask, and the one test
  case has none. Untestable today.
- **6 — regional acceptance.** Anticipates the λ(x) field of roadmap §6 and is the most
  involved of the three.

Since rung 0 passes on the only case available, building 4–6 would mean writing recovery paths
that nothing can exercise. They stay recorded rather than written.

### Owed to whoever picks this up

1. **A second test case is now the bottleneck for everything.** The go/no-go, whether ICP earns
   its place, whether the gates discriminate, and rungs 4–6 all need one. §4's estimate of
   roughly an hour of rough clicking still stands, and it is the highest-value hour left in the
   plan.
2. **A case with water pipetted**, separately. The water gate has never been evaluated — it
   reports `applicable: false` on every run so far.
3. **Every Tier 3 constant is a guess**: the annealing schedules, the 30° orientation tolerance,
   the ICP radii, the straight-line distance penalty, the gate thresholds. They live in
   `GeorefConfig` (now version 4) so they can be tuned as a set, and none has been.
4. ~~**ICP's negative delta needs explaining.**~~ There was no delta: −0.0006 sat inside the
   ±0.012 snapping artifact (§8c). ICP has still never been isolated on a clean measurement —
   the corrected +0.0040 is chamfer **and** ICP together. Separating them needs a second case,
   which is item 1.
6. **Rungs 4–6 of the ladder remain unimplemented**, and rung 0 still passes on the only case
   available, so nothing exercises them. Rung 5 additionally needs a water mask that no case
   has. See "The ladder" above.
7. **The debug dump is throwaway** (§8e). It writes ~9 MB per import and exists to answer "why
   did this map place badly". Delete it or put it behind a real debug flag before this is
   considered finished.
5. ~~**`ENABLE_COASTLINE_SNAPPING` is still on.**~~ Measured and resolved in §8c: it puts a
   step function into the metric and hides alignment improvements. Now switchable via
   `GEOREF_ENABLE_COASTLINE_SNAPPING`, still defaulting to on so nothing changes silently.
   **Judge alignment with it off.**

---

## 9. Step 5 — cities as GCPs (post-PoC, well-specified)

> **Landed** — see [`city-gcps.md`](city-gcps.md). It departs from this section in three
> places, by decision: the gazetteer does **reject** unknown names (no fallback to a manual
> click on the reference map), city σ is **equal** to SIFT σ rather than an order of
> magnitude larger, and cities **do** pin the piecewise correction.

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
| 4 | 4–6 days | **Yes, gated**, on in the app | Chamfer + normal-search ICP + gates + ladder → §8b, §8c, §8d |
| 5 | post-PoC | Yes | Cities as GCPs |

Steps 0–4 is a week and a half and answers the only question that matters. Everything in the
roadmap is conditional on that answer.
