# Georeferencing — how it works now

What the code on `georef-exp` does today, end to end. This document describes; it does not
argue. Why the pipeline is shaped this way is in
[`georeferencing-history.md`](georeferencing-history.md), what the measurements say is in
[`georeferencing-testing.md`](georeferencing-testing.md), and what comes next is in
[`georeferencing-roadmap.md`](georeferencing-roadmap.md). Using the dev-test harness is in
[`dev-test-tool.md`](dev-test-tool.md).

Keep this document true: when the code changes, change it here.

**Status (2026-10-05).** Still experimental. The production defaults are the ones in
[§8](#8-configuration-and-switches), and two of them are expected to change after the first
corpus runs: the transform model (piecewise today, affine expected) and the coastline weight.
[§10](#10-before-the-pull-request) lists what must be settled before `georef-exp` is merged.

---

## 1. The problem and the shape of the answer

Extraction produces zones in **image pixels**. Georeferencing answers *where on Earth is each
pixel*, using:

- **control points**: pixels the user matched to real positions (SIFT coastline keypoints,
  named cities);
- **the reference coastline** (Natural Earth), which the map's own drawn coast is aligned to;
- **the framing box**: the world area the user said the map shows, which bounds every
  reference layer.

The fit happens in **EPSG:3857** (Web Mercator, in metres): planar like pixels, and conformal,
so shapes are right and only the scale is off by `1/cos(φ)`. Every distance reported in km
applies that correction at the framing box's centre latitude. Output is EPSG:4326.

One transform is fitted per map and shared by everything the map produces (shapes and colour
zones).

```
inputs (control points, framing box, legend, pipette picks)
  -> pixel zones (colour extraction, OCR-aware)
  -> control-point affine
  -> curve alignment (optional)          coastline -> better affine
  -> transform model                      affine | piecewise correction
  -> cleaning                             snap to coast, clip ocean and lakes
  -> EPSG:4326, saved with the map
```

---

## 2. The production flow (import session)

The import is a server-side session (`map_imports` table, `app/routers/imports.py`,
`app/services/imports.py`), mirrored in the frontend by `stores/importSession.ts` and shown by
`ImportView.vue` as a checklist.

| Call | What happens |
|---|---|
| `POST /imports` | The image is stored on the session and **OCR starts immediately** (`run_map_ocr`), so it runs while the user clicks. |
| `GET /imports/{map_id}`, `/image` | Restore an import in progress, image included. |
| `PUT /imports/{map_id}/inputs` | Save a confirmed step. `null` clears an entry. A *changed* framing box drops the control points (they were matched inside the old one); a first box keeps them. |
| `POST /imports/{map_id}/extract` | Starts the extraction if OCR is done; otherwise the session waits (`waiting_for_text`) and `run_map_ocr` dispatches it when the text is ready. A failed OCR is retried. |
| `POST /imports/{map_id}/cancel`, `DELETE` | Cancel keeps the entries; delete drops the session. |

The checklist steps: **Zone sur le monde** (framing box), **Légende** (rectangle or "no
legend"), **Points SIFT** (≥ 3 pairs), **Villes** (optional), **Couleurs** (zone picks, plus
optional water picks). Control-point steps unlock once the framing box exists.

`process_map_extraction(map_id)` (`app/tasks.py`) then reads everything from the session:

1. Load the image.
2. If text extraction is on, detect cities in the OCR text (point features in lon/lat, no
   transform involved).
3. **Place the map once** (`place_map`): select the control points the config uses, and
   align against the coastline when alignment is on ([§5](#5-the-transform)). Shapes and
   colours share this one transform.
4. Shapes extraction, if on, georeferenced (`MapPlacement.georeference`).
5. Colour extraction from the pipette picks ([§4](#4-pixel-zones)), georeferenced.
6. Save the features and `maps.georef_inputs` (the control points, box, legend and picks the
   map was georeferenced from), and close the session.

A map without a framing box or at least 3 control points cannot be extracted: the checklist
requires them, and `place_map` refuses to run without them.

**One pipeline everywhere.** `app/utils/extraction_steps.py` holds the steps:
`extract_zone_colors`, `place_map`, `MapPlacement.georeference`. The dev-test task
(`process_dev_test_extraction(test_id, test_case)`, which reads the case's `config.json` and
the test's stored image), the CLI `scripts/run_georef_alignment.py` and the variant runner all
call them, and differ only in where inputs come from and results go. Under the same settings
they produce identical zones.

---

## 3. Inputs

**Control points** are one list of `{source, pixel, geo}` records (`ControlPoint`,
`models.py`); a city also carries `city: {id, name}` (its GeoNames id).

- **SIFT points.** `sift_key_points_finder.py` renders the Natural Earth coastline over the
  framing box (1024×768), runs SIFT on the render, and returns up to 15 keypoints by
  **farthest-point sampling** (strongest first, then always the candidate farthest from those
  chosen; margins are ratios of the raster diagonal). Lakes are always drawn into the render
  too: a line marked `TODO ... testing modification` adds them up front, which makes the
  older "add lakes when the coast gives too few" fallback after it dead code. SIFT never runs
  on the user's map: it only suggests distinctive
  bits of real coastline, and the user clicks where their map draws each one.
- **Cities.** The user types a name; `city_gazetteer.py` searches GeoNames `cities15000`
  (a SQLite file built from the pinned `geonamescache`, under `app/.cache/`) inside the
  framing box, matching accents, prefixes and alternate names. The user picks a candidate and
  clicks it on the map. Unknown names (most historical ones) return nothing.
- Both sources are weighted equally (`gcp_sigma_px_sift = gcp_sigma_px_city`). `gcp_sources`
  can restrict a run to one of them.

**Framing box** (`frame.py`): `{west, south, east, north}`, antimeridian-safe. It is the extent
of every reference raster, so it must enclose the map.

**Legend**: a rectangle in pixels, or an explicit "no legend". The rectangle is excluded from
colour extraction and from the alignment evidence.

**Pipette picks** (`imposed_colors.py`): normalised `(x, y)`, a name, a sampling radius, and a
kind, `zone` or `water`. Water is picked separately because zones and sea are often the same
hue.

**Check points** exist only in dev-test cases (`georef.checkPoints`): points clicked like
control points but never given to anything that fits. See
[testing §3](georeferencing-testing.md#3-check-points).

---

## 4. Pixel zones

`color_extraction.py`, called through `extract_zone_colors`:

- **Text first.** With OCR boxes available, label ink is erased from the image before
  classification (`text_fill_method = "inpaint"`, palette mode): each ink pixel takes the
  colour most voted by its known neighbours, so a name written over a zone comes back as that
  zone.
- **Classification.** Every pixel is assigned to the nearest picked colour in CIELAB
  (ΔE2000), within a threshold; the legend rectangle is excluded. Zones are therefore an exact
  pixel partition.
- **Clean-up** per zone: opening, closing, hole filling.
- **Vectorising** per zone, independently (`cv2.findContours`, outer rings and holes), then
  simplified.
- **Shared borders (off).** `zone_gap_fill` closes the thin unassigned band a drawn border
  line leaves between two zones, settles each pixel on one zone, and vectorises all zones
  together so neighbours share one border. It scored badly in the first corpus run; see
  [§9](#9-known-limitations).

---

## 5. The transform

### 5.1 Control-point affine

`fit_affine_from_control_points` (`models.py`): least squares, pixel → EPSG:3857, six
parameters, ≥ 3 points. Always fitted and always recorded (`models.gcp_affine` in the run
record): it is the baseline every alignment is compared to. With exactly 3 points the fit is
exact and its error is reported as unknown (`rmse_status = no_redundancy`), not 0.

### 5.2 Curve alignment

On when `enable_curve_alignment` is true (on in the app, [§8](#8-configuration-and-switches)).
Entry point `runner.align_map`, which needs the OCR boxes (labels must not become edges).

**Reference side** (`reference.py`), over the framing box at 1024×768, cached on the box and
the source files: coastline, lakes, rivers (loaded, **not used**), land (= not ocean; lake
interiors count as land), ocean, water, and distance fields.

**Map side** (`evidence.py`):

- Canny edges, with OCR boxes (dilated 7 px) and the legend masked out;
- long straight lines (neatlines, graticules, frames) found with Hough and down-weighted to
  0.15, not deleted;
- with water picks: a water mask split into ocean (largest border-touching component) and
  lakes, and **only edges on a water/land boundary are kept** (`edge_water_filter`). Without
  water picks every remaining edge is candidate coastline, and only the robust loss keeps
  borders and rivers out of the fit.

**The fit** (`align.py`) optimises the six affine parameters, starting from the control-point
affine:

```
E = w_gcp · Σ ||T(p_j) − q_j||²   +   w_curve · Σ ρ_tukey( D_map(T(s_i)) )
```

- control points: plain least squares, so every point always pulls;
- curve samples `s_i` (reference coastline points pushed into the image): Tukey-robust, so a
  sample whose nearest map edge is far contributes nothing;
- each term normalised by its own count, so `weight_gcp` / `weight_curve` are true relative
  weights;
- samples under a label or off the image are *unseen*: each annealing level fits a frozen set
  of samples in view, and one that leaves view costs the outlier constant.

Three stages, each initialising the next:

| Stage | Evidence | Schedule |
|---|---|---|
| A1 coarse chamfer | coastline only | blur 64 → 14 px, Tukey cutoff 400 → 110 px |
| A2 fine chamfer | coastline + lakes | blur 8 → 0 px, cutoff 70 → 18 px |
| B ICP | coastline + lakes | search along the curve normal, 40 → 5 px; matched edge must agree in orientation within 30°; cutoff 20 px |

**Probe.** The same fit with the control points left out. Its transform is discarded; only its
distance to the held-out control points is kept, as the `probe_gcp_disagreement` gate.

**Gates** (`gates.py`), all computed and logged on every run: `probe_gcp_disagreement`,
`water_mask_iou`, `transform_determinant`, `scale_drift`, `rotation_drift`,
`curve_fit_engaged`, `optimizer_converged`, `inlier_fraction`. **They are neutralised**
(thresholds set to always pass, designed values in comments in `config.py`). What can still
reject an alignment: a mirrored transform, a non-converged optimiser, or a coastline chamfer
that got worse.

**Recovery ladder** (`recovery.py`): on gate failure, rung 1 re-anneals wider, rung 2 tries
multi-start perturbations, rung 3 boosts the control-point weight ×8, and rung 7 falls back to
the control-point affine (`method: gcp_only`). Rungs 4–6 were designed and never built. Every
corpus run so far settled at rung 0.

The result carries `method` (`joint`, `joint_gcp_weighted`, `gcp_only`), `rung`, the failed
checks and the gate values; features get `alignment_method` and `alignment_rung`.

### 5.3 Transform model

`transform_model` decides what places the map, given the affine from §5.1 or §5.2:

- **`affine`**: that affine as-is.
- **`piecewise_affine`** (`piecewise.py`): the affine plus a correction that passes exactly
  through every control point. The control points and 8 anchors on a frame (padded 25% around
  image ∪ zones ∪ control points) are triangulated; inside each triangle the correction is
  linear; the anchors pin it to zero. Geometries are densified to 1% of the image diagonal
  first, so long edges bend with it. A triangulation that folds (two points swapped) is
  refused and the run uses the affine. Its reported error is leave-one-out, labelled
  `leave_one_out` (base refitted per fold) or `leave_one_out_fixed_base` (on the aligned
  affine, optimistic).

The default is `piecewise_affine` today. The first corpus run did not support it
([testing §10](georeferencing-testing.md#8-results)), and the expected change is to make
`affine` the default and let piecewise earn its place per map through a leave-one-out
comparison ([roadmap](georeferencing-roadmap.md#2-transform-model-affine-by-default-piecewise-by-leave-one-out)).

---

## 6. Cleaning

`pipeline.georeference_features`, per zone, after the transform:

1. **Raw copy.** The zone straight out of the transform is kept (`raw_collections`, property
   `cleaned: false`). Dev-test runs score it separately; production does not save it.
2. **Coastline snap** (`snapping.py`, `snap_to_coastline`): every boundary vertex within the
   tolerance of the Natural Earth coastline moves onto it. Tolerance: 1.5% of the image
   diagonal, converted to metres with the transform's scale. Nearest point, no orientation
   test.
3. **Clip to land** (`clip_to_land_mask`): intersect with land minus ocean **and lakes**
   (`cleaning.py`, `land_mask_3857`; the same mask cleans expected zones in dev-test). A zone
   with less than 1% of its area left is dropped.
4. Convert to EPSG:4326 and attach `crs`, `transform_method`, `rmse_km`, `alignment_*`.

---

## 7. What a run leaves behind

- **Production:** the features, and `maps.georef_inputs` (version 2), which is enough to
  re-georeference the map without re-clicking. Nothing reads it yet.
- **Run record** (`records.py`, schema 2; dev-test and CLI runs, as `run_record.json`): the
  inputs, the models (`gcp_affine`, `aligned_affine`, `applied`), every gate, errors
  (`gcpRmseKm` with `gcpRmseKind`, per-source error, check points), per-phase timings, the
  config and any per-run switches.
- **Debug dumps** (`debug.py`) when `GEOREF_DEBUG=true` (set on `backend` and
  `celery-worker`): a folder of overlays and a `summary.txt` per import under
  `Backend-Atlas/debug_runs/` (newest 20 kept), or per case under `alignment_debug/`.
  Throwaway; to remove before the PR ([§10](#10-before-the-pull-request)).

---

## 8. Configuration and switches

Every hyperparameter is a field of `GeorefConfig` (`config.py`, `CONFIG_VERSION` 14), so a run
records exactly what it used and a variant is a set of overrides. `ambient_georef_config()`
applies the environment:

| Variable | Default | `backend`, `celery-worker` | `test-backend`, `georef-dev` |
|---|---|---|---|
| `GEOREF_ENABLE_CURVE_ALIGNMENT` | true | on | **off** |
| `GEOREF_ENABLE_COASTLINE_SNAPPING` | true | on | on |
| `GEOREF_DEBUG` | off | on | off |

Current defaults, and where each stands:

| Setting | Value | Status |
|---|---|---|
| Curve alignment | on in the app | Supported by the first corpus run: lower check-point error on 11 of 12 cases, worse on none |
| `weight_curve` / `weight_gcp` | 1 / 1 | The run favoured ×30 (gain stops there); not changed yet. The gain is mostly at the coast ([testing §10](georeferencing-testing.md#8-results)) |
| `enable_icp` | on, 30° | Kept: removing it is worse at high weight |
| `transform_model` | `piecewise_affine` | Not supported by the run; expected to become `affine` |
| `snap_to_coastline` | on | Kept: improves the shipped zones on 9 of 12 cases, worse on none |
| `clip_to_land_mask`, lake cut | on | Kept (production behaviour; expected zones are cut the same way when scored) |
| `text_fill_method` | `inpaint` | Kept: `label` is worse on every case |
| `zone_gap_fill` | off | Off: worse in its current form |
| Gates | neutralised | To decide; no run has given them anything to predict |

---

## 9. Known limitations

Verified in the code. Ordered roughly by impact.

1. **Colour collisions.** A country the user did not pick, painted in the same colour as one
   they did, is classified into it (Sudan into "Algérie" on the Maghreb map). Only the picked
   colours exist, and nothing ties a zone to the area around its pick.
2. **One affine for the whole map.** A large map drawn in another projection (east asia) has
   no affine that fits it: the control points themselves are 20–60 km off any affine. With a
   high coastline weight, alignment fits the coast and the interior pays.
3. **Piecewise after alignment re-pins every click**, undoing the coastline's contribution near
   each control point.
4. **Neighbouring zones do not share borders.** Each zone is vectorised and snapped on its own,
   so a drawn border between two zones leaves a gap, and snapping can move one side only.
   `zone_gap_fill` addresses the first part but is off.
5. **Snapping is blind:** nearest point, no orientation test, and the ring is closed by copying
   the first vertex over the last rather than snapping both consistently.
6. **The ladder cannot recover from its main gate** (the probe is computed once, so
   `probe_gcp_disagreement` is the same on every rung) and multi-start rotates around pixel
   (0, 0), not the image centre. Unreachable while the gates are neutral.
7. **The probe starts from the control-point affine**, so with weak coastline evidence it stays
   near the clicks and "agrees" with them: it measures drift more than independent agreement.
8. **Unequal σ would break the GCP normalisation.** The term is normalised by point count and
   median σ; if SIFT and city σ ever differ, normalise by the sum of weights instead.
9. **The gazetteer has no historical names** and only places of 15,000+ inhabitants.

---

## 10. Before the pull request

Agreed to be done before `georef-exp` is merged, once the production configuration is settled:

1. **One pipeline everywhere.** The regression suite (CI, `test-backend`) currently runs with
   alignment off and measures the control-point floor, while the app ships alignment + the
   transform model + cleaning. The suite must run the production configuration, and so must a
   regression re-run from the dev-test UI. Today a regression case's `best` can come from
   either container, so it can mix alignment off and on.
2. **Settle the defaults** of [§8](#8-configuration-and-switches): transform model, coastline
   weight, gates kept or removed.
3. **Remove the debug dumps** (`debug.py`, `GEOREF_DEBUG`), or put them behind a real
   developer flag.
4. Remove what only served experiments and lost: ladder rungs and gates if dropped, unused
   switches, and the always-on lakes "testing modification" in `sift_key_points_finder.py`
   (keep it or restore the fallback, deliberately).

---

## 11. Code map

`Backend-Atlas/app/utils/georeferencing/`:

| Module | Role |
|---|---|
| `config.py` | `GeorefConfig`, `CONFIG_VERSION`, environment switches |
| `models.py` | `ControlPoint`, `AffineModel` (fit, apply, inverse, serialize) |
| `piecewise.py` | `PiecewiseAffineModel`, leave-one-out |
| `projection.py` | EPSG:3857 maths, km units |
| `frame.py`, `inputs.py` | framing box; `maps.georef_inputs` |
| `reference.py` | reference rasters and distance fields over the framing box |
| `evidence.py` | map-side edges, straight-line weighting, water mask (cv2) |
| `align.py` | chamfer, ICP, Tukey, the objective |
| `gates.py`, `recovery.py` | named checks; the ladder |
| `runner.py` | image → gated alignment (cv2) |
| `pipeline.py` | transform → snap → clip → EPSG:4326 |
| `snapping.py`, `cleaning.py` | the snap; the shared ocean + lake mask |
| `records.py`, `diagnostics.py`, `debug.py`, `gcp_overlay.py` | run record; dev-tool diagnostics; debug dumps; control-point overlay |
| `checkpoints.py`, `requirements.py` | dev-test only: check points; what a case must have |

Elsewhere: `app/utils/extraction_steps.py` (`extract_zone_colors`, `place_map`,
`MapPlacement`: the steps every entry point shares),
`color_extraction.py`, `sift_key_points_finder.py`, `city_gazetteer.py`,
`coastline_land_mask.py`.

**Reference data** (`Backend-Atlas/app/geojson/`, all Natural Earth): `ne_coastline` (keypoints,
alignment, snapping, land mask), `ne_50m_lakes` (keypoints, alignment, lake cut),
`ne_ocean_points` (seeds for the land mask), `ne_50m_rivers_lake_centerlines` (loaded, unused).
The land mask is built by polygonising the coastline together with the world boundary and
marking every face that contains an ocean seed point as ocean. `borders/` (gitignored) holds
admin-0/admin-1 files for the dev-test zone editor only.
