# Dev test tool — georeferencing & extraction

An internal tool to measure how well the extraction + georeferencing pipeline reproduces
zones we drew by hand. You draw the *expected* zones once on a map, then create as many
*test cases* as you want on that same map (different SIFT anchor points, different pipette
picks), and each one gets scored against your drawing.

This guide covers **how to use it**, not how it works internally.

---

## 1. Prerequisites

- The stack is running: `docker compose up`
- You are logged in (all dev-test pages require auth)

---

## 2. Flow of use

### Step 1 — Open the test browser

**Profil** → **Voir tests** (route `/tests`).

You get the list of existing tests. A "test" = one map image + the expected zones you drew
on it.

### Step 2 — Create a test

Click **Créer un test**, upload your map image, give it a name
(ex: *Zones de la carte du Québec 1791*), then **Créer le test**.

You land in the **Test editor** for that map.

### Step 3 — Draw the expected zones

This is your ground truth. In the right-hand **Créer une nouvelle zone** panel:

1. **Activer le mode création**
2. Type the **zone name** — see [naming rules](#3-naming-rules-the-important-part) below
3. Draw one or more strokes on the map with the mouse. Stroke endpoints snap to each other
   when they are close, so you can build a contour in several passes.
4. Optional helpers:
   - **Mode frontière (côtes)** — click two points along a coastline and the tool follows
     the real coastline between them instead of your freehand line
   - **Frontières géopolitiques** — same thing, but following administrative borders
   - **Annuler le dernier trait** — undo the last stroke
   - **Ajouter une sous-zone** — for a zone made of several separate polygons (islands,
     disconnected pieces): close a contour, click this, then draw the next piece
5. When the contour comes back near its starting point it closes, and
   **Enregistrer la zone** becomes available.

Repeat for every zone you want to test. Draw only the zones you actually intend to extract.

Zones are saved as you go and reloaded every time you open the editor — you never redraw them.
The left panel lets you toggle visibility, rename, or delete a zone.

### Step 4 — Create a test case

Click **Ajouter un test case** (top right). You get asked for a test case name
(ex: *5 sift points*), then the import flow runs:

1. **World area** — select the region of the world your map covers
2. **Georeferencing (SIFT)** — place matching point pairs between your map image and the
   real-world map. More/better spread points = better transformation.
3. **Pipette (color picker)** — click each colored area of the map you want extracted.
   For every pick, **type the name of the corresponding expected zone**.
   Zoom in for small areas; the sampled radius adapts to the zoom.
4. **Confirmer les couleurs** starts the extraction.

When it finishes you are redirected to the test case result page.

> The legend step is skipped in dev-test mode on purpose: the pipette is the only color
> source here.

---

## 3. Naming rules (the important part)

**Zones are matched by name, and only by name.**

The name you type in the pipette must be the name of the expected zone you drew.
`Quebec` matches `Quebec`. Comparison ignores case and extra spaces, so `quebec` is fine.

If a name doesn't match:

- that expected zone scores **IoU 0** — it is not silently paired with whatever overlapped it
- the result page shows a warning listing the unmatched expected zones and the extracted
  colors that matched nothing

So a bad score is either a real pipeline problem or a typo, and the warning tells you which.
Use short, meaningful names (`Quebec`, `Ontario`), not color names.

If you pick two colors with the same name, extraction suffixes the second one (`Quebec_2`);
it still matches the expected `Quebec`.

---

## 4. Reading the report

The test case result page shows the map with three layers — your expected zones, the
extracted zones, and the **error overlay in red** — plus the metrics.

- **IoU** — overlap between an expected zone and its matched extracted zone. `1.0` = perfect,
  `0` = no match at all. This is the headline number.
- **Precision** — how much of the extracted zone is actually inside the expected one
  (low = the extraction spilled outside).
- **Recall** — how much of the expected zone was covered (low = the extraction missed parts).
- **FN area** (false negative, red) — expected surface that was **not** extracted.
- **FP area** (false positive, red) — extracted surface that should **not** be there.
- **Mean …** — the same metrics averaged over all your expected zones.
- **PASS / FAIL** — shown when a minimum IoU threshold was applied.

**Current / Best toggle** — *Current* is the latest run, *Best* is the best-scoring run ever
recorded for this test case. The best one is kept automatically whenever a run beats it, so a
regression never overwrites your reference result.

---

## 5. Managing tests and test cases

- **Delete a test case** — the ✕ next to its name in the **Test cases** panel of the test
  editor. Removes that case's config and results only; your drawn zones are untouched.
- **Delete a whole test** — the delete button on its card in **Voir tests**. This removes the
  map image, **the expected zones you drew**, and all its test cases. Not recoverable from the
  UI.

---

## 6. Where things are stored

Everything lives on disk under `Backend-Atlas/tests/assets/georef/`, not in the database:

```
maps/<test_id>.jpg                      the map image
georef_zones/<test_id>_zones.geojson    the expected zones you drew   ← the valuable part
tests_metadata.json                     test names / creation dates
test_cases/<test_id>/<case_id>/
    config.json          SIFT point pairs + pipette picks (position, name, radius)
    zones.geojson        zones extracted by the last run
    report.json          metrics of the last run
    errors.geojson       FP/FN overlay of the last run
    zones_best.geojson   \
    best_report.json      >  same three, for the best run so far
    errors_best.geojson  /
```

Because it's plain files in the repo, results are versioned in git — you can diff a report
between branches, and a deleted test case can be restored with `git checkout` if it had been
committed.

`config.json` is what makes a test case reproducible: **both the SIFT anchor points and the
pipette picks are saved there**, so a case can be replayed without you clicking anything again.

---

## 7. Automatic reruns

The `test-backend` service runs the backend test suite, which includes the dev-test cases
(`tests/test_georef_cases.py`). For every test case found on disk it:

1. re-runs the **current** extraction pipeline from that case's `config.json`
   (saved SIFT points + saved pipette picks)
2. rewrites `zones.geojson`, `report.json` and `errors.geojson`
3. asserts the score is at least `MIN_IOU` (currently **0.7**)

So the cases you save become a regression suite: change something in extraction or
georeferencing, run the tests, and every saved case is re-scored against your drawings.
Reports on disk always reflect the current algorithm, never a stale run.

A consequence worth knowing: a test case that scores below the threshold **fails the backend
test suite**. If a case is a known-bad experiment, delete it rather than leaving it red.

---

## 8. Tips & gotchas

- **Draw first, test after.** Expected zones are per-map, shared by all test cases of that map.
  Test cases are cheap and disposable; the drawing is the expensive part.
- **Iterate with test cases.** To compare 5 vs 10 SIFT points, make two cases on the same map
  and compare their mean IoU.
- **Name the case usefully** — `5-sift-points`, `10-points-coastline` beats `test2`.
- **Zoom in the pipette** for small or thin areas; the sample radius follows the zoom.
- A case created before the pipette existed has no colors in its `config.json` and can't be
  replayed — recreate it.
