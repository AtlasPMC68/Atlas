"""How a map draws its coast: generalisation (georeferencing-synthetic.md §3.2).

A drawn coast is never the reference coast: small features are simplified away,
tiny islands dropped, and capes and bays drawn a few pixels off, irregularly
along the coast. The warp W stays the truth (where the cartographer meant each
place); generalisation changes only what is drawn of the coast: the land fill,
the coastline, the zones' coastal edges, and where a user finds a coastal
feature. The interior is untouched, so the coast and the interior disagree, as
they do on real maps (georeferencing-synthetic.md §10.2).
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from .warps import SmoothField

#: RMS displacement of the drawn coast, px. A pen's error on a scan, so in
#: pixels rather than as a share of the map: 0.5 mm at 300 dpi is 6 px.
AMPLITUDE_PX = (1.0, 5.0)
#: How far along the coast the displacement stays the same: the spacing of its
#: kernels, as a share of the image diagonal. Short against the spacing of the
#: control points, so an interpolator between them cannot follow it.
SPACING_RATIO = (0.02, 0.05)
#: Douglas-Peucker tolerance, px: what is too small to draw.
TOLERANCE_PX = (0.5, 2.5)
#: Polygons smaller than a disc of this many tolerances in radius are dropped.
MIN_ISLAND_TOLERANCES = 3.0
#: The coast is densified to this before moving, so it bends with the field.
STEP_PX = 2.0


@dataclass(frozen=True)
class Generalisation:
    field: SmoothField
    amplitude_px: float
    spacing_px: float
    tolerance_px: float

    @property
    def reach_px(self) -> float:
        """How far the drawn coast can be from the true one."""
        return 3.0 * self.amplitude_px + self.tolerance_px + 2.0

    @property
    def snap_px(self) -> float:
        """How far a moved coast point can be from the drawn line: what the
        simplification removes. Further, the feature is not drawn."""
        return 2.0 * self.tolerance_px + 2.0

    def move(self, q: np.ndarray) -> np.ndarray:
        q = np.asarray(q, dtype=float).reshape(-1, 2)
        return q + self.field.displacement(q)

    def land(self, land_px: BaseGeometry) -> BaseGeometry:
        """The land fill as drawn: its outline moved, simplified, and the
        polygons too small to draw dropped."""
        if land_px.is_empty:
            return land_px
        moved = shapely.transform(shapely.segmentize(land_px, STEP_PX), self.move)
        drawn = shapely.make_valid(moved).simplify(self.tolerance_px, preserve_topology=True)
        min_area = math.pi * (MIN_ISLAND_TOLERANCES * self.tolerance_px) ** 2
        parts = [p for p in _polygons(drawn) if p.area >= min_area]
        return shapely.union_all(parts) if parts else shapely.Polygon()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "amplitudePx": round(self.amplitude_px, 3),
            "spacingPx": round(self.spacing_px, 2),
            "tolerancePx": round(self.tolerance_px, 3),
        }


def draw_generalisation(rng: np.random.Generator, image_size: Tuple[int, int]) -> Generalisation:
    diagonal = float(np.hypot(*image_size))
    amplitude = float(rng.uniform(*AMPLITUDE_PX))
    spacing = float(rng.uniform(*SPACING_RATIO)) * diagonal
    tolerance = float(rng.uniform(*TOLERANCE_PX))
    return Generalisation(_kernel_field(rng, image_size, spacing, amplitude), amplitude, spacing, tolerance)


def _kernel_field(rng: np.random.Generator, image_size: Tuple[int, int], spacing: float, rms_px: float) -> SmoothField:
    """Gaussian kernels every *spacing* px, scaled to *rms_px* over the image.
    The grid runs one spacing beyond the image, so the edges move too."""
    w, h = image_size
    diagonal = float(np.hypot(w, h))
    xs = np.arange(-spacing, w + spacing + 1e-9, spacing)
    ys = np.arange(-spacing, h + spacing + 1e-9, spacing)
    gx, gy = np.meshgrid(xs, ys)
    centres = np.column_stack((gx.ravel(), gy.ravel()))
    weights = rng.normal(0.0, 1.0, size=centres.shape)
    unit = SmoothField(centres, weights, spacing / math.sqrt(2.0), rms_px / diagonal)
    sx, sy = np.meshgrid(np.linspace(0, w, 48), np.linspace(0, h, 48))
    d = unit.displacement(np.column_stack((sx.ravel(), sy.ravel())))
    rms = float(np.sqrt(np.mean(np.sum(d * d, axis=1))))
    return SmoothField(centres, weights * (rms_px / rms), unit.radius, unit.rms_ratio)


def drawn_zone_geometries(
    zones_px: Sequence[BaseGeometry], true_land: BaseGeometry, drawn_land: BaseGeometry, reach_px: float
) -> List[BaseGeometry]:
    """Each zone's pixels as the map draws them: grown into what was sea, up
    to how far the coast moved, then cut to the drawn land. Largest first, so
    where two zones grow into the same strip the larger keeps it."""
    order = sorted(range(len(zones_px)), key=lambda i: -zones_px[i].area)
    out: List[BaseGeometry] = [shapely.Polygon()] * len(zones_px)
    claimed: BaseGeometry = shapely.Polygon()
    for i in order:
        zone = zones_px[i]
        grown = zone.union(zone.buffer(reach_px).difference(true_land))
        drawn = shapely.make_valid(grown.intersection(drawn_land)).difference(claimed)
        out[i] = shapely.union_all(_polygons(drawn)) if not drawn.is_empty else drawn
        claimed = claimed.union(out[i])
    return out


def drawn_feature_pixels(coastline: BaseGeometry, pixels: np.ndarray, generalisation: Generalisation) -> np.ndarray:
    """Where the drawn coast shows the features at *pixels* (on the true
    coast): moved with the coast, then onto the drawn line."""
    moved = generalisation.move(pixels)
    if coastline.is_empty:
        return moved
    lines = shapely.shortest_line(coastline, shapely.points(moved))
    return np.array([line.coords[0] for line in lines])


def _polygons(geom: BaseGeometry) -> List[Any]:
    return [p for p in shapely.get_parts(shapely.get_parts(geom)) if p.geom_type == "Polygon"]
