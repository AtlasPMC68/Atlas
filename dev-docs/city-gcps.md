# City control points

Plan Step 5 ([`georeferencing-plan.md`](georeferencing-plan.md) §9), as built. Written
2026-09-22 on `georef-exp`. It covers what was implemented, why it is shaped the way it
is, and what is left.

---

## 1. What it does

A new, optional import step between SIFT matching and the legend/pipette. The user types
the name of a city their map shows. We offer the gazetteer cities inside the framing box
whose name matches, and the user picks one; it appears, labelled, on the reference map.
The user then clicks where their own map draws it. Each placed city becomes a control point
exactly like a SIFT one, tagged `source: "city"`.

```
World area -> SIFT (>= 4 pairs) -> Villes (0..n, optional) -> Legend -> Colours -> Extraction
```

SIFT keeps its minimum of 4 pairs. Cities have no minimum, since a map may show none.

---

## 2. What changed

| Layer | Change |
|---|---|
| Point model | `ControlPoint{pixel, geo, source, city}`, a discriminated union: `source` is `sift` or `city`, and `city: CityRef{geonameid, name}` is required for a city and forbidden otherwise. `manual` is gone, since nothing produced it. `sigma_px` left the record. |
| Wire format | One `control_points` list everywhere, in `ControlPoint.to_dict()` shape: the upload form field of both routes, the Celery task argument of both tasks, dev-test `config.json` (`georef.controlPoints`) and `maps.georef_inputs` (version 2). `image_points` / `world_points` / `imagePoints` / `worldPoints` and `ControlPoint.from_pairs` are deleted, not kept alongside. |
| Gazetteer | `app/utils/city_gazetteer.py` + `POST /projects/city-candidates {q, west, south, east, north}`. |
| Config (v8) | `gcp_sources` (which sources a run fits from, default both), `gcp_sigma_px_sift` and `gcp_sigma_px_city` (both 6). |
| Piecewise | Every control point pins the local correction. The source-based local mask and `n_local_points` are gone. |
| Requirements (v3) | `controlPoints` = at least 3 points among the *selected* sources. New optional `cityControlPoints`. |
| Run record | `inputs.controlPointsBySource`, `errors.gcpRmseKmBySource`, `errors.gcpPredictedLonLat`. |
| Frontend | `GeoRefCitiesModal.vue`, `useCityCandidates.ts`. `GeoRefSiftWorldMap` is generalised into `GeoRefWorldMap` (labelled points, greyed context points), which both modals use. `ImportView` has an 8-step bar. |
| Dev-test tool | Source checkboxes on exploration cases, a control-point overlay with per-source error on the result page, `--sources` in `run_georef_alignment.py`. See [`dev-test-tool.md`](dev-test-tool.md). |
| Debug dump | Cities get a magenta circle and their name in `09_control_points.png`; `summary.txt` names the city instead of printing sigma. |

The five existing case configs were converted once, by a throwaway script (their points
became `source: "sift"`), and nothing reads the old format any more.

---

## 3. Key choices

**The source is on every point, and cities carry their identity.** The pipeline needs the
source to weight points, to report error per source, and to run SIFT-only or cities-only
from the same clicks. The GeoNames id tells two spellings of one city ("Quebec", "Kebek")
apart from two different cities, which is why the modal refuses a duplicate. The name makes
records and overlays readable. Making the union strict means no consumer ever handles a city
without a name.

**σ is configuration, not data.** It moved from the stored point into `GeorefConfig` and is
looked up by source when fitting. A stored σ would freeze a guess into every click on disk.
In config it can be swept from the tuning panel.

**SIFT and cities are weighted equally.** A SIFT point is a user matching an abstract
coastline shape, and that identification can be poor. A city is a named dot, but the map may
draw it in the wrong place. Which source is noisier is for residuals to say, so the record
now reports RMS error per source (`gcpRmseKmBySource`). The baseline affine is still
unweighted. The alignment GCP term weights by `(median σ / σ)²`, which is exactly 1 while
the two σ are equal.

**Cities pin the piecewise correction.** This follows from trusting them equally. It used
to be SIFT-only, when cities were assumed to be sloppy.

**The source filter is applied once, where the task reads the points.** When a source is
unticked, it takes no part in the alignment, the gates, the baseline, the piecewise
correction or the reported error. It is not merely dropped from the final fit. It travels in
`config_overrides`, so the Celery signature is unchanged by it, and like any non-default
setting it is never promoted to `best`. The re-run endpoint checks requirements under the
run's own sources before dispatching, so "cities only" on a case with two cities is a 400
naming the reason, not a failure in the worker log.

**The gazetteer is a SQLite file queried by the frame.** geonamescache loads its whole JSON
for the world into every process that imports it. Instead, the pinned geonamescache
`cities15000` (about 32k places of 15k+ inhabitants) is built once into
`app/.cache/cities15000-gnc<version>-b<builder>.sqlite`, which is gitignored and bind-mounted
into every backend container. It is keyed on the library version, so an upgrade rebuilds it.
Each search reads only the frame's rows: about 150 cities and 870 names for a Quebec-sized
box, in about 2 ms. The file is about 8.5 MB, because alternate names are kept in Latin
script only (about 13 MB with every script). Alternate names are what make historical and
foreign spellings match.

**Matching.** Names are normalised for accents, case and punctuation, so "trois rivieres"
finds Trois-Rivières. Matches are ranked exact, then prefix (3+ characters), then near miss
(`difflib` ratio ≥ 0.8), then by population.

**Only cities inside the frame, and no fallback.** A city outside the world area the user
framed is not on their map. A name the gazetteer does not know (Stadacona, say) returns an
empty list and is simply not used.

**The dev tool shows the residual on the map.** Each point is drawn at its true position
with a line to where the fitted transform put the clicked pixel. That is where "old maps
place cities wrongly" becomes visible, and where a mis-clicked or mis-picked point stands
out.

---

## 4. Verification

- **Output unchanged for existing cases.** Every case was georeferenced before and after,
  with `affine` and `piecewise_affine` and snapping on and off (5 × 2 × 2 = 20 runs). All 20
  are byte-identical in matrix, geometry and reported RMSE.
- **257 unit tests pass** (georeferencing, requirements, and the new `test_city_gazetteer.py`,
  which builds the real gazetteer into a temp dir). The new tests cover union enforcement,
  the wire format, source selection, per-source error (`None`, not 0 km, on an exact 3-point
  fit), cities pinning the piecewise correction, and the re-run pre-check.
- **Routes** exercised through FastAPI's TestClient: `city-candidates` results
  ("kebek" → Québec, Stadacona → none, Toronto outside the frame → none) and the dev-test
  upload with a mixed list.
- **The Celery task** was run through `.apply()` on a throwaway case (6 SIFT + 3 cities,
  since deleted) under each source selection. Its city clicks were synthetic, so this checks
  the plumbing, not accuracy.
- `vue-tsc` reports nothing in the touched files. The 8 remaining errors are in files this
  work did not touch.
- **Not verified:** the new modal has not been clicked through in a browser.

**Pre-existing, not caused by this:** `pip_7sift`, the only regression case, has no
framing box. It has been blocked since requirements v2, so `test_georef_cases.py` fails on it.

---

## 5. What is left

1. **A real case with cities.** Nothing has measured cities yet: every number above is
   plumbing. Recreate a case on the `pip_7sift` map (zones are already drawn) with its SIFT
   points plus the cities you can read. That fixes the missing framing box too, and gives
   SIFT only / cities only / both from the same clicks. Do the same on the Leclerc map as an
   exploration case.
2. **Set σ from data, and fix the normalisation first.** Once per-source residuals exist
   across a few cases, the two σ can differ. Before that, the alignment GCP term has to be
   normalised by the sum of the weights rather than by count and median σ. Otherwise its
   total pull against the coastline shifts with the mix of sources (see the comment in
   `config.py`).
3. **GCPs versus the Tukey cutoff.** The GCP residuals share the curve term's robust loss.
   By arithmetic, not yet measured, a GCP stops pulling beyond about 3 px in the fine
   alignment stage. If that holds, neither SIFT points nor cities constrain fine alignment.
   It is worth a per-stage "GCPs inside cutoff" count in the run record.
4. **Gates weigh every point alike.** `probe_gcp_disagreement` averages over all points.
   Noisy points make it more lenient, not stricter. Its detail could break the value down by
   source.
5. **Gazetteer reach.** `cities15000` has the big, stable cities, which was the requirement.
   It has no small historical places (Tadoussac, forts) and no historical names (Stadacona,
   Ville-Marie). The full GeoNames dump has historical and abandoned populated places
   (`PPLH`/`PPLQ`) if that is ever wanted, and the SQLite layout scales to it.
6. **Suggestions from OCR.** City detection already reads place names off the map. They
   could pre-fill the city step instead of the user typing them.
7. **`cities_validation.py` still loads geonamescache whole**, for OCR city detection. It
   could read the same SQLite file. It is a separate feature, so it was left alone.
8. **Going back from the city step to SIFT restarts SIFT matching.** This is the existing
   behaviour of every modal in the flow. Cities are kept when coming back to their step.
9. **Operational.** The Celery task signature changed (`control_points` replaced
   `pixel_points` / `geo_points_lonlat`), so restart `celery-worker` along with the backend.
   The first city search builds the gazetteer file.
