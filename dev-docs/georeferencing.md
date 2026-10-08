# Georeferencing — how it works now

What the code on `georef-exp` does today, end to end. This document describes; it does not
argue. Why the pipeline is shaped this way is in
[`georeferencing-history.md`](georeferencing-history.md), what the measurements say is in
[`georeferencing-testing.md`](georeferencing-testing.md), and what comes next is in
[`georeferencing-roadmap.md`](georeferencing-roadmap.md). Using the dev-test harness is in
[`dev-test-tool.md`](dev-test-tool.md).

Keep this document true: when the code changes, change it here.

**Status (2026-10-07).** Still experimental. The production defaults are the ones in
[§8](#8-configuration-and-switches): curve alignment is on everywhere at a coastline weight
of ×10, only on maps whose coastline the water picks identify, behind four lenient checks.
Still open: the transform model (piecewise today, affine expected);
[§10](#10-before-the-pull-request) lists what remains.

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
optional water picks), **Formes** (optional shape clicks). Control-point steps unlock once
the framing box exists.

`process_map_extraction(map_id)` (`app/tasks.py`) then reads everything from the session:

1. Load the image.
2. If text extraction is on, detect cities in the OCR text (point features in lon/lat, no
   transform involved).
3. **Place the map once** (`place_map`): select the control points the config uses, and
   align against the coastline when alignment is on ([§5](#5-the-transform)). Shapes and
   colours share this one transform.
4. Shapes, when the user clicked any (**Formes** step): one flood fill per click
   (`extract_shapes_from_clicks`), georeferenced without the coastline snap or the land
   clip (`MapPlacement.georeference(..., clean=False)`), since a shape may sit at sea.
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
`control_points.py`); a city also carries `city: {id, name}` (its GeoNames id).

- **SIFT points.** `sift_key_points_finder.py` renders the Natural Earth coastline and the
  lake shorelines over the framing box (1024×768), separately, runs SIFT on each render, and
  returns up to 15 keypoints by **farthest-point sampling**: the strongest coastline keypoint
  first, then always the candidate farthest from those chosen. **Coastline first:** a lake
  keypoint is taken only when no coastline candidate is at least 5% of the diagonal from every
  chosen point, because a map may omit or distort a lake but always draws its coast. Below
  that spacing the same rule continues down to a 1% duplicate floor. Each keypoint says which
  curve it lies on (`feature`). SIFT never runs on the user's map: it only suggests distinctive
  bits of real coastline, and the user picks which ones to click on their map.
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

- **Text first.** With OCR boxes available (`text_aware_zone_fill`), label ink is erased
  from the image before classification. Two ways to find and repaint it
  (`text_inpaint_algo`): **`palette`** (production) takes the background colours in a ring
  around each box, calls ink whatever is far from them, and gives each ink pixel the colour
  most voted by its known neighbours, so a name written over a zone comes back as that zone;
  **`telea`** splits ink from background by brightness and fills it with OpenCV's Telea
  inpainting, a weighted average that can blend two zone colours. An earlier `label` method,
  which repaired the zones after classification instead, was removed after losing on every
  corpus case.
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

`fit_affine_from_control_points` (`affine.py`): least squares, pixel → EPSG:3857, six
parameters, ≥ 3 points. Always fitted and always recorded (`models.gcp_affine` in the run
record): it is the baseline every alignment is compared to. With exactly 3 points the fit is
exact and its error is reported as unknown (`rmse_status = no_redundancy`), not 0.

### 5.2 Curve alignment

On when `enable_curve_alignment` is true (the default, [§8](#8-configuration-and-switches)).
Entry point `runner.align_map`; the fit and its checks are in `gates.py`, the optimiser in
`align.py`.

**How the coastlines are matched.** Alignment does not start from nothing: it starts from the
control-point affine (§5.1), which already places the map roughly. Everything below refines
that affine; nothing ever searches the world for where the map might be.

1. **Reference side** (`reference.py`). The Natural Earth coastline and lake shorelines inside
   the framing box are rasterised (1024×768, cached on the box) and sampled into points along
   each curve, in EPSG:3857, each with the direction of its curve.
2. **Map side** (`evidence.py`). Canny edges on the user's image, with the OCR boxes (dilated
   7 px) and the legend masked out, and long straight lines (neatlines, graticules, frames,
   found with Hough) down-weighted to 0.15. The water picks give a water mask, split into ocean
   (the largest component touching the image border) and lakes, and **only edges on the
   water/land boundary are kept**. That is what identifies the map's coastline: rivers, borders
   and roads lie inside the land and are dropped.
3. **The loop** (`align.py`). Push every reference point *into the image* through the current
   affine; measure how far each lands from the map's coastline edges; nudge the affine's six
   parameters to bring them closer, while keeping the control points close to where the user
   clicked:

```
E = w_gcp · Σ ||T(p_j) − q_j||²   +   w_curve · Σ ρ_tukey( D_map(T(s_i)) )
```

- control points: plain least squares, so every point always pulls;
- curve samples `s_i`: Tukey-robust, so a sample whose nearest map edge is far contributes
  nothing (a stretch of coast the map does not draw, or draws elsewhere);
- each term normalised by its own count, so `weight_gcp` / `weight_curve` (1 / 10) are true
  relative weights;
- samples under a label or off the image are *unseen*: each annealing level fits a frozen set
  of samples in view, and one that leaves view costs the outlier constant.

Three stages, each starting from the previous one's result:

| Stage | Evidence | How it measures "distance to the map's coast" |
|---|---|---|
| A1 coarse chamfer | coastline only | Distance to the **nearest** coastline edge pixel, read from a distance map blurred 64 → 14 px, Tukey cutoff 400 → 110 px. No pairing: wide reach, a basin of attraction |
| A2 fine chamfer | coastline + lakes | Same, blur 8 → 0 px, cutoff 70 → 18 px |
| B ICP | coastline + lakes | Each reference point searches along its own curve's normal (40 → 5 px) for a map edge **with the same orientation (±30°)**, and is paired with it. Precise, and ignores lines crossing the coast, but blind beyond its search radius |

**Chamfer and ICP.** They answer the same question at different ranges. The chamfer gets the
map into the right basin when the control-point affine leaves the coast tens of pixels off;
ICP makes the final, orientation-aware lock. With the coastline identified by the water
filter, the chamfer's job is reach, and it is needed: ICP alone (`enable_chamfer` off) is
worse on 9 of 14 cases, most on maps whose control points cover one part of the map, where
the coast elsewhere starts beyond ICP's radius
([testing §8.9](georeferencing-testing.md#89-icp-only-2026-10-07)). Both stay.

**Precondition: an identified coastline** (`runner.align_map`). Alignment only runs when the
map's coastline can be told apart from its other lines, which is what the water filter does.
It is skipped, and the map placed by the control-point affine alone, when:

| `skipped` | When |
|---|---|
| `no_water_picks` | the map has no water pick (unpainted sea, landlocked map) |
| `water_mask_too_small` | the water mask covers less than 1% of the image (`edge_water_min_fraction`): more likely a stray pick on a legend swatch than the sea |
| `no_coast_evidence` | the framing box has no coastline, or no edge survives the filter |
| `alignment_inputs_failed`, `alignment_raised` | an error while building the layers or fitting; logged |

**The checks** (`gates.py`). One fit, then four sanity checks on its result. Any failure means
the control-point affine is used (`method: gcp_only`, the failed checks recorded). They are set
leniently on purpose: matching the right curves is the precondition's job, and these only catch
a fit that went somewhere absurd.

| Check | Fails when | Threshold |
|---|---|---|
| `transform_determinant` | the aligned transform is mirrored or folded | sign change |
| `curve_fit_engaged` | the coastline matches *worse* than under the control points | improvement < 0 (`gate_min_chamfer_improvement`) |
| `water_agreement` | the map's water, warped in, overlaps the real water clearly less than under the control points: a sea put on the wrong side of a coast | drop > 0.10 IoU (`gate_water_iou_max_drop`) |
| `control_points_held` | the fit moved the map far off the user's own clicks | RMS rise > 5% of the image diagonal (`gate_max_gcp_shift_ratio_of_diagonal`); the corpus at ×10 rose 0.4–3.6 px |

There is no retry: a failure goes straight to the control-point affine. Logged with every run
but never checked: scale and rotation drift, optimiser convergence, inlier fraction, ICP
correspondences, the chamfer residuals and how far the coast moved.

The result carries `method` (`joint` or `gcp_only`), `skipped` (a precondition, or null) and
`failedChecks`; features get `alignment_method`. Why the checks look like this, and what they
replaced (a probe fit, eight neutralised gates and a recovery ladder):
[history, 2026-10-07](georeferencing-history.md#2026-10-07--alignment-on-everywhere-and-the-checks-redesigned).

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
- **`auto`** (the default): the affine's RMS residual on the control points it was fitted to,
  in image pixels, against `auto_piecewise_rmse_ratio_of_diagonal` (0.01) of the image
  diagonal. At or under it the affine is kept; over it, `piecewise_affine` is applied. With 3
  points the fit is exact and the affine is kept. The run record has `autoAffineRmsePx`,
  `autoThresholdPx` and `autoChoseModel`. The threshold is a first guess, not measured.

`auto` is a first step toward letting piecewise earn its place per map. The roadmap's
version compares leave-one-out errors instead of an in-sample threshold
([roadmap](georeferencing-roadmap.md#2-transform-model-affine-by-default-piecewise-by-leave-one-out)).

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
- **Debug dumps** (`debug.py`) when `GEOREF_DEBUG=true` (off by default; set on
  `celery-worker` in `docker-compose.yml`): a folder of overlays and a `summary.txt` per
  import under `Backend-Atlas/debug_runs/` (newest 20 kept), or per case under
  `alignment_debug/`.

---

## 8. Configuration and switches

<<<<<<< HEAD
Every hyperparameter is a field of `GeorefConfig` (`config.py`, `CONFIG_VERSION` 19), so a run
records exactly what it used and a variant is a set of overrides. `ambient_georef_config()`
applies the environment:

| Variable | Default | `backend`, `celery-worker` | `test-backend`, `georef-dev` |
|---|---|---|---|
| `GEOREF_ENABLE_CURVE_ALIGNMENT` | true | on | **off** |
| `GEOREF_ENABLE_COASTLINE_SNAPPING` | true | on | on |
| `GEOREF_DEBUG` | off | on | off |
=======
Every hyperparameter is a field of `GeorefConfig` (`config.py`, `CONFIG_VERSION` 15), so a run
records exactly what it used and a variant is a set of overrides. **The file defaults are the
production configuration**, and every container runs them: the app, the regression suite, the
dev-test UI and the CLI. `ambient_georef_config()` lets a deployment override two of them
from the environment (`GEOREF_ENABLE_CURVE_ALIGNMENT`, `GEOREF_ENABLE_COASTLINE_SNAPPING`);
none does. `GEOREF_DEBUG` (off by default, on for `celery-worker`) only writes diagnostics.
>>>>>>> d64ed9e18b630019801f49502b7300c181814c05

Current defaults, and where each stands:

| Setting | Value | Status |
|---|---|---|
| Curve alignment | on | Supported by the first corpus run: lower check-point error on 11 of 12 cases, worse on none |
| `weight_curve` / `weight_gcp` | 10 / 1 | The gain grows to ×30 and stops there, mostly at the coast ([testing §8](georeferencing-testing.md#8-results)). ×10 takes most of it (10 of 12 cases better, the 2 worse within 0.7 km) and leaves the control points more say inland |
| `enable_icp` | on, 30° | Kept: removing it is worse at high weight |
| `transform_model` | `auto` | Affine unless its GCP RMS exceeds 1% of the image diagonal; threshold not measured yet |
| `snap_to_coastline` | on | Kept: improves the shipped zones on 9 of 12 cases, worse on none |
| `clip_to_land_mask`, lake cut | on | Kept (production behaviour; expected zones are cut the same way when scored) |
| Text fill | `palette` inpaint | Kept; `label` was worse on every case and was removed. `telea` kept, unmeasured |
| `zone_gap_fill` | off | Off: worse in its current form |
| Checks | 4, lenient, behind a water precondition | Redesigned 2026-10-07 ([§5.2](#52-curve-alignment)) |

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
6. **No water picks, no alignment.** A map with an unpainted sea cannot have its coastline
   identified, so it is placed by its control points alone.
7. **Unequal σ would break the GCP normalisation.** The term is normalised by point count and
   median σ; if SIFT and city σ ever differ, normalise by the sum of weights instead.
8. **The gazetteer has no historical names** and only places of 15,000+ inhabitants.

---

## 10. Before the pull request

Done: every container runs the production configuration (alignment on, ×10), so the
regression suite measures what ships; rivers, the `label` text fill and unused switches are
removed; the debug dumps are off by default. Still to settle before `georef-exp` is merged:

1. **The regression baselines.** Every case's `best` was recorded under the old defaults
   (alignment off in the suite, ×1). Run the suite once and promote each case's run
   (`scripts/force_promote_georef_best.py`), so `best` is the production number.
2. **The transform model** default ([§5.3](#53-transform-model)).

---

## 11. Code map

`Backend-Atlas/app/utils/georeferencing/`:

| Module | Role |
|---|---|
| `config.py` | `GeorefConfig`, `CONFIG_VERSION`, environment switches |
| `control_points.py` | `ControlPoint`, `CityRef`, parsing, per-source selection and weights |
| `affine.py` | `AffineModel` (fit, apply, inverse, serialize) |
| `piecewise.py` | `PiecewiseAffineModel`, leave-one-out |
| `projection.py` | EPSG:3857 maths, km units |
| `frame.py`, `inputs.py` | framing box; `maps.georef_inputs` |
| `reference.py` | reference rasters and distance fields over the framing box |
| `evidence.py` | map-side edges, straight-line weighting, water mask (cv2) |
| `align.py` | chamfer, ICP, Tukey, the objective |
| `gates.py` | the alignment attempt and its four checks |
| `runner.py` | image → checked alignment (cv2); the water precondition |
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
`ne_ocean_points` (seeds for the land mask).
The land mask is built by polygonising the coastline together with the world boundary and
marking every face that contains an ocean seed point as ocean. `borders/` (gitignored) holds
admin-0/admin-1 files for the dev-test zone editor only.
