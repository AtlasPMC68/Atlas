# Georeferencing — testing and results

How we find out how good the georeferencing pipeline is, which parts earn their place, and
what the measurements say so far. Started 2026-10-02 on `georef-exp`, after the bug fixes of
2026-09-30 ([history](georeferencing-history.md#2026-09-30--three-bugs-that-shaped-every-earlier-number)):
every alignment number measured before them measured the bugs.

Companion documents: [`georeferencing.md`](georeferencing.md) (how the pipeline works),
[`dev-test-tool.md`](dev-test-tool.md) (how to use the harness),
[`georeferencing-roadmap.md`](georeferencing-roadmap.md) (what the results lead to).

**Where to look:** the method is §1–§7, the numbers are [§8](#8-results), and the current
state and next steps are [§9](#9-where-things-stand).

---

## 1. What we want to know

1. **Where we are.** How far off, in kilometres, the pipeline places a map as it runs in the
   app.
2. **What each part is worth.** Piecewise vs affine; whether curve alignment helps, and which
   half (chamfer, ICP); how far the coastline should be allowed to move the map; whether
   snapping helps or hides; SIFT points vs cities.
3. **Whether the gates are worth keeping.** They are neutralised and logged on every run: do
   their values predict the runs where alignment made things worse?

Before this plan there was no honest placement metric (control-point error is measured on the
points the model was fitted to, and IoU mixes placement with extraction) and one scored case.
§3–§7 are the tooling built to fix that.

---

## 2. The plan

| Phase | What | Status |
|---|---|---|
| 1 | Tooling: check points, boundary distance, variant runner, borders as expected zones | done (§3–§7) |
| 2 | The corpus, clicked to one protocol | **modern maps done** (4 maps, 12 cases); historical maps to do |
| 3 | Decision rules, written before any run | done (below) |
| 4 | Noise floor | done (`N1`); not measured for check points |
| 5 | Variant runs | done on the modern corpus (§8) |
| 6 | Analysis and decisions | first pass done (§8); historical maps outstanding |

### The corpus protocol

- **Modern maps** with expected zones loaded from administrative borders (§7), and
  **historical maps** (Quebec 1791, traité 1783, the `pip_7sift` map, Leclerc), judged mainly
  on their check points.
- **Per case:** framing box and legend answer; at least 6 well-spread SIFT points; 3–6 cities
  in the fit; **at least 5 check points**, placed as §3 describes, with cities among them (the
  only check points that are inland, see §8.2); a water pick if the sea is painted.
- **Several cases per map, each varying one user input.** What the pipeline does with the
  inputs (piecewise, snapping, alignment settings, one source only) is a variant (§6), not a
  case. Create the extra cases with *Partir d'un test case existant*
  ([`dev-test-tool.md`](dev-test-tool.md) step 4) so they share everything else with
  `protocol`, check points above all.

  | Case | Inputs | What it tells |
  |---|---|---|
  | `protocol` | The protocol above | The reference; the case the analysis counts |
  | `minimal` | 4 SIFT pairs, no cities; same frame, legend, colours, water pick, check points | What a typical user gets; where alignment has a job |
  | `clustered` | Control points in one part of the map only, same check points | Extrapolation, where models differ |
  | `bad-point` | `protocol` with one pair 15–30 px off or a wrong city; kind **probe** | Robustness; whether the gates notice |
  | `reclick` | Same frame, legend, colours; every point clicked again, ideally by someone else | The real click noise |

- **The water pick is not varied in a case.** Without it, alignment treats every edge as
  candidate coastline; to measure what the water filter is worth, use a variant with
  `edge_water_filter` off on the same case (not in the variant list yet).

### Decision rules (Phase 3)

Written before the numbers were seen:

- **Alignment ships** if it lowers check-point error on a clear majority of cases and never
  makes a case worse by more than the click noise.
- **Piecewise becomes the default** only if it beats the affine on check-point error; its own
  leave-one-out does not count. (A *per-map* choice by leave-one-out is a different thing,
  validated the same way: [roadmap §2](georeferencing-roadmap.md#2-transform-model-affine-by-default-piecewise-by-leave-one-out).)
- **Snapping stays** only if it improves the shipped output's boundary distance on the modern
  maps.
- **The gates stay** only if their logged values predict the cases where alignment made
  check-point error worse.

### How results are read

- Per variant: the difference from `A0` on each case, the median difference, and a count of
  cases better and worse beyond the noise floor. With about ten cases, counting wins and
  losses is the honest tool; averages let one map decide.
- Metrics in order of trust:
  1. **Check-point error** (km): placement only.
  2. **Boundary distance and IoU before cleaning**: placement plus extraction.
  3. **Boundary distance and IoU after cleaning**: the shipped output, and the regression
     score.
  4. **Control-point error inside the fit**: a diagnostic, never a verdict.

---

## 3. Check points

A check point is a pixel ↔ lon/lat pair clicked exactly like a control point that **nothing
fitting ever sees**. After the run, the transform that placed the zones is applied to its
pixel; the distance to its true position, in ground km, is its error. It judges the transform
actually shipped, on points it was not fitted to.

- **A separate list, not a role.** `georef.checkPoints` in a case's `config.json`, same shape
  as control points. Control points flow into the baseline, the alignment, the probe, the
  piecewise pins, the source filter and the leave-one-out; a role flag would have to be
  filtered out at each, and one missed filter would silently turn a check point into a fitted
  one. As a separate list they never enter `control_points`. A test runs the pipeline with and
  without absurd check points and asserts byte-identical output.
- **Rules.** Not the same city or clicked pixel (within 1 px) as a control point, and not the
  same city twice; a case breaking this is refused when read. Optional.
  Changing them resets the case's best.
- **Two kinds.** Cities (*Villes de vérification* step) and SIFT pairs (ticked
  *vérification* in the SIFT step). **SIFT check points are always on the coast** (SIFT
  keypoints are coastline features), so they judge coastline alignment on its own ground;
  cities are the inland judges.
- **Reported** in `run_record.json` under `errors.checkPoints`: `rmseKm`, `medianKm`,
  `maxKm`, per point its error and placement, `byModel` (the same RMS for the control-point
  affine), and `byPlacement` (RMS inside and outside the control points' hull). Placement
  fields per point:

  | Field | Why it matters |
  |---|---|
  | `nearestControlPx` | Next to a control point, an interpolating model is pinned and scores near zero |
  | `insideControlHull` | Inside the hull models interpolate; outside they extrapolate |
  | `coastDistanceKm` | Alignment has evidence at the coast and none inland |
  | `gcpAffineErrorKm` | The control-point affine's error at the same point |

- **Placing them:** spread over the area the zones cover, mostly inside the control points'
  hull and at least ~1/3 of the typical gap between control points away from any of them;
  one or two outside the hull; a mix of coastal and inland, with **several inland cities**.

---

## 4. Boundary distance

For each expected zone and its matched extracted zone, both **outer rings** are sampled every
0.5 km of ground, converted to Earth-centred xyz, and each sample is matched to the nearest
sample of the other ring (k-d tree). Reported: the symmetric **mean**, the **p90** and the
**max**, plus each direction's mean (`expectedToExtractedMeanKm`,
`extractedToExpectedMeanKm`). Floor: 0.25 km.

- **3D, not a flat projection:** zones span many degrees of latitude, where any single flat
  projection is off by ~15% at the edges.
- **Outlines only.** Holes (lakes, text) are counted (`expectedHoles`, `extractedHoles`) but
  not measured: a lake hole is not a misplaced border, and IoU already charges it. With holes
  measured, `pip_7sift` reported a 30 km mean for a 4 km one.
- **Read the two directions apart when they disagree.** Pieces of the extracted zone far from
  the expected one (colour collisions, specks) inflate the extracted→expected direction while
  barely moving IoU. On Maghreb, Algeria was 5 km expected→extracted and 409 km the other way
  (§8.6). The expected→extracted direction is the placement-like one.

An expected zone with no match has no boundary distance (`null`); the count is reported.

---

## 5. Scoring before and after cleaning

Cleaning (snapping, ocean clip, lake cut) is part of what ships, so it is tested, but it
corrects transform error after the fact, so placement cannot be judged through it. Every run
is scored twice:

| | Zones | Against | Used for |
|---|---|---|---|
| **Main** (`report.json`) | after snapping, ocean clip, lake cut | the expected zones through the **same ocean and lake cuts** | the regression score, PASS/FAIL, best |
| **Raw** (`report.json` → `raw`) | as the transform placed them | the expected zones **as drawn** | judging georeferencing |

- **One mask.** `georeferencing/cleaning.py` builds land minus ocean and Natural Earth lakes
  once; the pipeline's clip and `clean_expected_zones` both use it. Snapping is not applied to
  expected zones: it corrects a transform, and a drawing has none. Expected zones are cut,
  never dropped.
- **Cleaned expected zones are derived.** Saving a map's expected zones also writes
  `<id>_zones_cleaned.geojson`, stamped with the drawn file's hash and `CLEANING_VERSION`;
  when either stops matching, it is recomputed on the next read.
- **Score version 2** is recorded in every report (version 1 compared the shipped zones with
  the zones as drawn).

---

## 6. Variant runner

```
docker compose run --rm georef-dev python scripts/run_georef_variants.py --list
docker compose run --rm georef-dev python scripts/run_georef_variants.py --stage 1,2
docker compose run --rm georef-dev python scripts/run_georef_variants.py \
    --variants A0,B2,B5c --test-id <id>,<id> --case-id protocol,minimal
```

- **Variants are code** (`scripts/georef_variants.py`): a name, a stage, a question, and
  overrides **on the file defaults**, never on a container's environment.
- **Per case**, OCR and colour extraction run once and are shared; only the transform differs
  between georeferencing variants. Results are computed in memory: the case's own files are
  never touched.
- **Output** in `Backend-Atlas/ablations/<run>/` (gitignored): per case and variant the zones,
  raw zones, run record and metrics; `results.csv` (one row per case × variant × metric);
  `summary.md` (per metric, cases × variants against `A0`, median difference, better/worse
  counts); `variants.json` (overrides, config version, a hash of the code). **Copy what
  matters into §8**: the folder is not committed.
- **Noise floor `N1`:** `A0` with the zones moved by one pixel. Better/worse counts ignore any
  difference within a case's own `N1` difference, and never less than 0.1 km or 0.001 IoU.
  `N1` does not move check points, so their floor is not measured (the 0.1 km is a
  placeholder).
- A variant a case cannot run (cities only, with fewer than 3 cities) is reported as skipped.
- `--test-id` and `--case-id` take comma-separated lists.

| Stage | Variants |
|---|---|
<<<<<<< HEAD
| 1. Base transform | `A0` affine, no snapping, clipping on (the floor) · `A1` piecewise · `A1La/b/c` piecewise, local regularization at reach 0.1, 0.175, 0.25 of the diagonal · `A2` A0 + snapping · `A3` / `A4` SIFT / cities only |
| 2. Alignment | `B1` chamfer only · `B2` chamfer + ICP · `B3` B2 + piecewise · `B3La/b/c` B2 + local piecewise, same reaches · `B4` ICP at 60° · `B5a/b/c/d` coastline weight ×3, ×10, ×30, ×100 · `B6` chamfer only at ×10 · `B7` B3Lb then align again (align → piecewise → align) · `B8` local piecewise at 0.175 then align (piecewise → align; the GCP affine is aligned when the correction is refused) · `B7a/b` B7 with coastline weight ×3, ×10 |
=======
| 1. Base transform | `A0` affine, no snapping, clipping on (the floor) · `A1` piecewise · `A2` A0 + snapping · `A3` / `A4` SIFT / cities only |
| 2. Alignment | `B1` chamfer only · `B2` chamfer + ICP · `B3` B2 + piecewise · `B4` ICP at 60° · `B5a/b/c/d` coastline weight ×3, ×10, ×30, ×100 · `B6` chamfer only at ×10 · `B7` / `B8` ICP only at ×1 / ×10 |
>>>>>>> d64ed9e18b630019801f49502b7300c181814c05
| 3. Production | `PROD`: file defaults with alignment on (= alignment + piecewise + snapping) |
| Extraction | `E2` zone gap fill on (`E1`, label text fill, was removed with the method) |
| Noise | `N1` |

---

## 7. Expected zones from administrative borders

The test editor can load a real border as an expected zone and cut off what the map does not
show (usage: [`dev-test-tool.md`](dev-test-tool.md) step 3).

- `app/utils/borders.py` indexes every file in `app/geojson/borders/` once (~6 s), recognised
  by its properties: Natural Earth admin-0/admin-1, geoBoundaries ADM0/ADM1. Admin-1 units are
  grouped by Natural Earth's `region` (Italy: 110 provinces in 20 regions); several units load
  as one merged zone, simplified at ~500 m. Files: `scripts/fetch_natural_earth_borders.py`.
- **Plain files, not the "_lakes" variants**: lakes are cut by the cleaning step with the
  pipeline's own lake layer (§5).
- Known limits: the UK's groups are statistical regions, not its four nations.

---

## 8. Results

### 8.1 First corpus run (2026-10-04)

Four modern maps with expected zones from Natural Earth, three cases each (`protocol`,
`minimal`, `clustered`; Maghreb's protocol case is `protocol-frontiere-heavy`, Test 1's
minimal is `minimal-4`). `south-america` was left out: its colour extraction is broken, so its
scores say nothing about georeferencing. Every variant of §6 ran; the weight sweep
(`B5c`, `B5d`, `B6`) followed the same day. Runs: `corpus-2026-10-04`,
`weight-sweep-2026-10-04`.

| Map | Case | SIFT | Cities | Check points (SIFT / city) |
|---|---|---|---|---|
| Test 1 | protocol / minimal-4 / clustered | 8 / 4 / 6 | 3 / 0 / 1 | 5/0 · 5/0 · 7/2 |
| central africa | protocol / minimal / clustered | 9 / 5 / 7 | 5 / 0 / 0 | 4/2 · 5/6 · 7/6 |
| Maghreb | protocol / minimal / clustered | 4 / 4 / 4 | 6 / 0 / 7 | 0/4 · 0/8 · 0/5 |
| east asia | protocol / minimal / clustered | 8 / 5 / 5 | 6 / 0 / 2 | 3/5 · 6/8 · 6/7 |

Check points differ between a map's cases (the copy-a-case feature came later), so variants
compare within a case, not protocol against minimal.

**Check-point error (km), selected variants:**

| Case | A0 floor | B2 align ×1 | B5b ×10 | B5c ×30 | B5d ×100 | B6 ×10 no ICP | PROD |
|---|---|---|---|---|---|---|---|
| Test 1 protocol / minimal-4 / clustered | 18 / 20 / 31 | 18 / 20 / 16 | 17 / 18 / 15 | 17 / 17 / 15 | 17 / 17 / 15 | 18 / 18 / 16 | 21 / 20 / 17 |
| central africa protocol / minimal / clustered | 92 / 106 / 160 | 84 / 93 / 82 | 62 / 65 / 68 | 59 / 63 / 62 | 59 / 62 / 61 | 73 / 69 / 69 | 96 / 93 / 88 |
| Maghreb protocol / minimal / clustered | 32 / 132 / 108 | 31 / 83 / 58 | 21 / 35 / 37 | 18 / 30 / 36 | 18 / 30 / 37 | 26 / 39 / 60 | 29 / 78 / 58 |
| east asia protocol / minimal / clustered | 114 / 112 / 144 | 113 / 112 / 138 | 114 / 113 / 111 | 110 / 113 / 111 | 109 / 114 / 110 | 112 / 115 / 118 | 113 / 112 / 146 |

Against `A0`, better / worse on check points: `B1` 11/1, `B2` 11/0, `B4` 11/0, `B5a` 11/0,
`B5b` 10/2 (the two worse within 0.7 km), `B3` and `PROD` 8/4, `A1` 6/5 (median −0.2 km),
`A3` 2/5, `A4` 3/2 (skipped where < 3 cities).

### 8.2 Coast or inland: where the gain is

Pooling every check point of the 12 cases (each better/worse is per point against `A0`,
changes under 1 km ignored):

| Variant | Coastal (≤ 50 km, 55 pts) RMS · better/worse | Inland (46 pts) RMS · better/worse |
|---|---|---|
| A0 | 116 km | 108 km |
| B2 (×1) | 76 · 37/8 | 105 · 19/17 |
| B5c (×30) | **45** · 45/9 | 100 · 21/24 |
| PROD | 78 · 36/15 | 109 · 19/24 |

By source, which is almost the same split (SIFT check points are coastal by construction; 34
of the 53 city check points are more than 50 km from the coast, median 164 km):

| Variant | SIFT (48) RMS · better/worse | City (53) RMS · better/worse | City RMS per map: Test 1 · central africa · Maghreb · east asia |
|---|---|---|---|
| A0 | 107 | 117 | 26 · 48 · 109 · 156 |
| B1 (×1, no ICP) | 81 · 30/9 | 103 · **35/14** | 20 · 34 · 66 · 153 |
| B2 (×1) | 72 · 26/8 | 105 · 30/17 | 20 · 45 · 67 · 154 |
| B5c (×30) | **48** · 35/12 | **93** · 31/21 | 20 · 44 · 30 · 145 |
| PROD | 76 · 29/16 | 107 · 26/23 | 21 · 54 · 64 · 157 |

City check points at ×30, per map: Maghreb 15 better / 2 worse; central africa 7/7; east asia
7/12 (RMS down only because a few large errors shrink); Test 1 has only 2.

**Reading.** Alignment fixes the coast a lot and the interior a little. With one affine for the
whole map, a high coastline weight bends the affine to the coast and the interior pays where
the map's coast and interior disagree (central africa). No map shows an inland loss in RMS,
but individual cities go either way. This is the measured case for a warp that can follow the
coast locally without dragging the interior ([roadmap §3](georeferencing-roadmap.md#3-a-smoothed-non-rigid-warp-driven-by-the-coastline)).

### 8.3 Verdicts against the decision rules

| Question | Verdict | Evidence |
|---|---|---|
| Does alignment ship? | **Yes** | `B2` lowers check-point error on 11 of 12 cases, worse on none; it improves the protocol case of all four maps |
| How much coastline weight? | **×30 is the candidate**, not final | Gain grows ×1 → ×3 → ×10 → ×30, then stops (×100 ≈ ×30). The gain is mostly coastal (§8.2); confirm on historical maps with city check points first |
| Chamfer only, or chamfer + ICP? | **Keep ICP** | At ×1 they are close (`B1` has the better city ratio); at ×10, without ICP is worse on 11 of 12 cases |
| ICP only, without the chamfer? | **Keep the chamfer** | At ×10, ICP alone is worse on 9 of 14 cases, better on 3 by under 0.3 km; the losses are on the clustered cases (§8.9) |
| ICP at 60°? | No | `B4` ≈ `B2` |
| Piecewise as the default? | **No** | `A1` vs `A0`: 6 better, 5 worse, median ≈ 0. On top of alignment (`B3`) worse than `B2` on 8 of 12; this is what makes `PROD` worse than `B2`. Expected change: `affine` default, piecewise chosen per map by leave-one-out |
| Does snapping stay? | **Yes** | `A2` improves the shipped outline distance on 9 of 12 cases and IoU on 8, worse on none. Check points cannot see it (it acts after the transform) |
| SIFT or cities? | **Both** | Without cities (`A3`) 5 cases worse, 2 better (Maghreb clustered 108 → 228 km). On Maghreb, cities alone beat both together (18 vs 32 km): its SIFT points are the weaker source. Cities alone fail with 3 cities (Test 1, 160 km) |
| Extraction options | **Keep `inpaint`, gap fill off** | `E1` worse on raw outline distance on all 12; `E2` much worse (up to +100 km), see §8.6 |
| Do the gates stay? | **No; replaced** | Every run settled at rung 0 and alignment made no case worse, so the gate values had nothing to predict. Replaced (2026-10-07) by a water precondition and four lenient checks ([`georeferencing.md` §5.2](georeferencing.md#52-curve-alignment)) |

### 8.4 Why piecewise loses here

Our piecewise model passes **exactly** through every control point and spreads each point's
residual linearly over its triangles. That pays when residuals are real local distortion
(a hand-drawn map with one region drawn too big, many accurate points). On these modern
maps the map-to-world relation is smooth, so the residual at each point is mostly click and
drawing noise, which an exact interpolator copies into the zones while a least-squares affine
averages it out. With 4–14 points the triangles span hundreds of km, and the anchors force the
correction to zero at the frame, where a systematic error is usually largest. After alignment
it re-pins every click, undoing the coastline's compromise (`B3` < `B2`). So the result says
"wrong tool for clean maps with few points", not "broken implementation"; historical maps are
where it could still earn its place.

### 8.5 East asia: no affine fits

The control points themselves sit 19–61 km off the best affine (61 km on `protocol`), and
check-point error stays at 110–145 km whatever the variant. At that scale a map drawn in
another projection than the one we fit in cannot be matched by one affine. Hypothesis, not
verified; it needs a smooth global model (§3 of the roadmap).

### 8.6 Colour collisions distort zone metrics

On Maghreb, "Algérie" contains a 255,000 km² piece near (25°E, 17°N) in Sudan/Chad and
"Mauritanie" pieces in Egypt; on east asia, "south korea" has pieces 1,000–2,600 km away in
China. The map paints unpicked countries in the picked colours, and extraction assigns them.
Hence a 1,500 km outline p90 next to a 32 km check-point error on Maghreb. Differences between
variants are still meaningful (same extraction for all); absolute zone scores on those maps are
not placement. It is also a production bug ([roadmap §5](georeferencing-roadmap.md#5-extraction-colour-collisions)).

Probably related: `E2` (gap fill) vectorises zones pixel by pixel (`mask_to_pixel_edge_geometry`)
where the normal path uses `cv2.findContours`, which drops 1–2-pixel specks. Hundreds of kept
specks would explain its outline explosion with little IoU change. Not verified.

### 8.7 Unexplained

On central africa `clustered`, alignment halves the check-point error while zone IoU drops
(0.833 → 0.80 at ×1), and at higher weight the protocol case loses IoU (0.903 → 0.872) while
its check points improve. Chamfer without ICP gives 0.911 on `clustered`. Not looked at yet.

### 8.8 What these results cannot support

- **Modern maps only.** Historical maps, the product's real target, are untested: their
  drawn coasts are themselves distorted, which matters most for a high coastline weight.
- **Too few inland check points per map** to judge the interior map by map.
- **No check-point noise floor.** The effects are tens of km, so no conclusion depends on it.

### 8.9 ICP only (2026-10-07)

Is the chamfer still needed once the water filter has identified the coastline? Run
`icp-only-2026-10-07`: every regression case (17; 14 with check points), `B7` / `B8` (ICP only
from the control-point affine, ×1 / ×10) against `B2` / `B5b` (chamfer + ICP at the same
weights), same code (config v15, before the checks were redesigned; every aligned run passed).

**Check-point error (km)**, the cases with check points:

| Case | A0 | B2 ×1 | B7 ICP ×1 | B5b ×10 | B8 ICP ×10 |
|---|---|---|---|---|---|
| Test 1 protocol / minimal-4 / clustered / 7sift-5-checkpoints | 18.0 / 20.0 / 31.0 / 18.8 | 17.6 / 19.5 / 15.9 / 18.5 | 17.6 / 19.5 / **25.1** / 18.5 | 17.2 / 17.5 / 15.4 / 17.8 | 17.1 / 17.7 / **20.3** / 17.8 |
| central africa protocol / minimal / clustered | 91.5 / 106.4 / 159.5 | 84.4 / 92.5 / 81.7 | 84.7 / 92.8 / 83.7 | 62.5 / 65.3 / 68.2 | 67.2 / 71.2 / 68.6 |
| Maghreb protocol / minimal / clustered | 32.2 / 131.9 / 108.2 | 30.5 / 83.2 / 58.0 | 30.5 / **95.5** / 62.7 | 20.5 / 35.4 / 37.3 | 23.2 / 36.7 / **53.7** |
| east asia protocol / minimal / clustered | 113.8 / 112.0 / 144.4 | 113.0 / 112.0 / 138.0 | 113.0 / 112.0 / 138.2 | 114.0 / 112.6 / 111.2 | 113.5 / 112.2 / **120.4** |
| south-america protocol | 129.3 | 125.4 | 125.4 | 135.3 | 130.0 |

`B7` vs `B2`: better 0, worse 7, median +0.07 km. `B8` vs `B5b`: better 3 (all under 0.3 km
except south-america, whose extraction is broken), worse 9, median +0.9 km. Raw IoU: a wash
(`B8` vs `B5b` 5 better, 5 worse). ICP alone is about 2.5 s faster per run (median 5.6 s
against 8.1 s, colour extraction included).

**Reading.** The losses concentrate on the `clustered` cases, whose control points cover one
part of the map: the control-point affine extrapolates badly elsewhere, so the coast there
starts beyond ICP's 40 px search radius and only the chamfer's wide basin brings it in. In-fit
control-point error says nothing about this (it is 3–8 px on those cases): what matters is how
far off the coast is *away* from the points. **The chamfer stays.** ICP-only could become a
fast path for maps with well-spread points, but no measured case asks for it.

---

## 9. Where things stand

2026-10-05.

**Exists:** check points (cities and SIFT), placement fields, boundary distance, scoring
before and after cleaning, expected zones from borders, the variant runner, cases that can be
completed, edited, or started from another case's inputs. Scored maps: Test 1, Maghreb,
central africa, east asia (south-america excluded until its extraction works).

**Decided so far (modern maps):** alignment on; keep ICP; keep snapping; keep `inpaint`; gap
fill off. **Applied (config v15):** alignment on everywhere, CI included; coastline weight ×10.
**Expected, not applied yet:** `affine` as the default model with piecewise chosen per map by
leave-one-out; possibly ×30 once historical maps confirm it
([`georeferencing.md` §8](georeferencing.md#8-configuration-and-switches)).

**Next, in order:**

1. **Inland city check points** on the existing cases (at least 3–4 per case, mainly central
   africa and Test 1), with "Modifier les entrées".
2. **2–3 historical cases**, judged on city check points, then rerun `A0`, `B2`, `B5c`,
   `PROD` and an `AUTO` (leave-one-out selector) variant.
3. **Runner improvements:** a coastal/inland (or city/SIFT) split in `summary.md`; one vote
   per map (its `protocol` case) in the better/worse counts; a modern/historical tag per test.
4. Then settle the production configuration and align CI and the dev-test UI on it
   ([`georeferencing.md` §10](georeferencing.md#10-before-the-pull-request)).
