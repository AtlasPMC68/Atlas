"""Post-hoc vertex snapping of zone boundaries onto the reference coastline."""

import json
import logging
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

import numpy as np
import shapely
from shapely.errors import GEOSException
from shapely.geometry import MultiPolygon, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON_DIR = os.path.join(BASE_DIR, "..", "geojson")


@lru_cache(maxsize=8)
def _load_coastline_geometry_cached(
    coastline_path: str,
    mtime: float,
) -> Optional[BaseGeometry]:
    """Load and union coastline features; cache by path + mtime."""
    # Keep mtime in signature so cache invalidates automatically when file changes.
    _ = mtime

    try:
        with open(coastline_path, "r", encoding="utf-8") as f:
            coastline_data = json.load(f)

        line_geometries: List[BaseGeometry] = []
        for feature in coastline_data.get("features", []):
            geom_data = feature.get("geometry")
            if not geom_data:
                continue
            geom = shape(geom_data)
            if geom and geom.is_valid and not geom.is_empty:
                line_geometries.append(geom)

        if not line_geometries:
            logger.warning("No valid coastline geometries found")
            return None

        return unary_union(line_geometries)

    except Exception as e:
        logger.error(f"Failed to load coastline geometry: {e}", exc_info=True)
        return None


def load_coastline_geometry(
    coastline_file: str = "ne_coastline.geojson",
) -> Optional[BaseGeometry]:
    """Load coastline linework as a single geometry for snapping."""
    coastline_path = os.path.join(GEOJSON_DIR, coastline_file)

    if not os.path.exists(coastline_path):
        logger.warning(f"Coastline file not found: {coastline_path}")
        return None

    try:
        mtime = os.path.getmtime(coastline_path)
    except OSError as e:
        logger.warning(f"Cannot stat coastline file '{coastline_path}': {e}")
        return None

    return _load_coastline_geometry_cached(coastline_path, float(mtime))


def _snap_ring_coords_to_coastline(
    coords: List[Tuple[float, float]],
    coastline_geom,
    snap_tolerance: float,
) -> Tuple[List[Tuple[float, float]], int, int]:
    """Snap ring coordinates to coastline where points are within tolerance."""
    if not coords:
        return coords, 0, 0

    snapped_coords: List[Tuple[float, float]] = []
    total_points = 0
    snapped_points = 0

    for x, y in coords:
        total_points += 1
        p = Point(float(x), float(y))
        distance = p.distance(coastline_geom)

        if distance <= snap_tolerance:
            _, nearest_on_coast = nearest_points(p, coastline_geom)
            snapped_coords.append((float(nearest_on_coast.x), float(nearest_on_coast.y)))
            snapped_points += 1
        else:
            snapped_coords.append((float(x), float(y)))

    # Ensure ring closure remains valid. Note this *forces* closure rather than
    # fixing it: if the first vertex snapped and the last did not, the last is
    # overwritten (georeferencing.md section 9). Left as-is on purpose --
    # changing it moves output, and the snapping stage is due for replacement.
    if snapped_coords and snapped_coords[0] != snapped_coords[-1]:
        snapped_coords[-1] = snapped_coords[0]

    return snapped_coords, total_points, snapped_points


def collect_polygons(candidate_geom: Optional[BaseGeometry]) -> List[Polygon]:
    """Extract only Polygon parts from Polygon/MultiPolygon/collections."""
    if candidate_geom is None or candidate_geom.is_empty:
        return []
    if candidate_geom.geom_type == "Polygon":
        return [candidate_geom]
    if candidate_geom.geom_type == "MultiPolygon":
        return list(candidate_geom.geoms)
    if hasattr(candidate_geom, "geoms"):
        parts: List[Polygon] = []
        for g in candidate_geom.geoms:
            parts.extend(collect_polygons(g))
        return parts
    return []


def snap_geometry_to_coastline(
    geom: Optional[BaseGeometry],
    coastline_geom: Optional[BaseGeometry],
    snap_tolerance: float,
) -> Tuple[Optional[BaseGeometry], int, int]:
    """Snap polygon boundary vertices to coastline and preserve valid geometry."""
    total_points = 0
    snapped_points = 0

    if coastline_geom is None or geom is None or geom.is_empty:
        return geom, total_points, snapped_points

    def snap_polygon(poly: Polygon) -> Tuple[BaseGeometry, int, int]:
        poly_total = 0
        poly_snapped = 0

        ext_coords = list(poly.exterior.coords)
        snapped_ext, t_ext, s_ext = _snap_ring_coords_to_coastline(
            ext_coords, coastline_geom, snap_tolerance
        )
        poly_total += t_ext
        poly_snapped += s_ext

        snapped_interiors = []
        for interior in poly.interiors:
            int_coords = list(interior.coords)
            snapped_int, t_int, s_int = _snap_ring_coords_to_coastline(
                int_coords, coastline_geom, snap_tolerance
            )
            poly_total += t_int
            poly_snapped += s_int
            snapped_interiors.append(snapped_int)

        snapped_poly = Polygon(snapped_ext, snapped_interiors)

        # Keep polygon stable if snapping creates invalid geometry
        if not snapped_poly.is_valid:
            repaired = snapped_poly.buffer(0)
            if repaired.is_valid and not repaired.is_empty:
                snapped_poly = repaired
            else:
                return poly, poly_total, 0

        return snapped_poly, poly_total, poly_snapped

    if geom.geom_type == "Polygon":
        snapped_geom, total_points, snapped_points = snap_polygon(geom)
        return snapped_geom, total_points, snapped_points

    if geom.geom_type == "MultiPolygon":
        snapped_parts = []
        for poly in geom.geoms:
            snapped_geom_part, t, s = snap_polygon(poly)
            total_points += t
            snapped_points += s
            snapped_parts.extend(collect_polygons(snapped_geom_part))

        if not snapped_parts:
            return geom, total_points, 0
        if len(snapped_parts) == 1:
            return snapped_parts[0], total_points, snapped_points
        return MultiPolygon(snapped_parts), total_points, snapped_points

    # Non-polygon geometries are left unchanged
    return geom, total_points, snapped_points


# --- Snapping stretches (config ``coastline_snap_stretches``, §10.8) -----------

#: Points against segments per block of the nearest-segment search.
_NEAREST_BLOCK = 256

#: The precision of the union a failed exact one falls back to, EPSG:3857 m.
SNAP_GRID_M = 0.01


@dataclass(frozen=True)
class CoastIndex:
    """The reference coastline as segments, each knowing its line and place on
    it, so a snapped stretch can follow the coast's own vertices."""

    a: np.ndarray  # (M, 2) segment starts
    b: np.ndarray  # (M, 2) segment ends
    line: np.ndarray  # (M,) the line each segment is on
    index: np.ndarray  # (M,) the segment's place on its line
    vertices: List[np.ndarray]  # each line's vertices, a ring's without the repeat
    along: List[np.ndarray]  # distance along the line at each vertex, then the total
    closed: np.ndarray  # (L,) whether each line is a ring

    @classmethod
    def build(cls, coastline: BaseGeometry) -> "CoastIndex":
        a, b, line, index, vertices, along, closed = [], [], [], [], [], [], []
        for part in shapely.get_parts(coastline):
            if part.geom_type not in ("LineString", "LinearRing") or part.is_empty:
                continue
            xy = np.asarray(part.coords, dtype=float)[:, :2]
            ring = len(xy) > 3 and np.allclose(xy[0], xy[-1])
            v = xy[:-1] if ring else xy
            if len(v) < 2:
                continue
            ends = np.vstack([v[1:], v[:1]]) if ring else v[1:]
            starts = v[: len(ends)]
            k = len(vertices)
            a.append(starts)
            b.append(ends)
            line.append(np.full(len(ends), k))
            index.append(np.arange(len(ends)))
            vertices.append(v)
            along.append(np.concatenate([[0.0], np.cumsum(np.hypot(*(ends - starts).T))]))
            closed.append(ring)
        if not vertices:
            empty = np.zeros((0, 2))
            return cls(empty, empty, np.zeros(0, int), np.zeros(0, int), [], [], np.zeros(0, bool))
        return cls(
            np.vstack(a), np.vstack(b), np.concatenate(line), np.concatenate(index),
            vertices, along, np.array(closed),
        )

    def nearest(self, points: np.ndarray, reach: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """For each point, its nearest point on the coast, the distance to it,
        the segment and the share along it; distance inf and segment -1 where
        no segment is within *reach* of the points' bounding box."""
        n = len(points)
        q = points.copy()
        d = np.full(n, np.inf)
        seg = np.full(n, -1)
        t = np.zeros(n)
        lo, hi = points.min(0) - reach, points.max(0) + reach
        box = (
            (np.minimum(self.a, self.b) <= hi).all(1) & (np.maximum(self.a, self.b) >= lo).all(1)
        )
        cand = np.flatnonzero(box)
        if cand.size == 0:
            return q, d, seg, t
        a, ab = self.a[cand], self.b[cand] - self.a[cand]
        ab2 = np.maximum((ab * ab).sum(1), 1e-18)
        for s in range(0, n, _NEAREST_BLOCK):
            p = points[s : s + _NEAREST_BLOCK, None, :]
            tt = np.clip(((p - a) * ab).sum(2) / ab2, 0.0, 1.0)
            foot = a + tt[..., None] * ab
            dist = np.hypot(*(p - foot).transpose(2, 0, 1))
            k = dist.argmin(1)
            rows = np.arange(len(k))
            q[s : s + _NEAREST_BLOCK] = foot[rows, k]
            d[s : s + _NEAREST_BLOCK] = dist[rows, k]
            seg[s : s + _NEAREST_BLOCK] = cand[k]
            t[s : s + _NEAREST_BLOCK] = tt[rows, k]
        return q, d, seg, t

    def between(self, si: int, ti: float, sj: int, tj: float, limit: float) -> List[Tuple[float, float]]:
        """The coast's vertices from the point *ti* along segment *si* to the
        point *tj* along *sj*, the shorter way along their line; none when
        they are on different lines or that way is longer than *limit*."""
        k = int(self.line[si])
        if int(self.line[sj]) != k:
            return []
        v, L = self.vertices[k], self.along[k]
        m, xi, xj = len(v), int(self.index[si]), int(self.index[sj])
        pi = L[xi] + ti * (L[xi + 1] - L[xi])
        pj = L[xj] + tj * (L[xj + 1] - L[xj])
        total = L[-1]
        ways = []  # (arc length, vertex indices)
        if self.closed[k]:
            ways.append(((pj - pi) % total, [(xi + 1 + c) % m for c in range((xj - xi) % m)]))
            ways.append(((pi - pj) % total, [(xi - c) % m for c in range((xi - xj) % m)]))
        elif pj >= pi:
            ways.append((pj - pi, list(range(xi + 1, xj + 1))))
        else:
            ways.append((pi - pj, list(range(xi, xj, -1))))
        arc, indices = min(ways, key=lambda w: w[0])
        if arc > limit:
            return []
        return [(float(v[c, 0]), float(v[c, 1])) for c in indices]


def _runs(mask: np.ndarray) -> List[np.ndarray]:
    """The runs of True in a ring's *mask*, as vertex indices in ring order; a
    run may wrap past the ring's start. All True is one run of every vertex."""
    n = len(mask)
    if mask.all():
        return [np.arange(n)]
    start = int(np.flatnonzero(~mask)[0])
    order = (start + np.arange(n)) % n
    runs, current = [], []
    for i in order:
        if mask[i]:
            current.append(i)
        elif current:
            runs.append(np.array(current))
            current = []
    if current:
        runs.append(np.array(current))
    return runs


def _snap_ring_stretches(
    coords: List[Tuple[float, ...]],
    coast: CoastIndex,
    tolerance: float,
    min_run: float,
    min_cos: float,
) -> Tuple[List[Tuple[float, float]], int, int]:
    """One ring with its coastal stretches snapped (``snap_geometry_to_coastline_stretches``)."""
    ring = np.asarray(coords, dtype=float)[:, :2]
    if len(ring) > 1 and np.allclose(ring[0], ring[-1]):
        ring = ring[:-1]
    n = len(ring)
    if n < 3:
        return [tuple(map(float, p)) for p in coords], n, 0
    q, d, seg, t = coast.nearest(ring, tolerance)
    near = d <= tolerance
    if not near.any():
        return [tuple(map(float, p)) for p in coords], n, 0

    # How parallel the boundary runs to the coast at each vertex.
    heading = np.roll(ring, -1, 0) - np.roll(ring, 1, 0)
    tangent = np.where(near[:, None], coast.b[seg] - coast.a[seg], 0.0)
    norm = np.hypot(*heading.T) * np.hypot(*tangent.T)
    cos = np.abs((heading * tangent).sum(1)) / np.maximum(norm, 1e-18)
    step = np.hypot(*(np.roll(ring, -1, 0) - ring).T)  # vertex i to i + 1

    whole = near.all()
    snapped = np.zeros(n, dtype=bool)
    for run in _runs(near):
        if not whole:
            # The ends where the boundary turns off the coast stay put.
            lo, hi = 0, len(run)
            while lo < hi and cos[run[lo]] < min_cos:
                lo += 1
            while hi > lo and cos[run[hi - 1]] < min_cos:
                hi -= 1
            run = run[lo:hi]
            if len(run) < 2 or step[run[:-1]].sum() < min_run:
                continue
        snapped[run] = True

    out: List[Tuple[float, float]] = []
    for i in range(n):
        j = (i + 1) % n
        if not snapped[i]:
            out.append((float(ring[i, 0]), float(ring[i, 1])))
            continue
        out.append((float(q[i, 0]), float(q[i, 1])))
        if snapped[j]:
            chord = float(np.hypot(*(q[j] - q[i])))
            out.extend(coast.between(seg[i], t[i], seg[j], t[j], 4.0 * (chord + tolerance)))
    out.append(out[0])
    return out, n, int(snapped.sum())


def snap_geometry_to_coastline_stretches(
    geom: Optional[BaseGeometry],
    coast: Optional[CoastIndex],
    snap_tolerance: float,
    min_run: float,
    max_angle_deg: float,
    max_area_change: float,
) -> Tuple[Optional[BaseGeometry], int, int]:
    """Snap only the stretches of each boundary that run along the coast.

    A stretch is a run of consecutive vertices within *snap_tolerance* of the
    coast, at least *min_run* long once its ends that leave the coast at more
    than *max_angle_deg* are dropped. Its vertices move to their nearest
    points on the coast, with the coast's own vertices between them, so a
    border that only reaches the sea moves at most its end, and a snapped
    shore follows the coast instead of cutting across its bends.

    A polygon whose snap changes more than *max_area_change* of its area is
    left as it was: snapping closes a strip along the shore, and a zone
    narrower than the tolerance would otherwise have every vertex in reach
    and fold onto the coast (§10.8). Counts as ``snap_geometry_to_coastline``."""
    if coast is None or geom is None or geom.is_empty or len(coast.a) == 0:
        return geom, 0, 0
    min_cos = math.cos(math.radians(max_angle_deg))
    total = snapped = 0
    parts: List[Polygon] = []
    for poly in collect_polygons(geom):
        rings, moved = [], 0
        for ring in [poly.exterior, *poly.interiors]:
            coords, t, s = _snap_ring_stretches(list(ring.coords), coast, snap_tolerance, min_run, min_cos)
            total += t
            moved += s
            rings.append(coords)
        out = Polygon(rings[0], rings[1:])
        if not out.is_valid:
            out = shapely.make_valid(out)
        kept = collect_polygons(out)
        try:
            change = (
                shapely.union_all(kept).symmetric_difference(poly).area / poly.area
                if kept and poly.area > 0
                else math.inf
            )
        except GEOSException:
            change = math.inf
        if change > max_area_change:
            parts.append(poly)
            continue
        parts.extend(kept)
        snapped += moved
    if not parts:
        return geom, total, 0
    if len(parts) == 1:
        return parts[0], total, snapped
    # Snapped neighbours of one zone can now overlap. Snapped onto the same
    # coast, their edges can also cross at a hair's angle, which the exact
    # overlay can fail on; rounded to a centimetre it does not.
    try:
        return shapely.union_all(parts), total, snapped
    except GEOSException:
        return shapely.union_all(shapely.make_valid(parts), grid_size=SNAP_GRID_M), total, snapped


def estimate_pixel_extent_from_features(
    pixel_feature_collections: List[dict],
) -> Optional[Tuple[float, float, float, float]]:
    """Bounding box (x0, y0, x1, y1) of every pixel-space feature, or None."""

    minx = float("inf")
    miny = float("inf")
    maxx = float("-inf")
    maxy = float("-inf")
    found_any = False

    for fc in pixel_feature_collections:
        if fc.get("type") != "FeatureCollection":
            continue
        for feat in fc.get("features", []):
            geom_data = feat.get("geometry")
            if not geom_data:
                continue
            try:
                geom = shape(geom_data)
            except Exception:
                continue
            if geom is None or geom.is_empty:
                continue
            gx_min, gy_min, gx_max, gy_max = geom.bounds
            minx = min(minx, gx_min)
            miny = min(miny, gy_min)
            maxx = max(maxx, gx_max)
            maxy = max(maxy, gy_max)
            found_any = True

    if not found_any:
        return None
    return (minx, miny, maxx, maxy)


def estimate_pixel_diagonal_from_features(
    pixel_feature_collections: List[dict],
) -> Optional[float]:
    """Estimate pixel-space diagonal from all feature bounds."""
    
    extent = estimate_pixel_extent_from_features(pixel_feature_collections)
    if extent is None:
        return None

    minx, miny, maxx, maxy = extent
    width_px = max(0.0, maxx - minx)
    height_px = max(0.0, maxy - miny)
    diagonal_px = math.sqrt(width_px * width_px + height_px * height_px)
    if diagonal_px <= 0:
        return None
    return diagonal_px
