"""The zones as colour extraction produced them, before any transform.

A georeferenced zone mixes two errors: the extraction's (holes where labels
sit, bleed across a border) and the transform's (the whole zone in the wrong
place). The dev tool's map only shows the sum. This module shows the first
term alone, on the scan the user clicked, with the OCR boxes drawn over it so
a hole that is really a label reads as one.

Snapshot written by the dev-test task next to ``zones.geojson``; rendered on
demand by the router. Needs cv2, so it is imported lazily there.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

import cv2
import numpy as np
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

logger = logging.getLogger(__name__)

PIXEL_ZONES_FILENAME = "zones_pixel.geojson"
CLASSIFIED_IMAGE_FILENAME = "classified_image.png"

OCR_BOX_COLOR = (255, 0, 255)  # BGR: magenta
HOLE_EDGE_COLOR = (0, 0, 255)  # BGR: red
FILL_ALPHA = 0.55


def write_pixel_zones(case_dir: str, pixel_collections: Sequence[Dict]) -> Optional[str]:
    """Persist the pixel-space zones of a run. Never raises."""
    try:
        features = [f for fc in pixel_collections for f in fc.get("features", [])]
        path = os.path.join(case_dir, PIXEL_ZONES_FILENAME)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {"type": "FeatureCollection", "features": features},
                f,
                ensure_ascii=False,
            )
        return path
    except Exception as e:
        logger.warning(f"[DEV-TEST] Could not write pixel-space zones: {e}")
        return None


def write_classified_image(case_dir: str, rgb: Optional[np.ndarray]) -> None:
    """Persist the image the zones were classified on, or drop a stale one.

    Removed when this run did not inpaint, so the view can never show the
    rebuild of an earlier run next to zones that did not come from it.
    Never raises.
    """
    path = os.path.join(case_dir, CLASSIFIED_IMAGE_FILENAME)
    try:
        if rgb is None:
            if os.path.exists(path):
                os.remove(path)
            return
        rgb_u8 = (np.clip(rgb, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        cv2.imwrite(path, cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2BGR))
    except Exception as e:
        logger.warning(f"[DEV-TEST] Could not write the classified image: {e}")


def load_pixel_zones(case_dir: str) -> Optional[List[Dict]]:
    path = os.path.join(case_dir, PIXEL_ZONES_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [f for f in data.get("features", []) if f and f.get("geometry")]


def _polygons(geometry) -> List[Polygon]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [g for g in getattr(geometry, "geoms", []) if g.geom_type == "Polygon"]


def _ocr_union(text_regions: Optional[Sequence]):
    boxes = []
    for region in text_regions or []:
        try:
            poly = Polygon([(float(p[0]), float(p[1])) for p in region])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                boxes.append(poly)
        except Exception:
            continue
    return unary_union(boxes) if boxes else None


def pixel_zone_stats(
    features: Sequence[Dict], text_regions: Optional[Sequence] = None
) -> List[Dict[str, Any]]:
    """Per zone: its area, its holes, and how much of the holes is text.

    ``holeAreaInTextRatio`` is the number to watch: the share of the hole area
    that falls inside an OCR box. High means the holes are labels the text
    fill did not recover; low means they are something else (a lake, a
    different colour, noise).
    """
    ocr = _ocr_union(text_regions)
    out = []
    for index, feature in enumerate(features):
        props = feature.get("properties") or {}
        try:
            geometry = shape(feature["geometry"])
        except Exception:
            continue
        polygons = _polygons(geometry)
        holes = [Polygon(ring) for poly in polygons for ring in poly.interiors]
        holes = [h if h.is_valid else h.buffer(0) for h in holes]
        hole_union = unary_union(holes) if holes else None
        hole_area = float(hole_union.area) if hole_union is not None else 0.0
        in_text = (
            float(hole_union.intersection(ocr).area)
            if hole_union is not None and ocr is not None
            else None
        )
        # Area of the zone's outline, holes included: the denominator a reader
        # expects when asked "how much of the zone is missing".
        filled_area = float(sum(Polygon(p.exterior).area for p in polygons))
        in_boxes = (
            float(geometry.intersection(ocr).area) if ocr is not None else None
        )
        out.append(
            {
                "index": index,
                "name": props.get("name") or props.get("color_name") or f"zone-{index}",
                "colorHex": props.get("color_hex"),
                "parts": len(polygons),
                "areaPx": round(float(geometry.area)),
                "areaInTextPx": None if in_boxes is None else round(in_boxes),
                "holes": len(holes),
                "holeAreaPx": round(hole_area),
                "holeAreaRatio": round(hole_area / filled_area, 4) if filled_area else 0.0,
                "holeAreaInTextRatio": (
                    round(in_text / hole_area, 4) if in_text is not None and hole_area else None
                ),
            }
        )
    return out


def text_box_coverage(
    features: Sequence[Dict], text_regions: Optional[Sequence] = None
) -> Optional[Dict[str, Any]]:
    """How much of the OCR boxes' area some zone covers.

    The hole count cannot see the text problem: a label's gap nearly always
    reaches the zone's edge through a river or a border, so it is a notch in
    the outline, not a hole. Coverage of the boxes can. Read it against the
    image, though: a box over a lake or the sea *should* stay uncovered, so
    100 % is not the target -- a fill that paints lakes scores higher and is
    worse.
    """
    ocr = _ocr_union(text_regions)
    if ocr is None or ocr.area <= 0:
        return None
    geometries = []
    for feature in features:
        try:
            geometries.append(shape(feature["geometry"]))
        except Exception:
            continue
    covered = unary_union(geometries).intersection(ocr).area if geometries else 0.0
    return {
        "boxAreaPx": round(float(ocr.area)),
        "coveredPx": round(float(covered)),
        "coveredRatio": round(float(covered) / float(ocr.area), 4),
    }


def _to_px(coords, scale: float) -> np.ndarray:
    return np.round(np.asarray(coords, dtype=np.float64)[:, :2] * scale).astype(np.int32)


def draw_pixel_zones(
    image_bgr: np.ndarray,
    features: Sequence[Dict],
    text_regions: Optional[Sequence] = None,
    *,
    blank_background: bool = False,
    caption: str = "",
    min_width: int = 1100,
) -> np.ndarray:
    """The zones filled in their own colour, holes outlined in red, OCR in magenta.

    ``blank_background`` swaps the scan for white, where a hole is a white gap
    rather than a patch of scan that looks like it belongs to the zone.
    """
    height, width = image_bgr.shape[:2]
    scale = max(1.0, min_width / float(width))
    size = (int(round(width * scale)), int(round(height * scale)))

    if blank_background:
        canvas = np.full((size[1], size[0], 3), 255, dtype=np.uint8)
    else:
        canvas = cv2.resize(image_bgr, size, interpolation=cv2.INTER_NEAREST)

    edges: List[tuple] = []
    for feature in features:
        props = feature.get("properties") or {}
        rgb = props.get("color_rgb") or [60, 120, 220]
        bgr = (int(rgb[2]), int(rgb[1]), int(rgb[0]))
        try:
            polygons = _polygons(shape(feature["geometry"]))
        except Exception:
            continue

        mask = np.zeros((size[1], size[0]), dtype=np.uint8)
        for poly in polygons:
            cv2.fillPoly(mask, [_to_px(poly.exterior.coords, scale)], 1)
        for poly in polygons:
            for ring in poly.interiors:
                cv2.fillPoly(mask, [_to_px(ring.coords, scale)], 0)

        region = mask.astype(bool)
        color = np.array(bgr, dtype=np.float32)
        canvas[region] = (
            canvas[region].astype(np.float32) * (1.0 - FILL_ALPHA) + color * FILL_ALPHA
        ).astype(np.uint8)

        darker = tuple(int(c * 0.6) for c in bgr)
        for poly in polygons:
            edges.append((_to_px(poly.exterior.coords, scale), darker, 2))
            for ring in poly.interiors:
                edges.append((_to_px(ring.coords, scale), HOLE_EDGE_COLOR, 1))

    # Outlines after every fill, so one zone's fill never hides another's edge.
    for pts, color, thickness in edges:
        cv2.polylines(canvas, [pts], True, color, thickness, cv2.LINE_AA)

    for region in text_regions or []:
        try:
            pts = _to_px([(float(p[0]), float(p[1])) for p in region], scale)
        except Exception:
            continue
        if len(pts) >= 3:
            cv2.polylines(canvas, [pts], True, OCR_BOX_COLOR, 1, cv2.LINE_AA)

    if caption:
        font = cv2.FONT_HERSHEY_SIMPLEX
        for i, line in enumerate(caption.split("\n")):
            y = 22 + i * 20
            cv2.putText(canvas, line, (10, y), font, 0.5, (255, 255, 255), 3, cv2.LINE_AA)
            cv2.putText(canvas, line, (10, y), font, 0.5, (20, 20, 20), 1, cv2.LINE_AA)

    return canvas
