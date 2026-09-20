# Georeferencing — Current Implementation

Reference description of how georeferencing works today, end to end. Written as of
2026-09-19 (branch `main`). This document is descriptive, not aspirational: it describes
what the code does, including its quirks. The planned replacement is in
[`georeferencing-plan.md`](georeferencing-plan.md); anything beyond the proof of concept
is in [`georeferencing-roadmap.md`](georeferencing-roadmap.md).

---

## 1. What georeferencing does here

Extraction (colors, shapes) produces GeoJSON whose coordinates are **image pixel
positions**. Georeferencing answers: *where on Earth is each of these?*

The answer is built from a handful of user-supplied control point pairs — a pixel
position on the scanned map, matched to a longitude/latitude — fitted into a single
affine transform, then cleaned up against a reference coastline.

Output is GeoJSON in EPSG:4326, persisted one feature per row.

---

## 2. End-to-end flow

```
FRONTEND                             BACKEND
--------                             -------
ImportView.vue
  |
  |- user draws world area box  ---> POST /projects/coastline-keypoints
  |  (GeoRefSiftWorldMap.vue)         |- find_coastline_keypoints()
  |                                   |  rasterize coastline -> SIFT -> <=10 keypoints
  |  <--------------------------------- keypoints [{pixel, geo, response}]
  |
  |- user matches keypoints to
  |  their map (GeoRefSiftModal.vue
  |  + GeoRefImageMap.vue)
  |
  |- user pipettes zone colors
  |- user draws legend box
  |
  |- startImport() ----------------> POST /projects/upload
     (useImportProcess.ts)            |- parse + validate
                                      |- Celery: process_map_extraction
                                         |- text extraction   (optional)
                                         |- city detection    (optional)
                                         |- shapes extraction (optional) --+
                                         |- color extraction  (optional) --+
                                         |                                 |
                                         |  georeference_features_with_sift_points
                                         |     |- fit affine (pixel -> EPSG:3857)
                                         |     |- snap to coastline
                                         |     |- clip to land mask
                                         |     |- convert -> EPSG:4326
                                         |                                 |
                                         |- persist_features <-------------+
```

---

## 3. Stage A — control point acquisition

### 3.1 The framing box

`ImportView.vue` holds `worldAreaBounds` (`{west, south, east, north}`) and
`worldAreaZoom`, set when the user selects a region on the world map
(`GeoRefSiftWorldMap.vue`).

Its **only** current use is as the argument to the coastline-keypoints request. It is
called out here because it is *not* forwarded to `/projects/upload` — see
[§9, limitation 3](#9-known-limitations-and-quirks).

### 3.2 Coastline keypoint suggestion

`POST /projects/coastline-keypoints` → `find_coastline_keypoints(bounds, width=1024, height=768)`
in [`sift_key_points_finder.py`](../Backend-Atlas/app/utils/sift_key_points_finder.py).

1. Allocate a blank grayscale image of `width × height`.
2. `draw_geojson_features()` rasterizes `ne_coastline.geojson` into it, projecting lon/lat
   linearly onto the raster via `draw_coastline()`:
   `px = (lon − west)/(east − west) · width`, `py = (north − lat)/(north − south) · height`.
   Points outside the bounds are dropped; the rest are drawn as 3px antialiased polylines.
3. `detect_sift_keypoints_on_image()`: Gaussian blur → Canny(75, 175) → `cv2.SIFT_create()`
   using the edge map as a mask.
4. Filter: at least `BORDER_MARGIN = 20` px from any edge; sort by response descending;
   greedily keep keypoints at least `MIN_DISTANCE_BETWEEN_KEYPOINTS = 10` px apart; stop at
   `NUMBER_OF_KEYPOINTS = 10`.
5. If fewer than 10 survive, `ne_50m_lakes.geojson` is drawn into the *same* image for extra
   inland detail and detection re-runs. The response reports `used_lakes`.
6. Each keypoint is converted back to lon/lat with the inverse of the step-2 mapping.

**Important:** SIFT runs on a *synthetic render of the reference coastline*, never on the
user's map. It is a landmark *suggester* — "here are 10 visually distinctive bits of real
coastline in your region". The actual pixel↔geo pairing is a human decision.

This makes the module name `georeferencingSift.py` a misnomer: no SIFT runs inside it.

### 3.3 User matching

`GeoRefSiftModal.vue` shows the suggested keypoints; `GeoRefImageMap.vue` lets the user
click the corresponding position on their own map. The result is a list of
`GeorefMatch { index, world: [lat, lng], image: [x, y], color }` — see
[`georef.ts`](../Frontend-Atlas/src/typescript/georef.ts).

---

## 4. Stage B — the upload payload

`useImportProcess.startImport()` builds a `FormData`:

| Field | Content |
|---|---|
| `project_id`, `map_id` | UUIDs |
| `image_points` | JSON `[{x, y}]` — pixel coords |
| `world_points` | JSON `[{lat, lng}]` |
| `enable_georeferencing` / `_color_extraction` / `_shapes_extraction` / `_text_extraction` | booleans |
| `imposed_colors` | JSON `[{x, y, name, radius}]` — pipette picks, x/y **normalised to [0,1]** |
| `legend_bounds` | JSON `{x, y, width, height}` — pixel space |
| `file` | the image |

`POST /projects/upload` ([`projects.py`](../Backend-Atlas/app/routers/projects.py)):

- verifies the map belongs to a project owned by the caller;
- validates the file extension;
- when `enable_georeferencing` and both point arrays are present, parses them into
  `pixel_points_list` as `(x, y)` and `geo_points_list` as **`(lng, lat)`** — note the swap
  into GeoJSON axis order;
- rejects mismatched array lengths with HTTP 400;
- parses `imposed_colors` through the shared
  [`imposed_colors.py`](../Backend-Atlas/app/utils/imposed_colors.py) parser into
  `(click_positions, names, radii)`, which enforces normalised coords and a radius in
  `[1, 200]`;
- dispatches the Celery task.

The same parser serves the dev-test upload route, so the two stay in sync.

---

## 5. Stage C — where georeferencing sits in the extraction task

`process_map_extraction` in [`tasks.py`](../Backend-Atlas/app/tasks.py), six reported steps:

| Step | Work |
|---|---|
| 1 | Save upload to a temp file |
| 2 | Load and validate the image |
| 3 | Text extraction (optional) → `text_regions`; then city detection from that text |
| 4 | Shapes extraction (optional) → `shape_pixel_features` → **georeference** → persist |
| 5 | Color extraction (optional) → `pixel_features` → **georeference** → persist |
| 6 | Cleanup, debug output |

Georeferencing is therefore **not a pipeline step of its own**. It is invoked twice, inline,
once per producer of pixel-space features.

### 5.1 Relationship to the other extraction tools

- **Text extraction** produces `text_regions`, consumed by shapes extraction to drop contours
  overlapping labels. It does not feed georeferencing.
- **City detection** ([`cities_validation.py`](../Backend-Atlas/app/utils/cities_validation.py))
  matches recognised text against a `geonamescache` gazetteer loaded at import into a
  normalised-name → `[{name, lat, lon, country, population}]` map. Detected cities are written
  **directly in lon/lat** via `persist_city_feature` — they bypass the affine entirely, since
  their coordinates come from the gazetteer rather than from the map.
- **Shapes extraction** produces both `normalized_features` (0–1 relative coords) and
  `pixel_features`. Only the latter is georeferenceable.
- **Color extraction** is the main producer. `build_exclusive_masks_by_nearest_center()` assigns
  every pixel to exactly one pipetted color by nearest ΔE, so **zones are already a pixel-level
  partition**. `mask_to_geometry()` then vectorises each mask *independently* with
  `skimage.measure.find_contours`.

### 5.2 Fallback when there are no control points

Both call sites share one shape:

```python
if pixel_points and geo_points_lonlat:
    georef = georeference_features_with_sift_points(pixel_features, ...)
    persist_features(..., georef)
elif normalized_features:
    persist_features(..., normalized_features)   # 0-1 relative coords, NOT geographic
```

A map without control points still persists features — in normalised space.

---

## 6. Stage D — the transform

[`georeferencingSift.py`](../Backend-Atlas/app/utils/georeferencingSift.py),
`georeference_features_with_sift_points()`.

### 6.1 Validation

At least 3 pairs, equal counts, tuples rather than dicts. Raises `ValueError` / `TypeError`
otherwise; both call sites catch and log, persisting nothing for that producer.

### 6.2 Projection of the targets

Each `(lon, lat)` → WebMercator metres via `_lonlat_to_webmercator()`: spherical Mercator on
`R_EARTH = 6378137.0`, latitude clamped to ±89.9°.

The fit happens in a **planar** space because pixels are planar. Fitting lon/lat degrees
directly would bake latitude distortion into the model. WebMercator is conformal, so it is
locally isotropic — shape is preserved; only absolute scale is off, by `1/cos(φ)`.

### 6.3 The affine fit

`AffineTransformation.__init__` builds a `2n × 6` design matrix, two rows per control point:

```
X = a*x + b*y + tx      row:  [x, y, 1, 0, 0, 0]
Y = c*x + d*y + ty      row:  [0, 0, 0, x, y, 1]
```

solved with `np.linalg.lstsq`. Parameters are stored as a 3×3 homogeneous matrix; `__call__`
applies it vectorised over coordinate arrays.

Six unknowns, so ≥3 points; extra points are least-squares averaged.

Affine provides translation, non-uniform scale, rotation and shear — the degrees of freedom a
scanned, slightly rotated, slightly stretched paper map needs. The docstring records that it
deliberately replaced a thin-plate spline: TPS interpolates every control point exactly but
extrapolates wildly outside their convex hull, which distorted map corners badly.

Pixel Y grows downward while northing grows upward; nothing flips it explicitly — the fit
simply learns a negative `d`.

`self.rmse = sqrt(residuals[0] / (2n))`, stamped on every output feature as `rmse_meters`.

### 6.4 Direction

The model is **pixel → EPSG:3857 only**. There is no inverse method.

---

## 7. Stage E — coastline snapping

Controlled by `snap_to_coastline` (default `True`), gated in the colors path by
`ENABLE_COASTLINE_SNAPPING = True` in `tasks.py`.

1. `_load_coastline_geometry()` unions every feature of `ne_coastline.geojson` into one
   geometry, LRU-cached on `(path, mtime)` so editing the file invalidates the cache.
2. Reprojected to 3857 with the vectorised `_lonlat_arrays_to_webmercator`.
3. Tolerance derivation:
   - base = `diagonal_px × 0.01`, where `diagonal_px` is the bounding diagonal of **all
     features in pixel space** (`_estimate_pixel_diagonal_from_features`), or `8.0` px if
     unavailable; overridable via `coastline_snap_tolerance_px`;
   - clamped to `[3, 40]` px;
   - `× meters_per_pixel` from `_estimate_affine_meters_per_pixel()` (mean of the two column
     norms of the linear block);
   - clamped again to `[200 m, 50 000 m]`.
4. `_snap_geometry_to_coastline()` walks every polygon ring; any vertex within tolerance of the
   coastline is moved to its `nearest_points` projection on it.
5. If snapping invalidates a polygon, `buffer(0)` repairs it; if that fails the **original**
   polygon is kept unchanged.

Counts of total and snapped points are accumulated but never reported.

---

## 8. Stage F — land clipping, and Stage G — output

### 8.1 Building the land mask

[`coastline_land_mask.py`](../Backend-Atlas/app/utils/coastline_land_mask.py). There is no land
*polygon* file — only coastline **lines** and `ne_ocean_points.geojson`, seed points known to
lie in water. So `build_land_mask_cached()`:

1. unions the coastline linework with the world bbox boundary `box(-180, -89.9, 180, 89.9)`;
2. `shapely.ops.polygonize()` turns every closed face of that planar arrangement into a polygon;
3. any face containing an ocean seed point (tested with `prep()`) is marked ocean;
4. `land_mask = world_bounds.difference(union(ocean_faces))`.

A flood fill by seeding. Cached on all four `(path, mtime)` values.

### 8.2 Clipping

`clip_zone_to_land_mask()`:

- validates/repairs the zone (`buffer(0)`);
- intersects with the land mask, retrying on topology errors with both sides repaired;
- discards non-polygonal leftovers via `extract_polygonal_geometry()` — the frontend only
  renders `Polygon`/`MultiPolygon`;
- **drops the zone entirely** when surviving area / original area `< land_coverage_threshold`
  (default `0.01`). A zone almost entirely at sea is treated as a bad detection.

### 8.3 Output

`_to_lonlat` converts back to WGS84, and each feature gains:

```json
{"is_pixel_space": false, "is_georeferenced": true,
 "crs": "EPSG:4326", "transform_method": "affine", "rmse_meters": 1234.56}
```

FeatureCollections with no surviving features are dropped. `persist_features()` writes one row
per feature via `insert_feature_in_db`, logging and continuing on individual failures.

---

## 9. Known limitations and quirks

Verified against the code, in rough order of impact.

1. **`rmse_meters` is in WebMercator units**, inflated by `1/cos(φ)` — ≈1.8× at 56°N. Reported
   as metres, so a stated 1000 m is ≈550 m on the ground at Quebec latitudes.
2. **With exactly 3 control points the fit is exact**, `lstsq` returns an empty residuals array,
   and `rmse` falls to the `else: 0.0` branch — reporting perfect confidence precisely when
   there is no redundancy to check it against.
3. **The framing box is collected and discarded.** `worldAreaBounds` never reaches `/upload`.
4. **The fitted transform is never persisted.** It is refit on every run and unavailable to
   later feature edits or re-renders.
5. **Snapping is unconditional nearest-point** with no orientation test, so a boundary vertex
   near a graticule line, neatline or unrelated coast is pulled onto it just as readily as onto
   the correct coast.
6. **Zone polygons are vectorised independently per color mask**, so neighbouring zones can
   carry slightly different vertices along a shared edge even though the underlying pixel
   assignment is an exact partition.
7. **`snap_to_coastline` is not passed in the shapes path** (`tasks.py:202`), so it uses the
   default `True`. `ENABLE_COASTLINE_SNAPPING` only actually governs the colors path.
8. **`_to_lonlat` is a per-point Python loop** while its forward counterpart is fully
   vectorised — the hot spot on dense color-extraction polygons.
9. **Snap tolerance keys off feature bounds, not image size**, so a map whose zones cluster in
   one corner gets a much smaller tolerance than the same map with spread-out zones.
10. **Ring closure is forced, not fixed**: if the first vertex snapped and the last did not, the
    last is overwritten with the first rather than snapped consistently.

---

## 10. The dev-test harness

The evaluation path, and the reason the planned work is measurable. Fully described in
[`dev-test-tool.md`](dev-test-tool.md); summarised here for its georeferencing role.

Assets live under `Backend-Atlas/tests/assets/georef/`:

```
maps/<test_id>.jpg                       the source map
georef_zones/<test_id>_zones.geojson     hand-drawn ground truth, EPSG:4326
test_cases/<test_id>/<case_id>/
    config.json          GCPs + pipette picks, so a case re-runs identically
    zones.geojson        extraction output of the latest run
    report.json          IoU metrics of the latest run
    zones_best.geojson   best run so far
    best_report.json     its metrics
```

`config.json` carries `georef.imagePoints`, `georef.worldPoints` and `colors.imposed`, written
by `write_test_config()` and read back by `build_extraction_task_args_for_case()`.

`process_dev_test_extraction` is a parallel task that **skips text and shapes extraction**, runs
color extraction plus georeferencing, writes assets to disk and evaluates. It runs synchronously
through `.apply()` with no broker, which is what lets `tests/test_georef_cases.py` work in CI.

`dev_test_evaluator.py` matches extracted zones to expected zones by normalised name, computes
IoU / precision / recall / false-positive and false-negative areas per zone, and
`evaluate_and_persist_case()` promotes a run to `*_best` when `meanIou` improves. `MIN_IOU = 0.7`
in the test.

Current state: **one test case** (`pip_7sift`, 7 control points, one pipetted zone "Quebec"),
scoring IoU ≈ 0.94.

Run it with:

```
docker compose run --rm test-backend pytest tests/test_georef_cases.py -v
```

or via `scripts/run_georef_tests.py` with `--test-id` / `--case-id` filters.

---

## 11. Reference data

`Backend-Atlas/app/geojson/`:

| File | Used by | Role |
|---|---|---|
| `ne_coastline.geojson` | keypoint finder, snapping, land mask | coastline linework |
| `ne_50m_lakes.geojson` | keypoint finder only | extra inland detail when <10 keypoints |
| `ne_ocean_points.geojson` | land mask | ocean seed points for the flood fill |

All Natural Earth. There is no rivers/watercourse layer.

---

## 12. Dependencies relevant to georeferencing

Present: `numpy`, `shapely==2.1.2`, `scipy==1.16.3`, `scikit-image==0.26.0`,
`opencv-python-headless`, `geonamescache`.

Absent: `pyproj`, `rasterio`, `gdal`. All projection maths is hand-rolled in
`georeferencingSift.py`.
