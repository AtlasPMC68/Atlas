"""The simulated user (georeferencing-synthetic.md §3.4): what a user could click on a map
(candidates), what they did click (a layout), and their water pick."""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import shapely
from shapely.geometry import MultiPoint, Point
from shapely.geometry.base import BaseGeometry

from app.utils.city_gazetteer import cities_in_frame
from app.utils.georeferencing import ControlPoint
from app.utils.sift_key_points_finder import find_coastline_keypoints

from .regions import Rejected
from .warps import Warp

#: A candidate is kept when its true pixel is this far inside the image (share
#: of each side): a user does not click on the very edge of the map.
CANDIDATE_MARGIN_RATIO = 0.02

SOURCE_SIFT = "sift"
SOURCE_CITY = "city"

#: Two clicked points closer than this (share of the diagonal) would constrain
#: nothing more than one; a user would not click both. The keypoint finder's own
#: duplicate floor.
MIN_POINT_SEPARATION_RATIO = 0.01
MIN_POINTS = 3

WATER_PICK_RADIUS_PX = 20

BAD_SIFT_MISMATCH = "sift_mismatch"

#: The two layout families: ``open`` (what a user does, §3.4) and ``protocol``
#: (what the real corpus's protocol cases ask, georeferencing-testing.md §2).
FAMILY_OPEN = "open"
FAMILY_PROTOCOL = "protocol"

#: Check points, placed as the real cases' protocol asks
#: (georeferencing-testing.md §3, "Placing them"): up to this many SIFT
#: suggestions and cities the layout did not click; at most
#: ``CHECK_OUTSIDE_HULL`` outside the control points' hull; none nearer a
#: control point than ``CHECK_GAP_RATIO`` of their typical gap; within
#: ``CHECK_ZONE_MARGIN_RATIO`` of the diagonal of the zones.
CHECK_SIFT = 4
CHECK_CITY = 4
CHECK_OUTSIDE_HULL = 2
CHECK_GAP_RATIO = 1.0 / 3.0
CHECK_ZONE_MARGIN_RATIO = 0.02


def _inside(px: np.ndarray, py: np.ndarray, image_size: Tuple[int, int]) -> np.ndarray:
    w, h = image_size
    mx, my = CANDIDATE_MARGIN_RATIO * w, CANDIDATE_MARGIN_RATIO * h
    return (px >= mx) & (px <= w - 1 - mx) & (py >= my) & (py <= h - 1 - my)


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------


def sift_candidates(frame_bounds: Dict[str, float], warp: Warp) -> List[Dict[str, Any]]:
    """The real keypoint suggestions for the framing box, where the map draws them."""
    keypoints = find_coastline_keypoints(frame_bounds)["keypoints"]
    if not keypoints:
        return []
    lon = np.array([kp["geo"]["lng"] for kp in keypoints])
    lat = np.array([kp["geo"]["lat"] for kp in keypoints])
    px, py = warp.forward(lon, lat)
    keep = _inside(px, py, warp.image_size)
    return [
        {
            "lon": float(lon[i]),
            "lat": float(lat[i]),
            "pixel": (float(px[i]), float(py[i])),
            "feature": keypoints[i]["feature"],
            "response": keypoints[i]["response"],
        }
        for i in np.flatnonzero(keep)
    ]


def city_candidates(frame_bounds: Dict[str, float], warp: Warp) -> List[Dict[str, Any]]:
    """The gazetteer cities inside the framing box that the map shows."""
    cities = sorted(cities_in_frame(frame_bounds), key=lambda c: c.geonameid)
    if not cities:
        return []
    lon = np.array([c.lon for c in cities])
    lat = np.array([c.lat for c in cities])
    px, py = warp.forward(lon, lat)
    keep = _inside(px, py, warp.image_size)
    return [
        {
            "id": cities[i].geonameid,
            "name": cities[i].name,
            "lon": float(lon[i]),
            "lat": float(lat[i]),
            "population": cities[i].population,
            "pixel": (float(px[i]), float(py[i])),
        }
        for i in np.flatnonzero(keep)
    ]


# --------------------------------------------------------------------------
# The water pick
# --------------------------------------------------------------------------


def water_pick(ocean: np.ndarray) -> Optional[Tuple[float, float]]:
    """The ocean pixel farthest from any land, normalised; None without ocean."""
    if not ocean.any():
        return None
    distance = cv2.distanceTransform(ocean.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(np.argmax(distance)), distance.shape)
    h, w = ocean.shape
    return (float(x) / w, float(y) / h)


# --------------------------------------------------------------------------
# The layout
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LayoutOptions:
    """What a layout is drawn from. Tests narrow it (no noise, say)."""

    #: SIFT pairs: never fewer than the import's minimum. The count asked for is
    #: uniform from this share of the suggestions on the map to all of them: a
    #: user matches most of what the finder shows.
    min_sift: int = MIN_POINTS
    sift_request_low_ratio: float = 0.6
    #: Cities are optional in the import, and most maps show none the gazetteer
    #: knows: none this often, otherwise a uniform count in ``city_count``.
    no_city_probability: float = 0.6
    city_count: Tuple[int, int] = (1, 6)
    #: The area the user clicks in, log-uniform, as a share of the image diagonal.
    #: From 15%, a quarter of layouts were clipped to exactly 3 points.
    radius_ratio: Tuple[float, float] = (0.3, 1.0)
    #: σ of a click, px, per layout. Up to 8 px: with 4, the control-point
    #: affine's in-fit residual was 3.5 px on the matched maps against 6.7 on
    #: real ones (georeferencing-synthetic.md §10.2).
    noise_px: Tuple[float, float] = (1.0, 8.0)
    #: One SIFT pair matched to the neighbouring feature of the same curve.
    bad_probability: float = 0.05
    #: Layouts drawn as the corpus protocol asks: the whole map, at least
    #: ``protocol_min_sift`` SIFT pairs and ``protocol_city_count`` cities, each
    #: picked away from the points already chosen. 7 of the real corpus's 17
    #: scored cases are protocol cases; without them a layout had a control
    #: point far from the coast 15% of the time, against 59% on the real ones
    #: (georeferencing-synthetic.md §10.6).
    protocol_probability: float = 0.4
    protocol_min_sift: int = 6
    protocol_city_count: Tuple[int, int] = (3, 6)
    mismatch_along_px: Tuple[float, float] = (20.0, 80.0)


@dataclass
class Layout:
    params: Dict[str, Any]
    #: Each: source, clicked pixel, true pixel, lon/lat given to the pipeline,
    #: the city (id, name) for a city, the curve (feature) for a SIFT pair, and
    #: whether it is the bad one.
    points: List[Dict[str, Any]]
    #: Held out, the same shape (never bad): what the run is scored on as the
    #: real cases are (``errors.checkPoints``), never fitted.
    check_points: List[Dict[str, Any]] = field(default_factory=list)

    def control_points(self) -> List[ControlPoint]:
        return [_control_point(p) for p in self.points]

    def check_control_points(self) -> List[ControlPoint]:
        return [_control_point(p) for p in self.check_points]


def extra_click(source: str, candidate: Dict[str, Any], offset: np.ndarray) -> ControlPoint:
    """One more control point, clicked on *candidate* (a SIFT suggestion or a
    city) *offset* px from where the map draws it: the click a user adds
    when asked (georeferencing-synthetic.md §4.3, Q5)."""
    point = _point(source, candidate)
    clicked = np.array(point["drawnPixel"]) + offset
    point["pixel"] = (float(clicked[0]), float(clicked[1]))
    return _control_point(point)


def _control_point(p: Dict[str, Any]) -> ControlPoint:
    geo = (p["lon"], p["lat"])
    if p["source"] == SOURCE_CITY:
        return ControlPoint.from_city(p["pixel"], geo, p["city"]["id"], p["city"]["name"])
    return ControlPoint.sift(p["pixel"], geo)


def _point(source: str, c: Dict[str, Any]) -> Dict[str, Any]:
    """A point before its click: aimed where the map draws it."""
    point = {
        "source": source,
        "pixel": None,
        "truePixel": (float(c["pixel"][0]), float(c["pixel"][1])),
        # Where the map draws it: off the true pixel when the coast is generalised.
        "drawnPixel": tuple(float(v) for v in c.get("drawnPixel", c["pixel"])),
        "lon": c["lon"],
        "lat": c["lat"],
        "bad": None,
    }
    if source == SOURCE_CITY:
        point["city"] = {"id": c["id"], "name": c["name"]}
    else:
        point["feature"] = c["feature"]
    return point


def _pick(
    rng: np.random.Generator,
    candidates: List[Dict[str, Any]],
    weights: np.ndarray,
    chosen_pixels: List[Tuple[float, float]],
    min_separation: float,
) -> Optional[int]:
    """One candidate by weight, among those not too close to a chosen point."""
    pixels = np.array([c["pixel"] for c in candidates])
    ok = weights > 0
    for px, py in chosen_pixels:
        ok &= np.hypot(pixels[:, 0] - px, pixels[:, 1] - py) >= min_separation
    if not ok.any():
        return None
    w = np.where(ok, weights, 0.0)
    return int(rng.choice(len(candidates), p=w / w.sum()))


def _spread_pick(
    rng: np.random.Generator,
    candidates: List[Dict[str, Any]],
    weights: np.ndarray,
    chosen_pixels: List[Tuple[float, float]],
    min_separation: float,
) -> Optional[int]:
    """As ``_pick``, the weights times the squared distance to the nearest
    point already chosen: a protocol user spreads the points over the map."""
    if chosen_pixels:
        pixels = np.array([c["pixel"] for c in candidates])
        chosen = np.array(chosen_pixels)
        nearest = np.min(
            np.hypot(pixels[:, None, 0] - chosen[None, :, 0], pixels[:, None, 1] - chosen[None, :, 1]), axis=1
        )
        weights = weights * nearest**2
    return _pick(rng, candidates, weights, chosen_pixels, min_separation)


def _area(
    rng: np.random.Generator, sift_pixels: np.ndarray, radius: float, min_sift: int
) -> Tuple[np.ndarray, float, int]:
    """The circle the user clicks in: centred on a SIFT suggestion, chosen with
    probability proportional to how many suggestions lie within *radius* of it
    (dense areas are favoured, but a map's small-radius layouts do not all land
    on the same cluster); grown until it holds *min_sift* suggestions."""
    distances = np.hypot(
        sift_pixels[:, None, 0] - sift_pixels[None, :, 0],
        sift_pixels[:, None, 1] - sift_pixels[None, :, 1],
    )
    within = (distances <= radius).sum(axis=1).astype(float)
    centre = int(rng.choice(len(sift_pixels), p=within / within.sum()))
    needed = float(np.sort(distances[centre])[min_sift - 1])
    return sift_pixels[centre], max(radius, needed), centre


def _mismatch(
    rng: np.random.Generator, true_pixel: np.ndarray, curves: BaseGeometry, options: LayoutOptions
) -> Optional[Tuple[np.ndarray, float]]:
    """Where a user clicks who matched the neighbouring cape or bay: a point of
    the same drawn curve, 20-80 px along it. None when the curve is too short."""
    lines = [g for g in shapely.get_parts(curves) if g.geom_type == "LineString" and g.length > 0]
    if not lines:
        return None
    point = Point(*true_pixel)
    line = min(lines, key=lambda g: g.distance(point))
    at = line.project(point)
    along = float(rng.uniform(*options.mismatch_along_px))
    targets = (at + along, at - along) if rng.random() < 0.5 else (at - along, at + along)
    for target in targets:
        if 0.0 <= target <= line.length:
            moved = line.interpolate(target)
            return np.array([moved.x, moved.y]), along
    return None


def draw_layout(
    rng: np.random.Generator,
    warp: Warp,
    sift: List[Dict[str, Any]],
    cities: List[Dict[str, Any]],
    curves: Dict[str, BaseGeometry],
    options: LayoutOptions = LayoutOptions(),
    family: str = FAMILY_OPEN,
) -> Layout:
    """Which candidates the user clicked, and how well.

    *curves* are the drawn curves in pixels by keypoint feature (coastline,
    lake), for the SIFT mismatch. *family* is drawn by the caller from a stream
    of its own, so an open layout makes the draws it made before protocol
    layouts existed.
    """
    if len(sift) < options.min_sift:
        raise Rejected(f"fewer than {options.min_sift} SIFT suggestions on the map")
    w, h = warp.image_size
    diagonal = float(np.hypot(w, h))
    protocol = family == FAMILY_PROTOCOL

    low = max(options.min_sift, math.ceil(options.sift_request_low_ratio * len(sift)))
    if protocol:
        low = min(len(sift), max(low, options.protocol_min_sift))
    sift_requested = int(rng.integers(low, len(sift) + 1))
    if protocol:
        city_requested = int(rng.integers(options.protocol_city_count[0], options.protocol_city_count[1] + 1))
    else:
        city_requested = (
            0
            if rng.random() < options.no_city_probability
            else int(rng.integers(options.city_count[0], options.city_count[1] + 1))
        )
    sift_pixels = np.array([c["pixel"] for c in sift])
    if protocol:
        # The whole map: a circle round its centre that holds every corner.
        radius_ratio = 1.0
        centre, radius, centre_index = np.array([w / 2.0, h / 2.0]), diagonal, None
    else:
        lo, hi = (math.log(v) for v in options.radius_ratio)
        radius_ratio = float(math.exp(rng.uniform(lo, hi)))
        centre, radius, centre_index = _area(rng, sift_pixels, radius_ratio * diagonal, options.min_sift)
    noise = float(rng.uniform(*options.noise_px))
    min_separation = MIN_POINT_SEPARATION_RATIO * diagonal

    def inside(candidates: List[Dict[str, Any]]) -> List[int]:
        return [
            i
            for i, c in enumerate(candidates)
            if math.hypot(c["pixel"][0] - centre[0], c["pixel"][1] - centre[1]) <= radius
        ]

    # SIFT first, uniform among the suggestions in the area: the finder already
    # spreads them and keeps them apart. A protocol user spreads them further.
    sift_in = inside(sift)
    chosen: List[Tuple[str, Dict[str, Any]]] = []
    if protocol:
        sift_weights = np.ones(len(sift))
        for _ in range(min(sift_requested, len(sift_in))):
            index = _spread_pick(rng, sift, sift_weights, [c["pixel"] for _, c in chosen], 0.0)
            if index is None:
                break
            chosen.append((SOURCE_SIFT, sift[index]))
            sift_weights[index] = 0.0
        chosen.sort(key=lambda sc: sift.index(sc[1]))
    else:
        picked = rng.choice(sift_in, size=min(sift_requested, len(sift_in)), replace=False)
        chosen = [(SOURCE_SIFT, sift[int(i)]) for i in sorted(picked)]

    # Then cities in the area, the biggest names first (weight sqrt(population)),
    # never within the duplicate floor of a point already chosen; a protocol
    # user picks them away from the points already chosen too, inland ones
    # included.
    weights = np.zeros(len(cities))
    for i in inside(cities):
        weights[i] = math.sqrt(cities[i]["population"])
    pick = _spread_pick if protocol else _pick
    for _ in range(city_requested):
        index = pick(rng, cities, weights, [c["pixel"] for _, c in chosen], min_separation) if cities else None
        if index is None:
            break
        chosen.append((SOURCE_CITY, cities[index]))
        weights[index] = 0.0

    points = [_point(source, c) for source, c in chosen]

    # Where each point is aimed: where the map draws it, except for a mismatched pair.
    aimed = [np.array(p["drawnPixel"]) for p in points]
    bad = None
    if rng.random() < options.bad_probability:
        sift_indices = [i for i, p in enumerate(points) if p["source"] == SOURCE_SIFT]
        for i in rng.permutation(sift_indices):
            i = int(i)
            moved = _mismatch(rng, aimed[i], curves[points[i]["feature"]], options)
            if moved is None:
                continue
            displacement = float(np.hypot(*(moved[0] - aimed[i])))
            aimed[i] = moved[0]
            points[i]["bad"] = BAD_SIFT_MISMATCH
            bad = {
                "kind": BAD_SIFT_MISMATCH,
                "index": i,
                "alongPx": round(moved[1], 2),
                "displacementPx": round(displacement, 2),
            }
            break

    for p, target in zip(points, aimed):
        clicked = target + rng.normal(0.0, noise, size=2)
        p["pixel"] = (float(clicked[0]), float(clicked[1]))

    params = {
        "family": family,
        "siftRequested": sift_requested,
        "cityRequested": city_requested,
        "count": len(points),
        "siftCount": sum(p["source"] == SOURCE_SIFT for p in points),
        "cityCount": sum(p["source"] == SOURCE_CITY for p in points),
        "centrePx": [round(float(v), 2) for v in centre],
        "centreSiftIndex": centre_index,
        "radiusRatio": radius_ratio,
        "radiusRatioUsed": radius / diagonal,
        "noisePx": noise,
        "bad": bad,
    }
    return Layout(params=params, points=points)


def draw_check_points(
    rng: np.random.Generator,
    warp: Warp,
    sift: List[Dict[str, Any]],
    cities: List[Dict[str, Any]],
    layout: Layout,
    zones: BaseGeometry,
) -> List[Dict[str, Any]]:
    """The points the user clicked to check the result, not to fit it: placed
    as the real protocol asks (``CHECK_*``), clicked as carefully as the
    layout's control points. SIFT check points lie on the coast and most
    cities inland, as on the real cases."""
    controls = np.array([p["truePixel"] for p in layout.points])
    gaps = np.hypot(controls[:, None, 0] - controls[None, :, 0], controls[:, None, 1] - controls[None, :, 1])
    np.fill_diagonal(gaps, np.inf)
    min_gap = CHECK_GAP_RATIO * float(np.median(gaps.min(axis=1)))
    hull = MultiPoint([tuple(c) for c in controls]).convex_hull
    w, h = warp.image_size
    diagonal = float(np.hypot(w, h))
    area = zones.buffer(CHECK_ZONE_MARGIN_RATIO * diagonal)
    used = {(p["lon"], p["lat"]) for p in layout.points}

    chosen: List[Tuple[str, Dict[str, Any]]] = []
    outside = 0
    for source, candidates, count in ((SOURCE_SIFT, sift, CHECK_SIFT), (SOURCE_CITY, cities, CHECK_CITY)):
        pool = [
            c for c in candidates
            if (c["lon"], c["lat"]) not in used
            and float(np.hypot(*(controls - np.array(c["pixel"])).T).min()) >= min_gap
            and area.covers(Point(*c["pixel"]))
        ]
        if not pool:
            continue
        # Uniform among the SIFT suggestions, the biggest names first among cities.
        weights = np.array([math.sqrt(c["population"]) if source == SOURCE_CITY else 1.0 for c in pool])
        outside_hull = np.array([not hull.covers(Point(*c["pixel"])) for c in pool])
        for _ in range(count):
            if outside >= CHECK_OUTSIDE_HULL:
                weights[outside_hull] = 0.0
            index = _pick(rng, pool, weights, [c["pixel"] for _, c in chosen], MIN_POINT_SEPARATION_RATIO * diagonal)
            if index is None:
                break
            chosen.append((source, pool[index]))
            weights[index] = 0.0
            outside += int(outside_hull[index])

    noise = layout.params["noisePx"]
    points = [_point(source, c) for source, c in chosen]
    for p in points:
        clicked = np.array(p["drawnPixel"]) + rng.normal(0.0, noise, size=2)
        p["pixel"] = (float(clicked[0]), float(clicked[1]))
    return points
