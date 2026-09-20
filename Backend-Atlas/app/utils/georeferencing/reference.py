"""Reference layers for a framing box: rasters, distance transform, samples.

Given the world area the user framed, produce and cache everything the reference
side of alignment needs:

    coastline raster    ne_coastline.geojson
    lakes raster        ne_50m_lakes.geojson              (shorelines)
    rivers raster       ne_50m_rivers_lake_centerlines.geojson
    land raster         the polygonize + ocean-seed flood fill, rasterized
    distance transform  distance in pixels to the nearest reference curve
    signed distance     the same, signed by land/water, plus its gradient

**Why rivers.** Coastline constrains only the boundary of the landmass, so
anywhere inland the warp is weakly determined. Rivers supply interior structure,
and historical boundaries frequently *follow* them (St. Lawrence, Ottawa,
Richelieu). They also add orientation diversity: a regional coast often runs in
one dominant direction, leaving the perpendicular poorly constrained.

**Resolution is not a precision constraint here.** At a ~2500 km framing box a
1024-px-wide raster is ~2.5 km/px, two orders of magnitude below the expected
accuracy floor. Matching the `find_coastline_keypoints` defaults is deliberate;
do not over-spend.

**Two deliberate departures from `sift_key_points_finder.draw_coastline`**, which
plan section 6 suggested promoting verbatim:

1. *It drops out-of-bounds vertices instead of clipping.* A line that leaves the
   framing box and re-enters it loses the crossing vertices, so `cv2.polylines`
   joins the two surviving runs with a straight segment that exists nowhere on
   Earth. Harmless when you only want SIFT corner responses off the render; ruin
   for a distance transform, which would treat that phantom edge as real
   geography. Here the geometry is clipped with shapely first.
2. *It draws a 3 px antialiased stroke.* That widens the curve and flattens the
   distance field near it. These rasters are 1 px and hard-edged.

`sift_key_points_finder` keeps its own copy on purpose: rasterizing differently
would move the keypoints suggested to users, and that path has no test coverage
to catch a regression.
"""

import json
import logging
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np
import shapely
from scipy.ndimage import distance_transform_edt
from shapely.geometry import LineString, MultiLineString, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.utils.coastline_land_mask import (
    load_land_mask_from_coastline_and_ocean_points,
)

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import FrameBounds

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON_DIR = os.path.join(BASE_DIR, "..", "geojson")

COASTLINE_FILE = "ne_coastline.geojson"
LAKES_FILE = "ne_50m_lakes.geojson"
RIVERS_FILE = "ne_50m_rivers_lake_centerlines.geojson"

# Mean Earth radius, for turning degrees into a rough ground scale.
R_EARTH_KM = 6371.0


# --------------------------------------------------------------------------
# Grid
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferenceGrid:
    """Linear mapping between lon/lat and raster pixels over a framing box.

    Matches the existing convention exactly:
        px = (lon - west) / (east - west) * width
        py = (north - lat) / (north - south) * height
    """

    west: float
    south: float
    east: float
    north: float
    width: int
    height: int

    @classmethod
    def from_bounds(
        cls, bounds: FrameBounds, width: int, height: int
    ) -> "ReferenceGrid":
        return cls(
            west=float(bounds["west"]),
            south=float(bounds["south"]),
            east=float(bounds["east"]),
            north=float(bounds["north"]),
            width=int(width),
            height=int(height),
        )

    @property
    def wraps_antimeridian(self) -> bool:
        """A box drawn across the date line has its west edge east of its east."""
        return self.west > self.east

    @property
    def east_unwrapped(self) -> float:
        return self.east + 360.0 if self.wraps_antimeridian else self.east

    @property
    def lon_span(self) -> float:
        return self.east_unwrapped - self.west

    @property
    def lat_span(self) -> float:
        return self.north - self.south

    @property
    def center_lat(self) -> float:
        return (self.north + self.south) / 2.0

    @property
    def km_per_pixel(self) -> float:
        """Rough ground scale at the box centre, for reporting only."""
        lat_km = math.radians(self.lat_span) * R_EARTH_KM / max(self.height, 1)
        lon_km = (
            math.radians(self.lon_span)
            * R_EARTH_KM
            * math.cos(math.radians(self.center_lat))
            / max(self.width, 1)
        )
        return (lat_km + lon_km) / 2.0

    def to_pixel(self, lon, lat) -> Tuple[np.ndarray, np.ndarray]:
        lon_arr = np.asarray(lon, dtype=float)
        lat_arr = np.asarray(lat, dtype=float)
        if self.wraps_antimeridian:
            lon_arr = np.where(lon_arr < self.west, lon_arr + 360.0, lon_arr)
        px = (lon_arr - self.west) / self.lon_span * self.width
        py = (self.north - lat_arr) / self.lat_span * self.height
        return px, py

    def to_lonlat(self, px, py) -> Tuple[np.ndarray, np.ndarray]:
        px_arr = np.asarray(px, dtype=float)
        py_arr = np.asarray(py, dtype=float)
        lon = self.west + px_arr / self.width * self.lon_span
        lat = self.north - py_arr / self.height * self.lat_span
        lon = np.where(lon > 180.0, lon - 360.0, lon)
        return lon, lat

    def clip_boxes(self) -> List[Tuple[BaseGeometry, float]]:
        """Boxes to clip source geometry against, with the lon shift each needs.

        One box normally. A box spanning the date line needs two, because source
        longitudes are in [-180, 180]: the eastern part is clipped as-is and the
        western part is shifted by +360 into the unwrapped frame.
        """
        if not self.wraps_antimeridian:
            return [(box(self.west, self.south, self.east, self.north), 0.0)]
        return [
            (box(self.west, self.south, 180.0, self.north), 0.0),
            (box(-180.0, self.south, self.east, self.north), 360.0),
        ]


# --------------------------------------------------------------------------
# Source geometry, cached on (path, mtime)
# --------------------------------------------------------------------------


def _layer_path(filename: str) -> str:
    return os.path.join(GEOJSON_DIR, filename)


def _mtime_or_none(path: str) -> Optional[float]:
    try:
        return float(os.path.getmtime(path))
    except OSError:
        return None


@lru_cache(maxsize=8)
def _load_linework_cached(path: str, mtime: float) -> Optional[BaseGeometry]:
    """Union every feature of a layer down to linework.

    Polygons contribute their boundary: a lake shoreline is a closed curve and
    is exactly the interior anchor we want, but its filled interior is not a
    curve and must not be rasterized as one.
    """
    _ = mtime  # in the signature so the cache invalidates when the file changes

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read reference layer {path}: {e}")
        return None

    parts: List[BaseGeometry] = []
    for feature in data.get("features", []):
        geom_data = feature.get("geometry")
        if not geom_data:
            continue
        try:
            geom = shape(geom_data)
        except Exception:
            continue
        if geom is None or geom.is_empty:
            continue
        if geom.geom_type in ("Polygon", "MultiPolygon"):
            geom = geom.boundary
        if geom is None or geom.is_empty:
            continue
        parts.append(geom)

    if not parts:
        logger.warning(f"Reference layer has no usable geometry: {path}")
        return None

    return unary_union(parts)


def load_reference_linework(filename: str) -> Optional[BaseGeometry]:
    path = _layer_path(filename)
    mtime = _mtime_or_none(path)
    if mtime is None:
        logger.warning(f"Reference layer not found: {path}")
        return None
    return _load_linework_cached(path, mtime)


# --------------------------------------------------------------------------
# Rasterization
# --------------------------------------------------------------------------


def _iter_linestrings(geom: Optional[BaseGeometry]) -> Iterator[LineString]:
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, LineString):
        yield geom
    elif isinstance(geom, MultiLineString):
        for part in geom.geoms:
            yield part
    elif hasattr(geom, "geoms"):
        for part in geom.geoms:
            yield from _iter_linestrings(part)


def _draw_polyline(canvas: np.ndarray, px: np.ndarray, py: np.ndarray) -> None:
    """Mark the pixels a polyline passes through. 1 px wide, no antialiasing.

    Each segment is sampled at roughly one sample per pixel of its longer axis,
    which is enough to leave no gaps on an 8-connected line.
    """
    if px.size < 2:
        return

    height, width = canvas.shape
    x0, x1 = px[:-1], px[1:]
    y0, y1 = py[:-1], py[1:]

    steps = np.maximum(np.abs(x1 - x0), np.abs(y1 - y0))
    steps = np.ceil(np.nan_to_num(steps, nan=0.0)).astype(int) + 1

    for i in range(steps.size):
        n = int(steps[i])
        xs = np.linspace(x0[i], x1[i], n)
        ys = np.linspace(y0[i], y1[i], n)
        cols = np.clip(np.rint(xs), 0, width - 1).astype(int)
        rows = np.clip(np.rint(ys), 0, height - 1).astype(int)
        canvas[rows, cols] = True


def rasterize_layer(grid: ReferenceGrid, geom: Optional[BaseGeometry]) -> np.ndarray:
    """Rasterize linework, clipped to the framing box, into a boolean raster."""
    canvas = np.zeros((grid.height, grid.width), dtype=bool)
    if geom is None or geom.is_empty:
        return canvas

    for clip_box, lon_shift in grid.clip_boxes():
        try:
            clipped = geom.intersection(clip_box)
        except Exception as e:
            logger.warning(f"Failed to clip reference layer to framing box: {e}")
            continue
        if clipped.is_empty:
            continue

        for line in _iter_linestrings(clipped):
            coords = np.asarray(line.coords, dtype=float)
            if coords.shape[0] < 2:
                continue
            px, py = grid.to_pixel(coords[:, 0] + lon_shift, coords[:, 1])
            _draw_polyline(canvas, px, py)

    return canvas


def rasterize_land_mask(grid: ReferenceGrid) -> np.ndarray:
    """Rasterize the land/water mask: True where a pixel centre is on land.

    The mask is built once as a vector geometry by the polygonize + ocean-seed
    flood fill, then clipped to the framing box before testing so the point-in-
    polygon work is proportional to the region, not to the whole world.
    """
    land = np.zeros((grid.height, grid.width), dtype=bool)

    land_geom = load_land_mask_from_coastline_and_ocean_points()
    if land_geom is None:
        logger.warning("Land/ocean mask unavailable; land raster will be empty.")
        return land

    # Pixel centres, not corners: a pixel is land if its middle is.
    cols = np.arange(grid.width, dtype=float) + 0.5
    rows = np.arange(grid.height, dtype=float) + 0.5
    px, py = np.meshgrid(cols, rows)
    lon, lat = grid.to_lonlat(px, py)

    # `to_lonlat` already wraps its output back into [-180, 180], and the clip
    # boxes are in that same source frame, so no unwrap shift is needed here --
    # unlike rasterize_layer, which goes the other way.
    for clip_box, _lon_shift in grid.clip_boxes():
        try:
            clipped = land_geom.intersection(clip_box)
        except Exception as e:
            logger.warning(f"Failed to clip land mask to framing box: {e}")
            continue
        if clipped.is_empty:
            continue

        shapely.prepare(clipped)
        land |= shapely.contains_xy(clipped, lon, lat)

    return land


# --------------------------------------------------------------------------
# The bundle
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferenceLayers:
    """Every reference raster for one framing box, plus derived fields."""

    grid: ReferenceGrid
    coastline: np.ndarray
    lakes: np.ndarray
    rivers: np.ndarray
    land: np.ndarray
    curves: np.ndarray
    distance_px: np.ndarray
    signed_distance_px: np.ndarray
    gradient_y: np.ndarray
    gradient_x: np.ndarray
    layer_versions: Dict[str, Optional[float]] = field(default_factory=dict)

    @property
    def has_curves(self) -> bool:
        return bool(self.curves.any())

    def coverage(self) -> Dict[str, float]:
        """Fraction of the raster each layer occupies. Cheap sanity signal: a
        framing box with almost no coastline in it is a known failure cause."""
        total = float(self.grid.width * self.grid.height) or 1.0
        return {
            "coastline": float(self.coastline.sum()) / total,
            "lakes": float(self.lakes.sum()) / total,
            "rivers": float(self.rivers.sum()) / total,
            "curves": float(self.curves.sum()) / total,
            "land": float(self.land.sum()) / total,
        }

    def sample_curve_points(
        self, spacing_px: float = 2.0, max_points: Optional[int] = 20000
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Reference curve points in lon/lat, for the chamfer term of Step 4.

        Samples the rasterized curves rather than the source vertices, so the
        density is uniform in *image* space instead of following whatever vertex
        spacing Natural Earth happened to use.
        """
        rows, cols = np.nonzero(self.curves)
        if rows.size == 0:
            return np.zeros(0), np.zeros(0)

        if spacing_px > 1.0:
            # Thin by keeping one point per spacing_px cell.
            cell = max(int(round(spacing_px)), 1)
            keys = (rows // cell).astype(np.int64) * (
                self.grid.width // cell + 1
            ) + (cols // cell)
            _, keep = np.unique(keys, return_index=True)
            rows, cols = rows[keep], cols[keep]

        if max_points is not None and rows.size > max_points:
            step = int(np.ceil(rows.size / max_points))
            rows, cols = rows[::step], cols[::step]

        return self.grid.to_lonlat(cols + 0.5, rows + 0.5)


def _derive_distance_fields(
    curves: np.ndarray, coastline: np.ndarray, land: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Distance to the curves, signed distance to the coast, and its gradient.

    `distance_transform_edt` measures, for every nonzero element, the distance to
    the nearest zero one -- hence the inversion: curve pixels become the zeros
    everything else is measured against.
    """
    if curves.any():
        distance_px = distance_transform_edt(~curves).astype(np.float32)
    else:
        distance_px = np.full(curves.shape, np.inf, dtype=np.float32)

    # Signed against the coastline specifically: lakes and rivers sit *inside*
    # land, so signing against every curve would carve meaningless sign flips
    # through the interior.
    if coastline.any():
        coast_distance = distance_transform_edt(~coastline).astype(np.float32)
    else:
        coast_distance = np.full(coastline.shape, np.inf, dtype=np.float32)

    signed = np.where(land, coast_distance, -coast_distance).astype(np.float32)

    if np.isfinite(signed).all():
        gradient_y, gradient_x = np.gradient(signed)
    else:
        gradient_y = np.zeros_like(signed)
        gradient_x = np.zeros_like(signed)

    return (
        distance_px,
        signed,
        gradient_y.astype(np.float32),
        gradient_x.astype(np.float32),
    )


@lru_cache(maxsize=4)
def _build_reference_layers_cached(
    west: float,
    south: float,
    east: float,
    north: float,
    width: int,
    height: int,
    coastline_mtime: Optional[float],
    lakes_mtime: Optional[float],
    rivers_mtime: Optional[float],
) -> ReferenceLayers:
    # The mtimes are in the signature purely so editing a layer file invalidates
    # the cache, the same pattern the land mask and coastline loaders use.
    grid = ReferenceGrid(
        west=west, south=south, east=east, north=north, width=width, height=height
    )

    coastline = rasterize_layer(grid, load_reference_linework(COASTLINE_FILE))
    lakes = rasterize_layer(grid, load_reference_linework(LAKES_FILE))
    rivers = rasterize_layer(grid, load_reference_linework(RIVERS_FILE))
    land = rasterize_land_mask(grid)

    curves = coastline | lakes | rivers
    distance_px, signed, gradient_y, gradient_x = _derive_distance_fields(
        curves, coastline, land
    )

    return ReferenceLayers(
        grid=grid,
        coastline=coastline,
        lakes=lakes,
        rivers=rivers,
        land=land,
        curves=curves,
        distance_px=distance_px,
        signed_distance_px=signed,
        gradient_y=gradient_y,
        gradient_x=gradient_x,
        layer_versions={
            COASTLINE_FILE: coastline_mtime,
            LAKES_FILE: lakes_mtime,
            RIVERS_FILE: rivers_mtime,
        },
    )


def build_reference_layers(
    bounds: FrameBounds,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> ReferenceLayers:
    """Build (or reuse) every reference layer for *bounds*.

    Cached on the framing box, the raster size and the mtime of each source
    file, so repeated runs over the same region cost nothing.

    Raises:
        ValueError: if *bounds* is missing or degenerate.
    """
    if not bounds:
        raise ValueError("A framing box is required to build reference layers")

    grid_width = int(width or config.reference_raster_width)
    grid_height = int(height or config.reference_raster_height)
    if grid_width < 2 or grid_height < 2:
        raise ValueError("Reference raster must be at least 2x2")

    west = float(bounds["west"])
    south = float(bounds["south"])
    east = float(bounds["east"])
    north = float(bounds["north"])
    if north <= south:
        raise ValueError("Framing box north must be above south")
    if west == east:
        raise ValueError("Framing box has zero longitude span")

    return _build_reference_layers_cached(
        west,
        south,
        east,
        north,
        grid_width,
        grid_height,
        _mtime_or_none(_layer_path(COASTLINE_FILE)),
        _mtime_or_none(_layer_path(LAKES_FILE)),
        _mtime_or_none(_layer_path(RIVERS_FILE)),
    )


# --------------------------------------------------------------------------
# Debug output
# --------------------------------------------------------------------------


def dump_reference_debug_pngs(layers: ReferenceLayers, out_dir: str) -> List[str]:
    """Write one PNG per layer. Visually verifiable, no pipeline change.

    Uses matplotlib rather than cv2 so this module never needs the image stack.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []

    def _save(name: str, data: np.ndarray, cmap: str) -> None:
        path = os.path.join(out_dir, f"{name}.png")
        finite = np.where(np.isfinite(data), data, np.nan)
        plt.imsave(path, finite, cmap=cmap)
        written.append(path)

    _save("coastline", layers.coastline.astype(np.uint8), "gray")
    _save("lakes", layers.lakes.astype(np.uint8), "gray")
    _save("rivers", layers.rivers.astype(np.uint8), "gray")
    _save("land", layers.land.astype(np.uint8), "gray")
    _save("curves", layers.curves.astype(np.uint8), "gray")
    _save("distance_px", layers.distance_px, "magma")
    _save("signed_distance_px", layers.signed_distance_px, "coolwarm")

    # One composite that shows whether the layers actually agree with each other,
    # which is the thing a per-layer dump cannot show.
    rgb = np.zeros((layers.grid.height, layers.grid.width, 3), dtype=np.uint8)
    rgb[layers.land] = (40, 48, 40)
    rgb[layers.rivers] = (80, 140, 255)
    rgb[layers.lakes] = (120, 200, 255)
    rgb[layers.coastline] = (255, 240, 120)
    composite_path = os.path.join(out_dir, "composite.png")
    plt.imsave(composite_path, rgb)
    written.append(composite_path)

    return written
