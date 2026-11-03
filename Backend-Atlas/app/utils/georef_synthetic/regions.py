"""Where a synthetic map is, what it shows, and which zones it has
(georeferencing-synthetic.md §3.1, §3.3)."""

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import shapely
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from app.utils import borders
from app.utils.coastline_land_mask import load_land_mask_from_coastline_and_ocean_points
from app.utils.georeferencing.reference import (
    COASTLINE_FILE,
    LAKES_FILE,
    load_reference_linework,
    load_reference_polygons,
)

from .warps import Warp

BBox = Tuple[float, float, float, float]  # west, south, east, north

CENTRE_LAT_RANGE = (-60.0, 72.0)
#: Log-uniform: from a regional map to a continent (median ~21 deg). The real
#: corpus spans ~20-50 deg; 4-40 made most maps look zoomed in.
LON_SPAN_DEG = (5.0, 90.0)
ASPECT = (0.6, 1.6)  # height / width
#: The real corpus goes down to 602 px (Quebec_1791).
LONG_SIDE_PX = (500, 2000)

#: A zone is kept from this share of the image: ~37 x 37 px on a 1400 px map,
#: still pickable. At 1%, a map of East Asia lost Japan and Korea.
MIN_ZONE_FRACTION = 0.001
#: Countries are the zones when at least MIN_ZONES of them cover this share
#: each; otherwise provinces.
COUNTRY_LEVEL_MIN_FRACTION = 0.01
MIN_ZONES = 2
#: A country's provinces are used as they are when the ones big enough to be
#: zones cover at least this share of its land in view; otherwise its groups.
MIN_PROVINCE_COVERAGE = 0.5
MAX_ABS_LAT = 84.0

#: The user's framing box encloses the map: the visible region's bounding box,
#: padded on each side by this share of its span.
FRAME_PADDING = (0.05, 0.10)

#: Zones are extended this far into the sea before being cut to land. The
#: borders are Natural Earth 10m and the coastline 50m: cut to land alone, a
#: zone would leave land slivers along the coast that belong to no zone.
ZONE_SEA_EXTENSION_DEG = 0.05

BORDER_POINTS_PER_SIDE = 64

LEVEL_COUNTRIES = "countries"
LEVEL_PROVINCES = "provinces"


class Rejected(Exception):
    """This draw cannot make a map; the reason is recorded and another is drawn."""


# --------------------------------------------------------------------------
# Reference geometry, loaded once per process
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _coastline_segments() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Every coastline segment as (starts, ends, cumulative ground length)."""
    starts, ends = [], []
    for line in shapely.get_parts(load_reference_linework(COASTLINE_FILE)):
        coords = np.asarray(line.coords, dtype=float)
        if coords.shape[0] >= 2:
            starts.append(coords[:-1])
            ends.append(coords[1:])
    a, b = np.vstack(starts), np.vstack(ends)
    mid_lat = np.radians((a[:, 1] + b[:, 1]) / 2.0)
    length = np.hypot((b[:, 0] - a[:, 0]) * np.cos(mid_lat), b[:, 1] - a[:, 1])
    return a, b, np.cumsum(length)


@dataclass(frozen=True)
class LandLayers:
    #: Not ocean: what the land fill covers, lakes included.
    land_with_lakes: BaseGeometry
    lakes: BaseGeometry
    #: Land minus lakes: what zones are cut to (the pipeline's own mask).
    land: BaseGeometry


@lru_cache(maxsize=1)
def land_layers() -> LandLayers:
    land_with_lakes = load_land_mask_from_coastline_and_ocean_points()
    lakes = load_reference_polygons(LAKES_FILE)
    if land_with_lakes is None or lakes is None:
        raise RuntimeError("The land mask or the lakes could not be loaded")
    land = land_with_lakes.difference(lakes)
    for geom in (land_with_lakes, lakes, land):
        shapely.prepare(geom)
    return LandLayers(land_with_lakes, lakes, land)


# --------------------------------------------------------------------------
# The region
# --------------------------------------------------------------------------


def draw_coast_point(rng: np.random.Generator) -> Tuple[float, float]:
    """A point on the coastline, uniform by ground length, inside the latitude range."""
    starts, ends, cumulative = _coastline_segments()
    while True:
        i = int(np.searchsorted(cumulative, rng.uniform(0.0, cumulative[-1])))
        t = float(rng.random())
        lon, lat = starts[i] + t * (ends[i] - starts[i])
        if CENTRE_LAT_RANGE[0] <= lat <= CENTRE_LAT_RANGE[1]:
            return float(lon), float(lat)


@dataclass(frozen=True)
class RegionDraw:
    centre: Tuple[float, float]
    lon_span: float
    aspect: float
    image_size: Tuple[int, int]

    @property
    def lat_span(self) -> float:
        """Approximate: the height of the region in degrees at its centre."""
        return self.lon_span * self.aspect * math.cos(math.radians(self.centre[1]))


def draw_region(rng: np.random.Generator) -> RegionDraw:
    centre = draw_coast_point(rng)
    lon_span = float(math.exp(rng.uniform(math.log(LON_SPAN_DEG[0]), math.log(LON_SPAN_DEG[1]))))
    aspect = float(rng.uniform(*ASPECT))
    long_side = int(rng.integers(LONG_SIDE_PX[0], LONG_SIDE_PX[1] + 1))
    if aspect <= 1.0:
        size = (long_side, max(1, round(long_side * aspect)))
    else:
        size = (max(1, round(long_side / aspect)), long_side)
    return RegionDraw(centre, lon_span, aspect, size)


def image_rect(image_size: Tuple[int, int]) -> Polygon:
    """The image in pixel coordinates (pixel centres at integers)."""
    w, h = image_size
    return box(-0.5, -0.5, w - 0.5, h - 0.5)


def visible_region(warp: Warp) -> Polygon:
    """The part of the world the image shows: W^-1 of the image rectangle."""
    w, h = warp.image_size
    t = np.linspace(0.0, 1.0, BORDER_POINTS_PER_SIDE, endpoint=False)
    x0, y0, x1, y1 = -0.5, -0.5, w - 0.5, h - 0.5
    px = np.concatenate((x0 + t * (x1 - x0), np.full_like(t, x1), x1 - t * (x1 - x0), np.full_like(t, x0)))
    py = np.concatenate((np.full_like(t, y0), y0 + t * (y1 - y0), np.full_like(t, y1), y1 - t * (y1 - y0)))
    lon, lat = warp.inverse(px, py)
    if not (np.all(np.isfinite(lon)) and np.all(np.isfinite(lat))):
        raise Rejected("warp not invertible on the image border")
    if np.any(np.abs(lat) > MAX_ABS_LAT):
        raise Rejected("too close to a pole")
    if np.any(lon < -180.0) or np.any(lon > 180.0):
        raise Rejected("crosses the antimeridian")
    region = shapely.make_valid(Polygon(np.column_stack((lon, lat))))
    if region.geom_type != "Polygon":
        raise Rejected("visible region is not one polygon")
    return region


def frame_bounds(region: Polygon, rng: np.random.Generator) -> Dict[str, float]:
    west, south, east, north = region.bounds
    lon_span, lat_span = east - west, north - south
    pad = rng.uniform(*FRAME_PADDING, size=4)
    return {
        "west": max(-180.0, west - pad[0] * lon_span),
        "south": max(-MAX_ABS_LAT, south - pad[1] * lat_span),
        "east": min(180.0, east + pad[2] * lon_span),
        "north": min(MAX_ABS_LAT, north + pad[3] * lat_span),
    }


def degrees_per_pixel(region: Polygon, image_size: Tuple[int, int]) -> float:
    """The finer of the two axes' scales, for densifying and simplifying."""
    west, south, east, north = region.bounds
    return min((east - west) / image_size[0], (north - south) / image_size[1])


def to_pixels(geom: BaseGeometry, warp: Warp, step_deg: float) -> BaseGeometry:
    """Push lon/lat geometry through the warp, densified first so it bends."""
    if geom.is_empty:
        return geom
    # A smooth one-to-one warp keeps a polygon valid in exact arithmetic; in
    # floating point two nearly touching rings can cross, so repair.
    return shapely.make_valid(shapely.transform(shapely.segmentize(geom, step_deg), warp.forward_xy))


# --------------------------------------------------------------------------
# Zones
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """An administrative unit: a country, or a province (with its group)."""

    name: str
    country: str
    group: Optional[str]
    geometry: BaseGeometry


#: (level, bbox, countries or None) -> the units of that level intersecting bbox.
UnitSource = Callable[[str, BBox, Optional[Sequence[str]]], List[Unit]]


@lru_cache(maxsize=2)
def _border_tree(level: str, _files: Tuple) -> Tuple[Tuple[Unit, ...], shapely.STRtree]:
    units: List[Unit] = []
    for code, country in sorted(borders.index().items()):
        if level == LEVEL_COUNTRIES:
            if country.wkb is not None:
                units.append(Unit(country.name, code, None, shapely.from_wkb(country.wkb)))
        else:
            for region_id, region in sorted(country.regions.items()):
                units.append(Unit(region.name, code, region.group, shapely.from_wkb(region.wkb)))
    return tuple(units), shapely.STRtree([u.geometry for u in units])


def border_units(level: str, bbox: BBox, countries: Optional[Sequence[str]] = None) -> List[Unit]:
    """Units from the ``borders/`` files (Natural Earth admin-0 and admin-1)."""
    units, tree = _border_tree(level, borders.border_files())
    hits = sorted(int(i) for i in tree.query(box(*bbox)))
    wanted = set(countries) if countries is not None else None
    return [units[i] for i in hits if wanted is None or units[i].country in wanted]


def _merge_groups(units: Sequence[Unit]) -> List[Unit]:
    """Provinces merged by their group where the file has one (Italy's 20 regions)."""
    grouped: Dict[Tuple[str, str], List[Unit]] = {}
    for unit in units:
        key = (unit.country, unit.group or f"\0{unit.name}")
        grouped.setdefault(key, []).append(unit)
    merged = []
    for (country, _key), members in sorted(grouped.items()):
        name = members[0].group or members[0].name
        geometry = shapely.union_all([m.geometry for m in members])
        merged.append(Unit(name, country, members[0].group, geometry))
    return merged


def _provinces_or_groups(
    provinces: Sequence[Unit], region: Polygon, warp: Warp, land: BaseGeometry
) -> List[Unit]:
    """Per country, its provinces, or their groups when the provinces are too
    small to make zones: France's 101 departements become its 18 regions, while
    Canada keeps its provinces (its groups lump Nunavut, the Northwest
    Territories and the Yukon into one)."""
    by_country: Dict[str, List[Unit]] = {}
    for unit in provinces:
        by_country.setdefault(unit.country, []).append(unit)
    chosen: List[Unit] = []
    for country, members in sorted(by_country.items()):
        if any(m.group for m in members):
            zones = _build_zones(members, region, warp, land)
            total = sum(z.pixel_geometry.area for z in zones)
            big = sum(
                z.pixel_geometry.area
                for z in zones
                if z.image_fraction(warp.image_size) >= MIN_ZONE_FRACTION
            )
            if total > 0 and big / total < MIN_PROVINCE_COVERAGE:
                members = _merge_groups(members)
        chosen.extend(members)
    return chosen


@dataclass(frozen=True)
class Zone:
    name: str
    country: str
    #: Lon/lat (EPSG:4326): the truth.
    geometry: BaseGeometry
    #: The truth through the warp, in pixels, clipped to the image.
    pixel_geometry: BaseGeometry
    #: As the map draws it, when the coast is generalised: its coastal edges
    #: follow the drawn coast. What is rendered and handed to the pipeline.
    drawn_geometry: Optional[BaseGeometry] = None

    @property
    def drawn(self) -> BaseGeometry:
        return self.pixel_geometry if self.drawn_geometry is None else self.drawn_geometry

    def image_fraction(self, image_size: Tuple[int, int]) -> float:
        return self.pixel_geometry.area / float(image_size[0] * image_size[1])


def _build_zones(
    units: Sequence[Unit], region: Polygon, warp: Warp, land: BaseGeometry
) -> List[Zone]:
    """Each unit cut to the visible region and to land, extended into the sea
    first so it fills its land up to the drawn coast."""
    dpp = degrees_per_pixel(region, warp.image_size)
    window = region.buffer(ZONE_SEA_EXTENSION_DEG * 2)
    clipped = []
    for unit in units:
        # clip_by_rect first: a country at 10m is hundreds of thousands of
        # vertices, and the window is a small part of it.
        geom = shapely.make_valid(shapely.clip_by_rect(unit.geometry, *window.bounds))
        geom = geom.intersection(window)
        if not geom.is_empty:
            clipped.append((unit, geom.simplify(dpp / 2.0)))
    if not clipped:
        return []

    occupied = shapely.union_all([g for _, g in clipped])
    land_here = shapely.make_valid(shapely.clip_by_rect(land, *window.bounds)).intersection(window)
    rect = image_rect(warp.image_size)
    claimed = shapely.Polygon()
    zones = []
    for unit, geom in sorted(clipped, key=lambda ug: -ug[1].area):
        extended = geom.union(geom.buffer(ZONE_SEA_EXTENSION_DEG).difference(occupied))
        extended = extended.difference(claimed)
        claimed = claimed.union(extended)
        truth = _polygonal(extended.intersection(land_here).intersection(region))
        if truth.is_empty:
            continue
        pixels = _polygonal(to_pixels(truth, warp, dpp * 1.5).intersection(rect))
        if pixels.is_empty:
            continue
        zones.append(Zone(unit.name, unit.country, truth, pixels))
    return zones


def _polygonal(geom: BaseGeometry) -> BaseGeometry:
    """Only the polygons of *geom* (intersections can leave lines and points)."""
    geom = shapely.make_valid(geom)
    parts = [
        p for p in shapely.get_parts(shapely.get_parts(geom)) if p.geom_type == "Polygon"
    ]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def _unique_names(zones: List[Zone]) -> List[Zone]:
    counts: Dict[str, int] = {}
    for z in zones:
        counts[z.name] = counts.get(z.name, 0) + 1
    out, seen = [], {}
    for z in zones:
        name = z.name if counts[z.name] == 1 else f"{z.name} ({z.country})"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name} {seen[name]}"
        out.append(Zone(name, z.country, z.geometry, z.pixel_geometry))
    return out


def choose_zones(
    region: Polygon, warp: Warp, units: UnitSource = border_units
) -> Tuple[str, List[Zone]]:
    """Countries when at least 2 cover 1% of the image, otherwise the provinces
    of the countries in view. Either way, zones from 0.1% of the image."""
    land = land_layers().land
    bbox: BBox = region.bounds

    countries = units(LEVEL_COUNTRIES, bbox, None)
    zones = _build_zones(countries, region, warp, land)
    fractions = [z.image_fraction(warp.image_size) for z in zones]
    if sum(f >= COUNTRY_LEVEL_MIN_FRACTION for f in fractions) >= MIN_ZONES:
        return LEVEL_COUNTRIES, _unique_names(
            [z for z, f in zip(zones, fractions) if f >= MIN_ZONE_FRACTION]
        )

    in_view = sorted({u.country for u in countries})
    provinces = _provinces_or_groups(units(LEVEL_PROVINCES, bbox, in_view), region, warp, land)
    zones = _build_zones(provinces, region, warp, land)
    big = [z for z in zones if z.image_fraction(warp.image_size) >= MIN_ZONE_FRACTION]
    if len(big) >= MIN_ZONES:
        return LEVEL_PROVINCES, _unique_names(big)
    raise Rejected("fewer than 2 zones")
