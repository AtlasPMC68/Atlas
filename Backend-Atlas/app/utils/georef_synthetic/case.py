"""A synthetic map and what is written for it."""

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from shapely.geometry import Polygon, mapping

from .regions import RegionDraw, Zone
from .user import WATER_PICK_RADIUS_PX, Layout
from .render import RGB, DrawnLayers, RenderStyle, render_overview
from .generalise import Generalisation
from .warps import Warp


@dataclass
class SyntheticMap:
    map_id: str
    seed: int
    #: The twin (``generate.DEFORMATIONS``), or None for the map as drawn.
    deformation: Optional[str]
    generator_version: str
    attempts: int
    rejections: Dict[str, int]
    region: RegionDraw
    warp: Warp
    #: The part of the world the image shows (lon/lat).
    visible: Polygon
    frame_bounds: Dict[str, float]
    zone_level: str
    zones: List[Zone]
    colours: List[RGB]
    style: RenderStyle
    layers: DrawnLayers
    land_fraction: float
    ocean_fraction: float
    #: How much coastline the map shows (``render.coast_signals``).
    coast: Dict[str, float]
    #: BGR, as OpenCV and the pipeline read it.
    image: np.ndarray
    #: Normalised (x, y), or None for a map without ocean (georeferencing-synthetic.md §3.1).
    water_pick: Optional[Tuple[float, float]] = None
    sift_candidates: List[Dict[str, Any]] = field(default_factory=list)
    city_candidates: List[Dict[str, Any]] = field(default_factory=list)
    #: How the coast is drawn, or None for a coast drawn exactly.
    generalisation: Optional[Generalisation] = None
    #: The stress twin only: the strength its draw kept (1 unless it folded
    #: and was softened) and how many softenings that took.
    stress: Optional[Dict[str, float]] = None

    @property
    def image_size(self) -> Tuple[int, int]:
        return self.warp.image_size

    @property
    def km_per_pixel(self) -> float:
        west, south, east, north = self.visible.bounds
        lat = math.radians((south + north) / 2.0)
        return (east - west) * 111.32 * math.cos(lat) / self.image_size[0]

    def to_dict(self) -> Dict[str, Any]:
        w, h = self.image_size
        return {
            "generatorVersion": self.generator_version,
            "mapId": self.map_id,
            "seed": self.seed,
            "deformation": self.deformation,
            "attempts": self.attempts,
            "rejections": self.rejections,
            "region": {
                "centre": list(self.region.centre),
                "lonSpanDeg": self.region.lon_span,
                "aspect": self.region.aspect,
            },
            "imageSize": [w, h],
            "kmPerPixel": round(self.km_per_pixel, 4),
            "visibleBounds": list(self.visible.bounds),
            "frameBounds": self.frame_bounds,
            "warp": self.warp.to_dict(),
            "nonAffineRmsPx": round(self.warp.non_affine_rms_px(), 3),
            "stress": self.stress,
            "style": self.style.to_dict(),
            "coastGeneralisation": self.generalisation.to_dict() if self.generalisation else None,
            "landFraction": round(self.land_fraction, 4),
            "oceanFraction": round(self.ocean_fraction, 4),
            "coast": self.coast,
            "zoneLevel": self.zone_level,
            "zones": [
                {
                    "name": z.name,
                    "country": z.country,
                    "colour": list(c),
                    "imageFraction": round(z.image_fraction(self.image_size), 4),
                }
                for z, c in zip(self.zones, self.colours)
            ],
            "waterPick": list(self.water_pick) if self.water_pick else None,
            "siftCandidates": self.sift_candidates,
            "cityCandidates": self.city_candidates,
        }

    def overview_header(self) -> List[str]:
        w, h = self.image_size
        f = self.frame_bounds
        lon, lat = self.region.centre
        rejected = ", ".join(f"{k} x{v}" for k, v in sorted(self.rejections.items())) or "none"
        return [
            f"{self.map_id}  {w}x{h} px  {self.km_per_pixel:.2f} km/px  "
            f"{self.zone_level}: {len(self.zones)} zones  "
            f"coast {self.coast['coastLengthRatio']:.1f} diag, {self.coast['zoneCoastShare']:.0%} of zone outlines",
            f"warp: {' + '.join(self.warp.families)}",
            f"centre {lat:.2f}, {lon:.2f}  span {self.region.lon_span:.1f} deg  "
            f"frame W{f['west']:.1f} S{f['south']:.1f} E{f['east']:.1f} N{f['north']:.1f}",
            f"SIFT candidates {len(self.sift_candidates)}  cities {len(self.city_candidates)}  "
            f"rejected draws: {rejected}",
        ]

    def write(self, directory: str) -> None:
        os.makedirs(directory, exist_ok=True)
        cv2.imwrite(os.path.join(directory, "image.png"), self.image)
        overview = render_overview(
            self.image, self.zones, self.sift_candidates, self.city_candidates, self.overview_header()
        )
        cv2.imwrite(os.path.join(directory, "overview.png"), overview)
        _write_json(os.path.join(directory, "map.json"), self.to_dict())
        _write_json(os.path.join(directory, "zones_true.geojson"), _collection(self.zones, pixels=False))
        _write_json(os.path.join(directory, "zones_pixel.geojson"), _collection(self.zones, pixels=True))


@dataclass
class SyntheticCase:
    """One control-point layout on a map: what a run is given."""

    map: SyntheticMap
    layout_index: int
    layout: Layout

    @property
    def case_id(self) -> str:
        return f"{self.map.map_id}-l{self.layout_index:02d}"

    def pixel_zones(self) -> List[Dict[str, Any]]:
        """The zones in pixels, one collection each, as colour extraction hands them over."""
        return [
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": z.name, "mapElementType": "zone"},
                        "geometry": mapping(z.drawn),
                    }
                ],
            }
            for z in self.map.zones
        ]

    def water_picks(self) -> Tuple[Any, Any, Any]:
        """The ``Picks`` triple ``place_map`` takes."""
        if self.map.water_pick is None:
            return None, None, None
        return [self.map.water_pick], [None], [WATER_PICK_RADIUS_PX]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generatorVersion": self.map.generator_version,
            "caseId": self.case_id,
            "mapId": self.map.map_id,
            "layoutIndex": self.layout_index,
            "layout": self.layout.params,
            "controlPoints": self.layout.points,
            "checkPoints": self.layout.check_points,
        }

    def write(self, directory: str) -> None:
        os.makedirs(directory, exist_ok=True)
        _write_json(os.path.join(directory, "case.json"), self.to_dict())
        cv2.imwrite(os.path.join(directory, "control_points.png"), self._control_points_image())

    def _control_points_image(self) -> np.ndarray:
        """Green ring: where the point is drawn; red cross: where it was
        clicked; the line between them is the click error. The bad point in
        magenta; check points in orange."""
        image = self.map.image.copy()
        size = max(6, int(min(self.map.image_size) / 120))
        checks = [(p, (0, 140, 255)) for p in self.layout.check_points]
        for p, colour in [(p, (200, 0, 200) if p["bad"] else (0, 0, 220)) for p in self.layout.points] + checks:
            tx, ty = (int(round(v)) for v in p["truePixel"])
            cx, cy = (int(round(v)) for v in p["pixel"])
            cv2.circle(image, (tx, ty), size, (0, 160, 0), 2, cv2.LINE_AA)
            cv2.line(image, (tx, ty), (cx, cy), colour, 1, cv2.LINE_AA)
            cv2.drawMarker(image, (cx, cy), colour, cv2.MARKER_CROSS, size * 2, 2, cv2.LINE_AA)
        return image


def _collection(zones: Sequence[Zone], pixels: bool) -> Dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"name": z.name, "country": z.country},
                "geometry": mapping(z.drawn if pixels else z.geometry),
            }
            for z in zones
        ],
    }


def _write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
