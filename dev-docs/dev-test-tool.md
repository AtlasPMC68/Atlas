# Dev test tool — georeferencing & extraction

An internal tool for two jobs that look similar and are not.

**Regression tests** measure how well the extraction + georeferencing pipeline reproduces
zones we drew by hand. You draw the *expected* zones once on a map, then create as many
*test cases* as you want on that same map (different SIFT anchor points, different pipette
picks), and each one gets scored against your drawing. These gate the backend test suite.

**Exploration tests** (`probe`) have no expected zones at all. They exist to persist the
clicks — control points, framing box, pipette picks — so a map can be re-extracted in
seconds and you can *look* at where the zones landed. Drawing ground truth is roughly an
hour of clicking per map; replaying a map you have not drawn is the loop you actually
spend the day in while changing georeferencing. Probes never fail CI, because there is
nothing for them to be wrong about.

Which one a test is, is **declared** when you create it, never inferred from a missing
zones file. Inferring it would mean a regression test whose drawing goes missing silently
demotes itself to a probe and coverage disappears with nothing going red.

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
(ex: *Zones de la carte du Québec 1791*), pick the **type**, then **Créer le test**.

| Type | What it does | When |
|---|---|---|
| **Régression** | Scored against expected zones you draw; part of the backend suite | You are pinning behaviour and willing to draw ground truth |
| **Exploration** | Replay-only: persists the clicks, never scored, never in CI | You want to see what the pipeline does on this map, now |

You land in the **Test editor** for that map.

For an **exploration** test, skip step 3 entirely and go straight to step 4.

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

**Or load a real border instead of drawing.** For a map of countries, states or provinces,
the ground truth already exists. In create mode, open **Charger une frontière (pays,
région)**:

1. Pick the country (type to filter). **Charger le pays entier** loads its outline.
2. Or tick regions and **Charger N régions**: several regions are merged into one zone (the
   Maritimes, say). Where the file groups its units, ticking the group selects them all:
   Natural Earth's admin-1 is 110 provinces for Italy and 101 départements for France, and
   the groups are the 20 Italian regions and 18 French ones.
3. The zone appears in blue and its name is pre-filled (French where the file has it). Edit
   the name if your pipette will use another one: zones are matched by name.
4. **If the map only shows part of it, cut the rest off**: **Découper une partie**, then
   click a polygon around what to remove and close it on its first point (Escape cancels).
   Cut as many times as needed; ↶ undoes the last cut. Only the loaded zone can be cut,
   never the zones already saved.
5. **Enregistrer la zone**. **Ajouter une sous-zone** works here too: a loaded border becomes
   one part, and the next can be loaded or traced.

The border files live in `Backend-Atlas/app/geojson/borders/` (gitignored, ~54 MB).
`python scripts/fetch_natural_earth_borders.py` downloads Natural Earth's countries and
states/provinces at 10m; any other admin-0 or admin-1 file dropped there (Natural Earth or
geoBoundaries) is recognised from its properties and listed too. Zones arrive simplified to
~500 m, below Natural Earth's own accuracy at that scale. Lakes are not pre-cut: the cleaned
version of each expected zone cuts them with the pipeline's own lake layer
([§4](#4-reading-the-report)).

Repeat for every zone you want to test. Draw only the zones you actually intend to extract.

Zones are saved as you go and reloaded every time you open the editor — you never redraw them.
The left panel lets you toggle visibility, rename, or delete a zone.

### Step 4 — Create a test case

Click **Ajouter un test case** (top right). Confirm the map, and the **Saisie utilisateur**
checklist opens next to it. Opening that page also starts OCR for the map in the background
when its text regions are not cached yet, so the first case's run does not wait for it.
Steps can be done in any order, and redone with **Modifier**:

1. **Zone sur le monde** — select the region of the world your map covers. The control
   points unlock once it is set; redrawing it resets them (you are warned first).
2. **Délimiter la légende** — draw a rectangle around the legend, or choose **Pas de
   légende sur la carte**. The rectangle is ignored by colour extraction and by the
   alignment evidence, so it changes the zones — which is why a case stores the answer.
3. **Points SIFT automatiques** — place matching point pairs between your map image and
   the real-world map. More/better spread points = better transformation.
4. **Villes (optional)** — type the name of a city your map shows, pick it from the
   candidates (only cities inside the world area are offered), then click where your map
   draws it. Add as many as you can read. A case with both SIFT points and cities can
   later be re-run with either alone (see [Re-running from the UI](#re-running-from-the-ui)).
5. **Villes de vérification (optional, "Évaluation (test)")** — cities placed exactly like
   the ones above, but **never used to fit anything**: after every run, the transform that
   placed the zones is measured on them, in km. That is the only placement error not
   measured on the points the model was fitted to, and the primary metric of the test plan
   ([`georeferencing-testing.md`](georeferencing-testing.md)). Place at least 5, spread over
   the map; a city already used as a control point is refused, and vice versa. **SIFT pairs
   can be check points too**: at the SIFT step, tick *vérification* under a matched pair. The
   minimum pair count only counts the pairs left for the fit.
6. **Couleurs à extraire (pipette)** — click each colored area of the map you want
   extracted. For every pick, **type the name of the corresponding expected zone**.
   Zoom in for small areas; the sampled radius adapts to the zoom.

**Commencer l'extraction** asks for the test case name (ex: *5 sift points*) and starts
the run. When it finishes you are redirected to the test case result page.

#### Starting from an existing case

When the map already has cases, the import page also shows **Partir d'un test case
existant**. Pick a source case and tick what to take from it: zone sur le monde, légende,
points SIFT, villes, points de vérification, couleurs des zones, pipette eau. Every part the
source has is ticked by default. The map's stored image comes with them, and the checklist
opens with those steps done. Each step is still editable: click a SIFT pair to retake it
(confirm without re-placing it to drop it), remove cities, remove or re-pick colours. Saving
asks for a new name; the source case is not touched.

A stored SIFT pair whose keypoint the frame no longer offers is still shown in the SIFT
step, as an extra point on the world map. This happens when the points were clicked before
the case had its frame (`pip_7sift`), or before the keypoint finder changed. It is kept and
can be retaken like any other. The same applies when editing a case's own inputs.

Points travel only with the zone sur le monde, because they were matched inside it. Use
this so that two cases of one map differ only in what the case is about. Above all, use it
to keep the same check points across a map's cases, or their check-point errors cannot be
compared. The case roles worth creating are listed in
[`georeferencing-testing.md` §2](georeferencing-testing.md#2-the-plan).

The text and shapes options of the production import are not offered here: dev-test runs
extract colours only.

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
extracted zones, and the **error overlay in red** — plus the metrics. The error overlay is
not stored: the API computes it from the run's zones and the expected zones when the page
asks (`GET /dev-test-api/test-cases/{test}/{case}/errors?run=latest|best&stage=cleaned|raw`).

On an **exploration** case there is no report, so the page shows every extracted zone
as-is (rather than only the ones a report matched) together with the case's kind and any
requirement gaps. That is the deliverable: you read it with your eyes.

- **IoU** — overlap between an expected zone and its matched extracted zone. `1.0` = perfect,
  `0` = no match at all. This is the headline number.
- **Precision** — how much of the extracted zone is actually inside the expected one
  (low = the extraction spilled outside).
- **Recall** — how much of the expected zone was covered (low = the extraction missed parts).
- **FN area** (false negative, red) — expected surface that was **not** extracted.
- **FP area** (false positive, red) — extracted surface that should **not** be there.
- **Distance des contours** (mean, p90, max) — how far, in km, the extracted zone's
  outline sits from the expected one, measured both ways. IoU is an area ratio and barely
  moves on a large zone; this is in the unit placement error is in. When the two directions
  disagree a lot (`extractedToExpectedMeanKm` far above `expectedToExtractedMeanKm`), the
  extracted zone has pieces far from where it should be, usually another region painted in
  the same colour, not a placement error ([testing §4](georeferencing-testing.md#4-boundary-distance)). **Outlines only**: holes
  (lakes cut out of zones, text) are counted in the report but not measured, since they are
  not misplaced borders and IoU already charges them as area.
- **Mean …** — the same metrics averaged over all your expected zones.

The **Points de contrôle (dernier run)** panel also shows the **check-point** error
(*Vérification*): RMS, median and max in km on the held-out cities, next to what the
control-point affine alone scores on them. Check points are drawn on the map in teal, with a
dashed line to where the transform placed them.
- **PASS / FAIL** — shown when a minimum IoU threshold was applied.

**Current / Best toggle** — *Current* is the latest run, *Best* is the best-scoring run ever
recorded for this test case. The best one is kept automatically whenever a run beats it, so a
regression never overwrites your reference result. When a lower score is the intended result,
replace it by hand ([§5](#5-managing-tests-and-test-cases)).

**Après nettoyage / Avant nettoyage** — every run is scored twice, and this toggle switches
the map and the report between the two:

- **Après nettoyage** (default): the zones the app ships, after coastline snapping, the ocean
  clip and the lake cut, against the expected zones put through the **same ocean and lake
  cuts**. This is the regression score: PASS/FAIL, `scoreUsed`, best.
- **Avant nettoyage**: the zones straight out of the transform, against the expected zones
  **as drawn**. This is the one to judge georeferencing on, since cleaning corrects transform
  error after the fact and so hides it.

The test editor always shows and edits the zones as drawn; their cleaned version is derived
from them when they are saved.

---

## 5. Managing tests and test cases

- **Delete a test case** — the ✕ next to its name in the **Test cases** panel of the test
  editor. Removes that case's config and results only; your drawn zones are untouched.
- **Delete a whole test** — the delete button on its card in **Voir tests**. This removes the
  map image, **the expected zones you drew**, all its test cases and its cached OCR. Not
  recoverable from the UI.
- **Change a test's kind** — edit `kind` on its entry in `tests_metadata.json`
  (`"regression"` or `"probe"`). A single case can override its map with a `kind` field in
  its own `config.json`, which is how a deliberate known-bad experiment lives on a map that
  otherwise carries real regressions, instead of being deleted to keep the suite green.
- **Replace a case's best on purpose** — a run only becomes `best` by beating it, so after a
  change that is meant to lower a score (a fix that removes a lucky error, a redrawn expected
  zone) the old best would stay the reference forever. Run the case, check the result, then:

  ```
  docker compose run --rm georef-dev python scripts/force_promote_georef_best.py --case-id pip_7sift
  ```

  It makes the last run the best whatever the two scores, and prints both. Add `--test-id`
  when several maps have a case of that name. A last run made with switches or excluded
  control points is refused, as it is for automatic promotion.

---

## 6. Where things are stored

Everything lives on disk under `Backend-Atlas/tests/assets/georef/`, not in the database:

```
maps/<test_id>.jpg                      the map image
georef_zones/<test_id>_zones.geojson    the expected zones you drew   ← the valuable part
georef_zones/<test_id>_zones_cleaned.geojson
                                        the same through the ocean and lake cuts: what the
                                        shipped zones are scored against. Derived: written
                                        on save, recomputed when stale (it carries a hash of
                                        the drawn file and the cleaning version)
tests_metadata.json                     test names / creation dates / kind
derived/<test_id>/
    text_regions.json    OCR label boxes for this map, with provenance
test_cases/<test_id>/<case_id>/
    config.json          control points (SIFT and city, each with its source), check
                         points (held out of every fit, same shape), framing box,
                         pipette picks (position, name, radius, zone-or-water),
                         optional kind
    best_report.json     metrics of the best run so far: the regression baseline
    zones_best.geojson, zones_raw_best.geojson
                         the zones of that best run, after and before cleaning

  The last run's files below are gitignored (see "What is committed"):
    case_state.json      which requirements this case satisfies, and its kind
    zones.geojson        zones extracted by the last run, as shipped (after cleaning)
    zones_raw.geojson    the same zones before snapping and the clip
    zones_pixel.geojson, classified_image.png
                         the zones in image pixels, for the result page's overlays
    report.json          metrics of the last run  (regression cases only)
    run_record.json      structured record of the last georeferencing run
    reference_debug/     PNG per reference layer (only with --reference)
    evidence_debug/      edge map and water overlays (only with --evidence)
    alignment_debug/     why the map placed where it did
```

### What is committed

Everything needed to run a case and everything it is compared against: the map image, the
expected zones (drawn and cleaned), `tests_metadata.json`, the OCR boxes in `derived/`, and
per case its `config.json` and its best run (`best_report.json`, `*_best.geojson`). A deleted
test case can be restored with `git checkout`.

A case's last run is not committed: it is rewritten by every run and reproduced by running
the case, so a fresh checkout shows each case's best run and no last run until you run it.
`case_state.json` is computed on demand when it is missing. Variant runs (`ablations/`) are
not committed either.

`config.json` is what makes a test case reproducible: **the control points, the framing
box and the pipette picks are all saved there**, so a case can be replayed without you
clicking anything again. Control points are one list under `georef.controlPoints`, each
`{source, pixel: {x, y}, geo: {lon, lat}}`, and a city point also carries
`city: {id, name}` (its GeoNames id). See [`georeferencing.md` §3](georeferencing.md#3-inputs).

`run_record.json` sits next to `report.json` and holds what the georeferencing run knew and
decided: the control points with their source (and any excluded by hand), the models under
`models` -- `gcp_affine` (the control-point baseline, always), `aligned_affine` (when
alignment used the coastline) and `applied` (what the zones were placed with) -- every gate
check (logged whether or not it passed), the errors and the per-phase timings.
`errors.gcpRmseKind` says which error is reported: `in_sample` for an affine,
`leave_one_out` for piecewise on the control-point affine, `leave_one_out_fixed_base` for
piecewise on the aligned affine (optimistic: that affine was fitted with every point). An IoU number alone
cannot tell you which stage moved it; this can. See
[`georeferencing.md` §7](georeferencing.md#7-what-a-run-leaves-behind).

`case_state.json` sits next to it and answers a different question: *is this case still
enough for the algorithm as it stands today?* See [§8](#8-keeping-cases-current).

`derived/<test_id>/text_regions.json` is the OCR output for that map, shared by every case
on it. It is committed deliberately: ~20 KB, deterministic given the image, and it saves
every clone of the repo 135 s per map. It records the SHA-256 of the image it came from and
is recomputed automatically when that stops matching — a cache serving regions from a
different map would hand back a silently wrong number, which is worse than no cache at all.

---

## 7. Automatic reruns

The `test-backend` service runs the backend test suite, which includes the dev-test cases
(`tests/test_georef_cases.py`). For every **regression** test case found on disk it:

1. checks the case still satisfies the current algorithm's requirements ([§8](#8-keeping-cases-current))
2. re-runs the **current** extraction pipeline from that case's `config.json`
   (saved SIFT points + saved pipette picks)
3. rewrites `zones.geojson`, `zones_raw.geojson`, `report.json`, `run_record.json` and
   `case_state.json`
4. asserts the score is at least `MIN_IOU` (currently **0.6**)

So the cases you save become a regression suite: change something in extraction or
georeferencing, run the tests, and every saved case is re-scored against your drawings.
Reports on disk always reflect the current algorithm, never a stale run.

**Exploration cases are skipped**, by design — they have nothing to be scored against, so
you can leave as many of them lying around as you like without touching CI.

Three consequences worth knowing:

- A regression case that scores below the threshold **fails the backend test suite**. If a
  case is a known-bad experiment, mark it as exploration or delete it rather than leaving it
  red.
- A regression case with **no expected zones fails** rather than skipping. That used to be a
  silent skip, which meant a lost ground-truth file cost you coverage with nothing going red.
  If a map is only for replaying, say so: mark it exploration.
- A case missing a required *user* input **fails with the reason and the fix**, rather than
  running with less evidence than the algorithm expects and reporting a worse number for a
  reason unrelated to whatever you were measuring.

---

## 8. Keeping cases current

The georeferencing pipeline changes shape, not just constants. Step 1 added a framing box,
Step 1/3 added a separate water pipette, Step 4 made an OCR text mask load-bearing. A case
authored before any of those carries inputs that were sufficient then and are not now.

`app/utils/georeferencing/requirements.py` is the single declaration of what the current
algorithm needs. Every run resolves it against the case and prints the result, so a case
that has fallen behind says so instead of quietly scoring worse:

```
regression case, requirements v6, scored
  ok        controlPoints      9 point(s) from sift, city (sift=6, city=3)
  ok        cityControlPoints  Cities the user named and located on the map.
  absent    checkPoints        0 point(s)
  ok        frameBounds        The world area the user framed; the extent for every reference layer.
  ok        zonePicks          Pipette picks of kind 'zone'; without them nothing is extracted.
  ok        legend             The legend rectangle, or an explicit 'no legend'. ...
  REFRESH   textRegions        not cached; text_extraction will be re-run once
  absent    waterPicks         Pipette picks of kind 'water'. They identify the map's coastline: ...
```

`controlPoints` counts only the sources the run uses (at least 3), so the same case can be
runnable with SIFT alone and blocked with cities alone. `cityControlPoints` is optional: a
map may show no city the gazetteer knows.

**The distinction that matters is whether a missing input can be recovered.**

| Kind | Example | Missing means |
|---|---|---|
| **User input** | control points, framing box, pipette picks, legend | A human clicked it. Nothing can re-derive it — a human supplies it, with **Compléter les entrées** ([below](#completing-a-case)). |
| **Derived** | OCR text regions | Extracted from the map by a step that is *not* georeferencing and does not change while georeferencing is tuned. Recomputed once, persisted, reused forever. An expense, never a blocker. |

So the statuses you will see:

| Status | Meaning | What happens |
|---|---|---|
| `ok` | present | nothing |
| `REFRESH` / `STALE` | derived artifact missing or produced from a different image | recomputed once (~135 s for OCR), then cached under `derived/` |
| `BLOCKED` | a required user input is missing | the run stops and prints how to fix it: complete the case |
| `absent` | a genuinely optional user input is missing | runs; a capability is simply not exercised (no water picks ⇒ no alignment, the map is placed by its control points) |

**There is deliberately no middle level**, and no exception for exploration cases. An input
the pipeline reads is either required or genuinely optional — there is no "runs, but through
a fallback that makes it weaker". That is how a case ends up running under-specified and
reporting a worse number for a reason unrelated to whatever you were measuring. The framing
box, the legend answer and the OCR text regions (when alignment is on) are required; the code
has no fallback for any of them.

Requirements depend on the config, not just on the code: `textRegions` is required **only
when curve alignment is on**. Alignment is on everywhere, so every case needs them; the
regression maps' text regions are committed under `derived/`, so the suite does not pay for
OCR.

`REQUIREMENTS_VERSION` bumps whenever a requirement is added, removed, or changes level, so
a `case_state.json` written under an older version is re-checked rather than trusted. It is
at **v6**: v1 had `frameBounds` as degraded, v2 promotes it to required, v3 counts control
points per selected source and adds `cityControlPoints`, v4 adds `legend`, v5 adds the
optional `checkPoints`, v6 stops exploration cases from replaying without a legend answer.
The exploration cases recorded before v4 have none and need completing before they re-run.

### Completing a case

A case never needs recreating. On its result page, the "Cas de test" panel always has a
button that reopens the **Saisie utilisateur** steps with everything the case already has --
control points, pipette picks, framing box, legend -- so only the step you want needs doing:

- **Compléter les entrées (…)** when a required input is missing; it names them.
- **Modifier les entrées** otherwise, to add an optional input the case never got (the
  panel lists them: `waterPicks`, `cityControlPoints`) or to change one.

**Commencer l'extraction** then saves the case under its own name, overwriting its
`config.json`, and re-runs it. If the inputs changed, the case's `best` run is deleted
(`best_report.json`, `zones_best.geojson`, `zones_raw_best.geojson`): it was scored on other
clicks and would otherwise outrank every run on the new ones. Re-saving identical inputs
keeps it.

Framing a case for the first time **keeps its control points**. Only *changing* an existing
box resets them, because SIFT keypoints and city candidates come from the box; no point was
matched under a box that did not exist. If a kept point falls outside the new box, the page
says so: the box is the extent of every reference layer, so widen it to include them.

---

## 9. Tips & gotchas

- **Draw first, test after.** Expected zones are per-map, shared by all test cases of that map.
  Test cases are cheap and disposable; the drawing is the expensive part.
- **Iterate with test cases.** To compare 5 vs 10 SIFT points, make two cases on the same map
  and compare their mean IoU.
- **Name the case usefully** — `5-sift-points`, `10-points-coastline` beats `test2`.
- **Zoom in the pipette** for small or thin areas; the sample radius follows the zoom.
- **Use exploration tests for the maps you are actually iterating on.** Drawing ground truth
  is the expensive part and it is not needed to see where a transform put the zones. Draw it
  when you want to *pin* a behaviour, not to look at one.
- A case created before the pipette existed has no colors in its `config.json` and can't be
  replayed — the run now says so and names the fix rather than failing obscurely. Complete it
  ([§8](#completing-a-case)): pick the colours and keep the rest.
- Older cases have no `kind` on their pipette picks: those are zones, which is the right
  default and needs no action.
- Older cases also have no `frameBounds`, and that **does** block them. Complete them
  ([§8](#completing-a-case)): draw the world area and keep the control points and picks.

---

## 10. The fast loop

The pytest path boots a container and collects every test. When you are iterating on
georeferencing itself, use the direct entry point instead — no broker, no database, no pytest
collection, and colour extraction cached between runs. It runs the same steps as the dev-test
task (`app/utils/extraction_steps.py`, `text_regions_for_run`), so under the same settings it
writes byte-identical zones to a re-run from the UI:

```
docker compose run --rm georef-dev
docker compose run --rm georef-dev python scripts/run_georef_alignment.py --case-id pip_7sift
```

It prints the case's kind, its requirement state ([§8](#8-keeping-cases-current)), the
control-point RMSE in kilometres, the check-point error when the case has check points,
the IoU and the per-phase timings, and writes the same files the task would
(`zones.geojson`, `zones_raw.geojson`, `report.json`, `run_record.json`, `case_state.json`,
and the error overlays). Pass
`--no-write` to leave the case untouched, or `--no-cache` when colour extraction itself is
what changed.

Exploration cases are run like any other; they just print zone counts instead of an IoU.
Use `--kind probe` or `--kind regression` to run only one sort — `--kind probe` is the
"replay the maps I am actually working on" loop, and it does not touch the scored cases.

Add `--reference` to build the reference layers for the case's framing box and dump a PNG per
layer (coastline, lakes, land, distance transform, plus a composite showing whether
they agree with each other).

Add `--evidence` to build the user-side evidence and dump overlays: the Canny edge map, and an
overlay of the map with kept edges in green and suppressed straight lines (neatlines, graticules,
title and scale boxes) in red. With water picks in the case config it also writes a water
overlay, ocean and lakes in different colours.

Add `--ocr` (which implies `--evidence`) to run text extraction so the edge map gets a text
mask. It costs ~135 s per map the first time and is cached afterwards, and it is worth it:
without it roughly **half** the edge pixels on a labelled map are place names rather than
geography.

The cache is `derived/<test_id>/text_regions.json`, shared by every case on that map and by
the Celery task — so a second case on a map you have already OCR'd costs nothing, and the
first run of the day is the only slow one. `--refresh-derived` recomputes it even when it is
cached (for when text extraction itself changed); `--no-refresh` makes a missing or stale
artifact an error instead, which is how you find out which cases are behind without paying
to bring them up to date.

Step 4 curve alignment runs by default, as in the app: the printout gives the method, whether
alignment was skipped and why (no water picks, say) or refused by a check, and every check
with its value. Add `--no-align` to place the map with the control points alone, the floor
alignment is measured against. Such a run differs from the production configuration, so it
is never promoted to `best`.

Add `--sources sift`, `--sources city` or `--sources sift,city` (the default) to fit from
one source of control points only. Every stage uses the same subset, and the printout gives
the RMS error per source. Run a case with SIFT points and cities three ways to see what each
source carries on its own.

Add `--no-snap` to disable blind coastline snapping. **Do this whenever you are judging
alignment.** Snapping corrects transform error after the fact, which both flatters the baseline
and hides the improvement you are trying to measure — with it on, translating the same transform
5 px swings IoU by 0.012 non-monotonically; with it off the metric falls smoothly. Same switch
in the app: `GEOREF_ENABLE_COASTLINE_SNAPPING`.

### Comparing variants

To compare settings across every case at once, use the variant runner instead of
re-running cases one by one:

```
docker compose run --rm georef-dev python scripts/run_georef_variants.py --list
docker compose run --rm georef-dev python scripts/run_georef_variants.py --stage 1
docker compose run --rm georef-dev python scripts/run_georef_variants.py --variants A1,B2 --case-id pip_7sift
```

Variants are named config sets in `scripts/georef_variants.py`, on top of the file defaults.
It never touches the cases' own files; results go to `Backend-Atlas/ablations/<run>/`
(gitignored), with a `summary.md` comparing every variant to `A0`. See
[`georeferencing-testing.md` §6](georeferencing-testing.md#6-variant-runner); its results are in §8.

### Why did this map place badly?

An IoU number, or a probe case with no number at all, cannot tell you *why* the zones landed
where they did. `alignment_debug/` in the case folder answers that. It is written whenever
`GEOREF_DEBUG` is on — already the case for `celery-worker`, so **every UI re-run produces
it** — and on demand from the CLI with `--debug` (which cannot be combined with
`--no-align`, since there is nothing to diagnose without alignment):

```
docker compose run --rm georef-dev python scripts/run_georef_alignment.py     --case-id 1st --debug --no-snap
```

| File | What it answers |
|---|---|
| `summary.txt` | leads with whether the fit actually engaged; then per-control-point residuals, every gate with value *and* threshold, evidence and reference stats |
| `06`/`07`/`08_reference_*` | the real coastline drawn through the transform onto your map, baseline red and aligned green. **If these do not sit on the drawn coast, that is your answer** |
| `09_control_points` | yellow circle = where you clicked, red cross = baseline prediction, green = aligned. Line length is the residual, so a mispaired point is obvious |
| `10_icp_correspondences` | what ICP matched, and to where |
| `04_edges_over_map` | green = edges used, red = suppressed straight lines |
| `01`–`03`, `05` | raw edges, weight map, text mask, water (water only when pipetted) |
| `alignment.json`, `zones.geojson` | machine-readable gates and phase matrices; the output itself |

Roughly 2–9 MB per case depending on scan size. The folder is **cleared before each run**, so
what is in it is always from the last run — a diagnostic folder quietly mixing two runs is
worse than none. It is gitignored, and it is per-case rather than the timestamped
`debug_runs/` the production import path uses, because a harness case gets re-run against the
same map over and over.

The regression suite does not write it: `test-backend` does not set `GEOREF_DEBUG`, so CI
stays fast without needing its own switch.

For app runs rather than harness runs, `GEOREF_DEBUG=true` (set on `celery-worker` only;
the code default is off) writes a folder per import to `Backend-Atlas/debug_runs/`:
`summary.txt`, overlays of the reference coastline through the transform, control-point
residuals, the edge map, ICP correspondences and the output zones. The newest 20 are kept.

Every container runs the production configuration: curve alignment is on in the app, the
regression suite, the UI re-runs and the CLI alike, so a regression case's `best` always
measures the pipeline that ships. The suite pays for alignment but not for OCR: the text
regions of every regression map are committed under `derived/`.

### Re-running from the UI

The case result page has a **Relancer** panel: it re-runs the case from its saved
inputs and reloads the map in place. What it offers depends on the case's kind, and the
panel says which kind it is.

**Regression case.** It measures the pipeline as the worker runs it, so only the two
post-processing switches are offered, **Snapping côtier** and **Découpe océan**, and both
start at the worker's own values. Re-run without touching them and the result is a plain
run, promotable to `best`; change one and it is written as latest only. No alignment
switch, no model choice, no tuning panel, no point exclusion — to try those, make an
exploration case on the same map. Tuning edits saved in the browser are never sent with a
regression run.

**Exploration case.** Everything below is available:

- **Snapping côtier** defaults **off**, because a re-run button exists to judge
  alignment and that is the one setting you must turn off to do so.
- **Découpe océan** defaults **on**, as the app does.
- **Alignement** defaults **on**, because seeing what the current pipeline does is the
  point of re-running.
- **Modèle de transformation**, the per-point exclusion checkboxes in **Points de
  contrôle**, and the tuning panel described below.

On an **exploration** case, **Points de contrôle utilisés** has one checkbox per source (SIFT,
Villes) with the case's point count for each. Untick one to re-run from the other alone. The
last source that has points cannot be unticked, and a selection with fewer than 3 points
disables the button. The selection travels as `gcp_sources` in the same `config_overrides`,
so a run that does not use every source is never promoted to `best`.

The **Points de contrôle (dernier run)** panel draws the last run's control points on the
map: a dot at the point's true position (amber SIFT, magenta city, hover for the city name)
and a dashed line to where the fitted transform put the pixel you clicked. It also shows the
RMS error per source in km (leave-one-out with `piecewise_affine`; fixed-base, so
optimistic, when alignment supplied the affine -- see `gcpRmseKind` above).

The switches apply to that run only — they never touch the worker's own settings, so two
people can re-run the same case differently at the same time. They reach the task as one
`config_overrides` dict rather than a flag each, so adding a switch later does not change
the Celery signature (which breaks in-flight tasks and any caller that has not restarted
alongside the worker).

**Paramètres (ce run seulement)** (exploration cases only) is a collapsible tuning panel
under the switches. It lists
every `GeorefConfig` field, grouped by section and filterable by name, pre-filled with the
worker's ambient values from `GET /dev-test-api/georef-config`. Edit a threshold and re-run:
only fields that differ from the ambient value are sent, as the JSON body of `run-evaluate`,
and they are validated against the field's type (a 400 names the bad field). `config.py` is
never written. What a run actually used is in its `run_record.json` under `runSwitches`.

- Lists (annealing schedules, ICP radii) are comma-separated; their length may change, which
  adds or removes a level.
- Edits persist in the browser across reloads and cases, so the same thresholds can be tried
  on several maps. The orange badge shows how many are active even when the panel is closed;
  **Tout réinitialiser** clears them.
- A run with any edited field counts as non-default: it is written as latest, never `best`.

Two things it deliberately will not do:

- **A run using any non-default switch is never promoted to `zones_best`.** "Best run so
  far" is only meaningful within one set of settings — snapping alone moves one map
  0.941 vs 0.926 — so a mixed `best` would be a mixture of two metrics. The run is still
  written as the latest result.
- **A case missing a required user input cannot be re-run at all.** The button is disabled
  and says which input, because no amount of re-running recovers a click that never happened.
  **Compléter les entrées** is how to supply it ([§8](#completing-a-case)).

The CLI is still the faster loop — it caches colour extraction, the task path does not. A CLI
run whose flags differ from the deployment's ambient config is, like a UI run with switches,
never promoted to `best`. Use the button when you are already looking at the map;
use `--kind probe --no-snap` when you are iterating.

**Pin your dependencies before trusting a number from this tool.** `numpy` and
`opencv-python-headless` are pinned in `requirements.txt` for a reason: an image rebuilt with a
different numpy produced a different zone geometry on the same map (IoU 0.9406 vs 0.9414). If
you rebuild and a score shifts slightly for no reason you can name, check `pip freeze` across
your containers before believing it.
