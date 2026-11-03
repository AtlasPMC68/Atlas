"""Vector layers -> the image the pipeline sees (georeferencing-synthetic.md §3.1, §3.3), and an
overview to look at."""

import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import shapely
from shapely.geometry import LineString, box
from shapely.geometry.base import BaseGeometry
from skimage.color import deltaE_ciede2000, rgb2lab

from app.utils.georeferencing.reference import COASTLINE_FILE, load_reference_linework

from .generalise import Generalisation
from .regions import LandLayers, Zone, degrees_per_pixel, image_rect, to_pixels
from .warps import Warp

RGB = Tuple[int, int, int]

#: Sub-pixel precision of OpenCV drawing: coordinates in 1/16 px.
SHIFT_BITS = 4
_SCALE = 1 << SHIFT_BITS

SEA_COLOURS: Tuple[RGB, ...] = (
    (166, 206, 227),
    (190, 220, 238),
    (205, 228, 240),
    (244, 241, 230),
)
#: The first far enough from the sea is used; the last is the one that clears
#: the off-white sea.
LAND_COLOURS: Tuple[RGB, ...] = ((236, 226, 198), (214, 206, 186), (210, 196, 150))
#: Distinguishable zone colours (ColorBrewer Set3). Any within MIN_SEA_DELTA_E
#: of the sea colour is left out for that map.
ZONE_PALETTE: Tuple[RGB, ...] = (
    (141, 211, 199),
    (255, 255, 179),
    (190, 186, 218),
    (251, 128, 114),
    (128, 177, 211),
    (253, 180, 98),
    (179, 222, 105),
    (252, 205, 229),
    (217, 217, 217),
    (188, 128, 189),
    (204, 235, 197),
    (255, 237, 111),
)
#: The water mask is built by colour (ΔE2000 <= ``water_delta_e``, 12): a zone
#: painted close to the sea would be read as water.
MIN_SEA_DELTA_E = 15.0

BORDER_RGB: RGB = (90, 90, 90)
COAST_RGB: RGB = (40, 40, 60)
GRATICULE_RGB: RGB = (120, 120, 140)
FRAME_RGB: RGB = (30, 30, 30)

#: How the coast is drawn (georeferencing-synthetic.md §3.1, §10.2). A coast
#: line with ``COAST_LINE_PROBABILITY``, ``COAST_WIDTH_PX`` wide (uniform, 3-4
#: as on scanned maps), its colour from the sea's (contrast 0) to
#: ``COAST_RGB`` (1): a faint line shows one flank only, as on real maps
#: (east asia). The zones outlined along the coast too with
#: ``COAST_OUTLINE_PROBABILITY``, otherwise between zones only. Neither (30%
#: of maps): the coast is a plain colour change (italie).
COAST_LINE_PROBABILITY = 0.5
COAST_WIDTH_PX = (1, 4)
COAST_CONTRAST = (0.1, 1.0)
COAST_OUTLINE_PROBABILITY = 0.4
FRAME_PROBABILITY = 0.7
GRATICULE_PROBABILITY = 0.5
FRAME_INSET_RATIO = 0.015
#: (largest longitude span, graticule step), both in degrees.
GRATICULE_STEPS = ((8.0, 1.0), (16.0, 2.0), (40.0, 5.0), (float("inf"), 10.0))
#: Zones closer than this (px) count as neighbours and get different colours.
NEIGHBOUR_PX = 2.0
#: A zone outline within this distance (px) of the drawn coastline is coast.
COAST_SHARE_TOLERANCE_PX = 2.0


@dataclass(frozen=True)
class RenderStyle:
    sea: RGB
    land: RGB
    #: 0: no coast line.
    coast_width: int
    coast_contrast: float
    coast_outline: bool
    frame: bool
    graticule_step: Optional[float]

    @property
    def coast_rgb(self) -> RGB:
        t = self.coast_contrast
        return tuple(int(round(s + t * (c - s))) for s, c in zip(self.sea, COAST_RGB))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sea": list(self.sea),
            "land": list(self.land),
            "coastWidth": self.coast_width,
            "coastContrast": round(self.coast_contrast, 3),
            "coastOutline": self.coast_outline,
            "frame": self.frame,
            "graticuleStepDeg": self.graticule_step,
        }


def delta_e(a: RGB, b: RGB) -> float:
    lab = rgb2lab(np.array([[a, b]], dtype=np.float64) / 255.0)
    return float(deltaE_ciede2000(lab[0, 0], lab[0, 1]))


def draw_style(rng: np.random.Generator, lon_span: float) -> RenderStyle:
    sea = SEA_COLOURS[int(rng.integers(len(SEA_COLOURS)))]
    land = next(c for c in LAND_COLOURS if delta_e(c, sea) >= MIN_SEA_DELTA_E)
    graticule = None
    if rng.random() < GRATICULE_PROBABILITY:
        graticule = next(step for limit, step in GRATICULE_STEPS if lon_span <= limit)
    line = bool(rng.random() < COAST_LINE_PROBABILITY)
    width = int(rng.integers(COAST_WIDTH_PX[0], COAST_WIDTH_PX[1] + 1))
    return RenderStyle(
        sea=sea,
        land=land,
        coast_width=width if line else 0,
        coast_contrast=float(rng.uniform(*COAST_CONTRAST)),
        coast_outline=bool(rng.random() < COAST_OUTLINE_PROBABILITY),
        frame=bool(rng.random() < FRAME_PROBABILITY),
        graticule_step=graticule,
    )


def assign_colours(zones: Sequence[Zone], sea: RGB, rng: np.random.Generator) -> List[RGB]:
    """Greedy colouring, largest zone first: touching zones differ, none is
    close to the sea. Each zone takes the least used colour its neighbours do
    not have, so colours repeat only once the palette is used up, and then
    between zones that do not touch."""
    palette = [c for c in ZONE_PALETTE if delta_e(c, sea) >= MIN_SEA_DELTA_E]
    start = int(rng.integers(len(palette)))
    palette = palette[start:] + palette[:start]

    order = sorted(range(len(zones)), key=lambda i: -zones[i].drawn.area)
    grown = [z.drawn.buffer(NEIGHBOUR_PX / 2.0) for z in zones]
    colours: Dict[int, RGB] = {}
    for i in order:
        taken = {colours[j] for j in colours if grown[i].intersects(grown[j])}
        free = [c for c in palette if c not in taken] or palette
        uses = [sum(1 for v in colours.values() if v == c) for c in free]
        colours[i] = free[int(np.argmin(uses))]
    return [colours[i] for i in range(len(zones))]


# --------------------------------------------------------------------------
# Drawing primitives (BGR images, pixel geometries)
# --------------------------------------------------------------------------


def _bgr(rgb: RGB) -> Tuple[int, int, int]:
    return (int(rgb[2]), int(rgb[1]), int(rgb[0]))


def _ring(coords: Any) -> np.ndarray:
    return np.round(np.asarray(coords, dtype=float)[:, :2] * _SCALE).astype(np.int32)


def _polygons(geom: BaseGeometry) -> List[Any]:
    return [g for g in shapely.get_parts(geom) if g.geom_type == "Polygon" and not g.is_empty]


def fill(image: np.ndarray, geom: BaseGeometry, colour: Any) -> None:
    """Fill polygons, holes included (OpenCV fills several contours even-odd)."""
    for poly in _polygons(geom):
        rings = [_ring(poly.exterior.coords)] + [_ring(r.coords) for r in poly.interiors]
        cv2.fillPoly(image, rings, colour, lineType=cv2.LINE_8, shift=SHIFT_BITS)


def stroke(image: np.ndarray, geom: BaseGeometry, colour: Any, width: int = 1) -> None:
    """Draw lines, or the rings of polygons, anti-aliased."""
    lines = []
    for part in shapely.get_parts(geom):
        if part.is_empty:
            continue
        if part.geom_type == "Polygon":
            lines.append(_ring(part.exterior.coords))
            lines.extend(_ring(r.coords) for r in part.interiors)
        elif part.geom_type == "LineString":
            lines.append(_ring(part.coords))
        elif part.geom_type in ("MultiLineString", "MultiPolygon", "GeometryCollection"):
            stroke(image, part, colour, width)
    if lines:
        cv2.polylines(image, lines, False, colour, width, lineType=cv2.LINE_AA, shift=SHIFT_BITS)


def fill_mask(geom: BaseGeometry, image_size: Tuple[int, int]) -> np.ndarray:
    mask = np.zeros((image_size[1], image_size[0]), dtype=np.uint8)
    fill(mask, geom, 255)
    return mask.astype(bool)


# --------------------------------------------------------------------------
# The map
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DrawnLayers:
    """What is drawn, in pixels. Kept apart from the true geometry the metric
    uses (georeferencing-synthetic.md §3.2): coastline generalisation changes
    the land fill and the coastline only."""

    land_with_lakes: BaseGeometry
    lakes: BaseGeometry
    coastline: BaseGeometry
    graticule: Optional[BaseGeometry]
    #: Land minus lakes through the warp, before generalisation (None when the
    #: coast is not generalised): not drawn, but what the zones' coastal edges
    #: are recut from.
    true_land: Optional[BaseGeometry] = None

    def ocean_mask(self, image_size: Tuple[int, int]) -> np.ndarray:
        return ~fill_mask(self.land_with_lakes, image_size)

    def land_mask(self, image_size: Tuple[int, int]) -> np.ndarray:
        """Land minus lakes."""
        return fill_mask(self.land_with_lakes, image_size) & ~fill_mask(self.lakes, image_size)


def _graticule(region: BaseGeometry, step: float) -> BaseGeometry:
    west, south, east, north = region.bounds
    lines = []
    for lon in np.arange(np.ceil(west / step) * step, east + 1e-9, step):
        lines.append(LineString([(lon, south), (lon, north)]))
    for lat in np.arange(np.ceil(south / step) * step, north + 1e-9, step):
        lines.append(LineString([(west, lat), (east, lat)]))
    return shapely.MultiLineString(lines) if lines else shapely.MultiLineString()


def drawn_layers(
    warp: Warp,
    region: BaseGeometry,
    land: LandLayers,
    graticule_step: Optional[float],
    generalisation: Optional[Generalisation] = None,
) -> DrawnLayers:
    """The reference layers in view, pushed through the warp; the coast
    generalised when *generalisation* is given."""
    dpp = degrees_per_pixel(region, warp.image_size)
    window = region.buffer(max(region.bounds[2] - region.bounds[0], region.bounds[3] - region.bounds[1]) * 0.05)
    bounds = window.bounds
    step = dpp * 1.5
    rect = image_rect(warp.image_size).buffer(4)

    def warped(geom: BaseGeometry, clip: bool = True) -> BaseGeometry:
        clipped = shapely.make_valid(shapely.clip_by_rect(geom, *bounds)).intersection(window)
        pixels = to_pixels(clipped.simplify(dpp / 4.0), warp, step)
        return pixels.intersection(rect) if clip else pixels

    graticule = warped(_graticule(window, graticule_step)) if graticule_step else None
    lakes = warped(land.lakes)
    if generalisation is None:
        coastline = load_reference_linework(COASTLINE_FILE)
        return DrawnLayers(
            land_with_lakes=warped(land.land_with_lakes),
            lakes=lakes,
            coastline=warped(coastline),
            graticule=graticule,
        )
    # Generalised before the image clip: the window's own edges, outside the
    # image, move instead of the image border. The coastline is the drawn
    # land's outline, so the line and the fill always agree.
    true_fill = warped(land.land_with_lakes, clip=False)
    drawn_fill = generalisation.land(true_fill)
    return DrawnLayers(
        land_with_lakes=drawn_fill.intersection(rect),
        lakes=lakes,
        coastline=drawn_fill.boundary.intersection(rect),
        graticule=graticule,
        true_land=true_fill.intersection(rect).difference(lakes),
    )


def coast_signals(
    layers: DrawnLayers, zones: Sequence[Zone], image_size: Tuple[int, int]
) -> Dict[str, float]:
    """How much coast the map shows: the drawn coastline's length in image
    diagonals, and the share of the zones' outlines that lie on it (the image
    edge left out, since zones are cut there)."""
    rect = image_rect(image_size)
    coast = layers.coastline.intersection(rect)
    outline = shapely.union_all([z.drawn.boundary for z in zones])
    outline = outline.difference(rect.exterior.buffer(1.0))
    on_coast = outline.intersection(coast.buffer(COAST_SHARE_TOLERANCE_PX)).length
    return {
        "coastLengthRatio": round(coast.length / float(np.hypot(*image_size)), 3),
        "zoneCoastShare": round(on_coast / outline.length, 3) if outline.length else 0.0,
    }


def render_map(
    layers: DrawnLayers,
    zones: Sequence[Zone],
    colours: Sequence[RGB],
    style: RenderStyle,
    image_size: Tuple[int, int],
) -> np.ndarray:
    """The map, as a BGR image, in the order of D7."""
    w, h = image_size
    image = np.empty((h, w, 3), dtype=np.uint8)
    image[:] = _bgr(style.sea)
    fill(image, layers.land_with_lakes, _bgr(style.land))
    for zone, colour in zip(zones, colours):
        fill(image, zone.drawn, _bgr(colour))
    fill(image, layers.lakes, _bgr(style.sea))
    outlines = shapely.union_all([z.drawn.boundary for z in zones]) if zones else None
    if outlines is not None and not style.coast_outline:
        outlines = outlines.difference(layers.coastline.buffer(COAST_SHARE_TOLERANCE_PX))
    if outlines is not None:
        stroke(image, outlines, _bgr(BORDER_RGB), 1)
    stroke(image, layers.lakes, _bgr(COAST_RGB), 1)
    if style.coast_width > 0:
        stroke(image, layers.coastline, _bgr(style.coast_rgb), style.coast_width)
    if layers.graticule is not None:
        stroke(image, layers.graticule, _bgr(GRATICULE_RGB), 1)
    if style.frame:
        inset = FRAME_INSET_RATIO * min(w, h)
        stroke(image, box(inset, inset, w - 1 - inset, h - 1 - inset), _bgr(FRAME_RGB), 2)
    return image


# --------------------------------------------------------------------------
# The overview: for looking at a map, never given to the pipeline
# --------------------------------------------------------------------------


def render_overview(
    image: np.ndarray,
    zones: Sequence[Zone],
    sift: Sequence[Dict[str, Any]],
    cities: Sequence[Dict[str, Any]],
    header: Sequence[str],
    max_cities: int = 40,
) -> np.ndarray:
    """The map with zone names, every SIFT candidate (green ring) and the
    largest cities (magenta dot) at their true position, under a header."""
    out = image.copy()
    h, w = out.shape[:2]
    font_scale = max(0.4, min(w, h) / 1600.0)
    thickness = max(1, int(round(font_scale * 2)))

    for zone in zones:
        largest = max(_polygons(zone.drawn), key=lambda p: p.area)
        x, y = largest.representative_point().coords[0]
        _label(out, zone.name, (x, y), font_scale, thickness, (0, 0, 0))

    radius = max(6, int(min(w, h) / 120))
    for kp in sift:
        x, y = kp["pixel"]
        cv2.circle(out, (int(round(x)), int(round(y))), radius, (0, 160, 0), 2, cv2.LINE_AA)
    for city in sorted(cities, key=lambda c: -c["population"])[:max_cities]:
        x, y = city["pixel"]
        cv2.circle(out, (int(round(x)), int(round(y))), max(3, radius // 2), (200, 0, 200), -1, cv2.LINE_AA)
        _label(out, city["name"], (x + radius, y), font_scale * 0.7, 1, (120, 0, 120))

    line_h = int(28 * font_scale) + 8
    band = np.full((line_h * len(header) + 8, w, 3), 255, dtype=np.uint8)
    for i, text in enumerate(header):
        cv2.putText(band, text, (8, (i + 1) * line_h), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
    return np.vstack((band, out))


def _label(image: np.ndarray, text: str, xy: Tuple[float, float], scale: float, thickness: int, colour: Tuple[int, int, int]) -> None:
    # OpenCV's Hershey font is ASCII only: drop the accents (French names).
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    org = (int(round(xy[0])), int(round(xy[1])))
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thickness + 2, cv2.LINE_AA)
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, colour, thickness, cv2.LINE_AA)
