"""User-side evidence: what the scanned map itself offers to align against."""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from skimage.color import deltaE_ciede2000, rgb2lab

from app.utils.color_sampling import sample_color_at
from app.utils.legend import LegendBounds, legend_mask as build_legend_mask

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig

logger = logging.getLogger(__name__)

# A polygon per OCR region, each a list of [x, y] points -- the shape
# `extract_text` produces and `filter_text_overlapping_contours` consumes.
TextRegions = Sequence[Sequence[Sequence[float]]]


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------


def build_text_mask(
    shape_hw: Tuple[int, int],
    text_regions: Optional[TextRegions],
    dilation_px: int,
) -> np.ndarray:
    """Mask of the OCR regions, dilated outwards."""

    mask = np.zeros(shape_hw, dtype=np.uint8)
    if not text_regions:
        return mask.astype(bool)

    for region in text_regions:
        try:
            points = np.array(
                [[int(round(float(p[0]))), int(round(float(p[1])))] for p in region],
                dtype=np.int32,
            )
        except (TypeError, ValueError, IndexError):
            continue
        if points.shape[0] >= 3:
            cv2.fillPoly(mask, [points], 255)

    if dilation_px > 0:
        # Scale with the image: 7 px on a 1700 px scan is a hairline, but on a
        # 520 px one it is three times as much of the picture. Keyed off the
        # diagonal so it means the same thing at any resolution.
        diagonal = float(np.hypot(shape_hw[0], shape_hw[1]))
        scaled = max(1, int(round(dilation_px * diagonal / 2200.0)))
        size = 2 * scaled + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        mask = cv2.dilate(mask, kernel)

    return mask.astype(bool)


# --------------------------------------------------------------------------
# Edges
# --------------------------------------------------------------------------


def blurred_gray(
    image_bgr: np.ndarray,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> np.ndarray:
    """The grey image Canny runs on."""
    if image_bgr.ndim == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_bgr

    ksize = int(config.edge_blur_ksize) | 1  # Gaussian kernels must be odd
    return cv2.GaussianBlur(gray, (ksize, ksize), 0)


def build_edge_map(
    image_bgr: np.ndarray,
    text_mask: Optional[np.ndarray] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> np.ndarray:
    """Canny edges of the user's map, with text regions removed."""
    blurred = blurred_gray(image_bgr, config)
    edges = cv2.Canny(blurred, config.edge_canny_low, config.edge_canny_high) > 0

    if text_mask is not None and text_mask.any():
        edges = edges & ~text_mask
    
    return edges


def detect_straight_lines(
    edges: np.ndarray,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> List[Tuple[int, int, int, int]]:
    """Long straight segments in the edge map, as (x1, y1, x2, y2)."""

    height, width = edges.shape
    diagonal = float(np.hypot(width, height))
    min_length = max(int(diagonal * config.straight_line_min_length_ratio), 20)

    found = cv2.HoughLinesP(
        edges.astype(np.uint8) * 255,
        rho=1,
        theta=np.pi / 180.0,
        threshold=int(config.straight_line_hough_threshold),
        minLineLength=min_length,
        maxLineGap=int(config.straight_line_max_gap_px),
    )
    return normalize_hough_output(found)


def normalize_hough_output(found: Any) -> List[Tuple[int, int, int, int]]:
    """Flatten whatever `HoughLinesP` returned into a list of 4-tuples."""

    if found is None:
        return []
    array = np.asarray(found)
    if array.size == 0:
        return []
    array = array.reshape(-1, 4)
    return [(int(x1), int(y1), int(x2), int(y2)) for x1, y1, x2, y2 in array]


def suppress_straight_lines(
    edges: np.ndarray,
    lines: Sequence[Tuple[int, int, int, int]],
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> np.ndarray:
    """Turn the binary edge map into a weight map, down-weighting straight runs."""

    weight = edges.astype(np.float32)
    if not lines:
        return weight

    stroke = np.zeros(edges.shape, dtype=np.uint8)
    thickness = max(int(config.straight_line_thickness_px), 1)
    for x1, y1, x2, y2 in lines:
        cv2.line(stroke, (x1, y1), (x2, y2), 255, thickness)

    under_line = stroke.astype(bool) & edges
    weight[under_line] = float(config.straight_line_weight)
    return weight


# --------------------------------------------------------------------------
# Water
# --------------------------------------------------------------------------


def build_water_mask(
    image_rgb: np.ndarray,
    water_click_positions: Optional[Sequence[Sequence[float]]],
    water_sampling_radii: Optional[Sequence[int]] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> np.ndarray:
    """Pixels close in colour to any water pick."""
    
    height, width = image_rgb.shape[:2]
    water = np.zeros((height, width), dtype=bool)
    if not water_click_positions:
        return water

    centers: List[List[float]] = []
    for idx, position in enumerate(water_click_positions):
        try:
            nx, ny = float(position[0]), float(position[1])
        except (TypeError, ValueError, IndexError):
            continue
        radius = 20
        if water_sampling_radii is not None and idx < len(water_sampling_radii):
            try:
                radius = int(water_sampling_radii[idx])
            except (TypeError, ValueError):
                radius = 20
        sampled = sample_color_at(image_rgb, nx, ny, radius_px=radius)
        if sampled and sampled.get("lab") is not None:
            centers.append(list(sampled["lab"]))

    if not centers:
        logger.warning("Water picks provided but none could be sampled")
        return water

    lab = rgb2lab(image_rgb.astype(np.float32) / 255.0)
    for center in centers:
        center_arr = np.array(center, dtype=float).reshape(1, 1, 3)
        water |= deltaE_ciede2000(lab, center_arr) <= config.water_delta_e

    if config.water_morph_radius_px > 0:
        size = 2 * int(config.water_morph_radius_px) + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        cleaned = cv2.morphologyEx(water.astype(np.uint8), cv2.MORPH_OPEN, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)
        water = cleaned.astype(bool)

    return water


def split_ocean_and_lakes(
    water: np.ndarray,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> Tuple[np.ndarray, np.ndarray]:
    """Split a water mask into (ocean, lakes)."""

    ocean = np.zeros_like(water, dtype=bool)
    lakes = np.zeros_like(water, dtype=bool)
    if not water.any():
        return ocean, lakes

    count, labels = cv2.connectedComponents(water.astype(np.uint8), connectivity=8)
    if count <= 1:
        return ocean, lakes

    border_labels = set(labels[0, :]) | set(labels[-1, :])
    border_labels |= set(labels[:, 0]) | set(labels[:, -1])
    border_labels.discard(0)

    sizes = np.bincount(labels.ravel())
    ocean_label = None
    if border_labels:
        ocean_label = max(border_labels, key=lambda lab: sizes[lab])
        ocean = labels == ocean_label

    min_area = int(config.water_min_component_px)
    for label in range(1, count):
        if label == ocean_label:
            continue
        if sizes[label] >= min_area:
            lakes |= labels == label

    return ocean, lakes


def filter_edges_near_water(
    edges: np.ndarray,
    water: np.ndarray,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> Tuple[np.ndarray, bool]:
    """Keep only edges on the water/land boundary."""

    if not config.edge_water_filter:
        return edges, False

    margin = max(int(config.edge_water_margin_px), 0)
    size = 2 * margin + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    water_u8 = water.astype(np.uint8)
    near_water = cv2.dilate(water_u8, kernel).astype(bool)
    near_land = cv2.dilate(1 - water_u8, kernel).astype(bool)
    return edges & near_water & near_land, True


#: Smoothing of the distance field the normals come from, in px.
_NORMAL_SIGMA_PX = 1.5


def _nearest(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """For every pixel, the (y, x) of the nearest pixel of *mask*."""
    _, labels = cv2.distanceTransformWithLabels(
        (~mask).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )
    ys, xs = np.nonzero(mask)
    by_label_y = np.zeros(int(labels.max()) + 1, dtype=np.int64)
    by_label_x = np.zeros_like(by_label_y)
    by_label_y[labels[ys, xs]] = ys
    by_label_x[labels[ys, xs]] = xs
    return by_label_y[labels], by_label_x[labels]


def centre_drawn_coast_lines(
    coast_edges: np.ndarray,
    edges: np.ndarray,
    water: np.ndarray,
    blurred: np.ndarray,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Move the coast evidence from a drawn line's sea-side flank to its centre.

    A coast drawn as a line has two Canny edges, one per flank, and the water
    filter keeps only the sea-side one once the line is wider than its margin,
    while the reference coastline is the line's centre: the fit was pulled
    seaward by about half the line (georeferencing-history.md, 2026-10-27).

    The two flanks of a line have opposite grey gradients along the coast's
    normal (dark line: falling, then rising, going landward). For each edge of
    *coast_edges* (the water filter's output), the nearest edge of *edges*
    with the opposite gradient, if within ``coast_line_max_width_px``, is the
    line's other flank: landward of it, the pair is replaced by its midpoint,
    which is the line's centre whatever the blur or the Canny thresholds;
    seaward of it, the edge is itself a land-side flank (both pass the filter
    when the line is thin) and is dropped, its pair being counted from the sea
    side. An edge with no partner is a coast drawn as a plain colour change,
    already the coast, and is kept as it is.

    Nearest by distance transform rather than by marching along the normal: a
    ray can slip between the diagonal pixels of an edge and miss it.
    """

    stats: Dict[str, Any] = {"coastLinePairedFraction": None, "coastLineMergedFraction": None, "coastLineFlankGapPx": None}
    max_gap = float(config.coast_line_max_width_px)
    if max_gap <= 0 or not coast_edges.any() or not water.any():
        return coast_edges, stats

    water_u8 = water.astype(np.uint8)
    signed = cv2.distanceTransform(1 - water_u8, cv2.DIST_L2, 5) - cv2.distanceTransform(
        water_u8, cv2.DIST_L2, 5
    )
    signed = cv2.GaussianBlur(signed, (0, 0), _NORMAL_SIGMA_PX)
    ny_field, nx_field = np.gradient(signed)
    grey = blurred.astype(np.float32)
    # The grey gradient along the normal (pointing landward): which flank an
    # edge is. The norm does not change the sign, so it is not divided out.
    along = (
        cv2.Sobel(grey, cv2.CV_32F, 1, 0, ksize=3) * nx_field
        + cv2.Sobel(grey, cv2.CV_32F, 0, 1, ksize=3) * ny_field
    )
    rising, falling = edges & (along > 0), edges & (along < 0)
    out = np.zeros_like(coast_edges, dtype=bool)
    if not rising.any() or not falling.any():
        stats["coastLinePairedFraction"] = 0.0
        return coast_edges, stats

    ys, xs = np.nonzero(coast_edges)
    sign = along[ys, xs]
    near_rising, near_falling = _nearest(rising), _nearest(falling)
    qy = np.where(sign > 0, near_falling[0][ys, xs], near_rising[0][ys, xs])
    qx = np.where(sign > 0, near_falling[1][ys, xs], near_rising[1][ys, xs])
    gap = np.hypot(qx - xs, qy - ys)
    landward = signed[qy, qx] > signed[ys, xs]
    found = (sign != 0) & (gap <= max_gap)
    paired = found & landward
    land_flank = found & ~landward
    # The other flank landward but beyond a line's width: strokes merged into
    # a dark mass (islands, a delta, a narrow channel), whose sea side is not
    # the coast either. Dropped, rather than kept on the sea side.
    merged = (sign != 0) & ~found & landward & (gap <= 2.0 * max_gap)
    alone = ~found & ~merged

    out[ys[alone], xs[alone]] = True
    # The midpoint is often a half pixel: mark the pixels on both sides of it
    # rather than rounding, which would move every point of a straight run of
    # coast the same way.
    mx = (xs[paired] + qx[paired]) / 2.0
    my = (ys[paired] + qy[paired]) / 2.0
    for cx in (np.floor(mx), np.ceil(mx)):
        for cy in (np.floor(my), np.ceil(my)):
            out[cy.astype(int), cx.astype(int)] = True

    seeds = ~land_flank
    stats["coastLinePairedFraction"] = float(paired[seeds].mean()) if seeds.any() else 0.0
    stats["coastLineMergedFraction"] = float(merged[seeds].mean()) if seeds.any() else 0.0
    if paired.any():
        stats["coastLineFlankGapPx"] = float(np.median(gap[paired]))
    return out, stats


# --------------------------------------------------------------------------
# The bundle
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UserEvidence:
    """Everything the user's map offers to align against, in its pixel space."""

    width: int
    height: int
    edges: np.ndarray
    edge_weight: np.ndarray
    straight_lines: List[Tuple[int, int, int, int]]
    text_mask: np.ndarray
    legend_mask: np.ndarray
    water: np.ndarray
    ocean: np.ndarray
    lakes: np.ndarray
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_water(self) -> bool:
        return bool(self.water.any())

    @property
    def has_edges(self) -> bool:
        return bool(self.edges.any())


def build_user_evidence(
    image_bgr: np.ndarray,
    text_regions: Optional[TextRegions] = None,
    water_click_positions: Optional[Sequence[Sequence[float]]] = None,
    water_sampling_radii: Optional[Sequence[int]] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    legend_bounds: Optional[LegendBounds] = None,
) -> UserEvidence:
    """Build the edge map, the straight-line weighting and the water mask."""
    
    height, width = image_bgr.shape[:2]

    text_mask = build_text_mask(
        (height, width), text_regions, config.text_mask_dilation_px
    )
    legend = build_legend_mask((height, width), legend_bounds)
    image_rgb = (
        cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        if image_bgr.ndim == 3
        else cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2RGB)
    )
    water = build_water_mask(
        image_rgb, water_click_positions, water_sampling_radii, config
    ) & ~legend
    ocean, lakes = split_ocean_and_lakes(water, config)

    all_edges = build_edge_map(image_bgr, text_mask | legend, config)
    raw_edge_pixels = int(all_edges.sum())
    # Filtered before straight-line detection, so Hough only sees what the
    # alignment will actually use.
    edges, water_filter_applied = filter_edges_near_water(
        all_edges, ocean | lakes, config
    )
    line_stats: Dict[str, Any] = {"coastLinePairedFraction": None, "coastLineMergedFraction": None, "coastLineFlankGapPx": None}
    if water_filter_applied:
        edges, line_stats = centre_drawn_coast_lines(
            edges, all_edges, ocean | lakes, blurred_gray(image_bgr, config), config
        )
    lines = detect_straight_lines(edges, config)
    edge_weight = suppress_straight_lines(edges, lines, config)

    pixels = float(width * height) or 1.0
    suppressed = int((edges & (edge_weight < 1.0)).sum())
    stats = {
        "edgeFraction": float(edges.sum()) / pixels,
        "rawEdgePixels": raw_edge_pixels,
        "waterEdgeFilterApplied": water_filter_applied,
        "waterEdgeFilterKept": (
            float(edges.sum()) / raw_edge_pixels if raw_edge_pixels else 0.0
        ),
        "textMaskFraction": float(text_mask.sum()) / pixels,
        "legendMaskFraction": float(legend.sum()) / pixels,
        "straightLineCount": len(lines),
        "suppressedEdgePixels": suppressed,
        "suppressedEdgeFraction": (
            suppressed / float(edges.sum()) if edges.any() else 0.0
        ),
        "waterFraction": float(water.sum()) / pixels,
        "oceanFraction": float(ocean.sum()) / pixels,
        "lakeFraction": float(lakes.sum()) / pixels,
        "hasWater": bool(water.any()),
        **line_stats,
    }

    return UserEvidence(
        width=width,
        height=height,
        edges=edges,
        edge_weight=edge_weight,
        straight_lines=lines,
        text_mask=text_mask,
        legend_mask=legend,
        water=water,
        ocean=ocean,
        lakes=lakes,
        stats=stats,
    )


# --------------------------------------------------------------------------
# Debug output
# --------------------------------------------------------------------------


def dump_evidence_debug_pngs(
    evidence: UserEvidence,
    image_bgr: np.ndarray,
    out_dir: str,
) -> List[str]:
    """Write the evidence as overlays on the user's map."""
    import os

    os.makedirs(out_dir, exist_ok=True)
    written: List[str] = []

    def _write(name: str, image: np.ndarray) -> None:
        path = os.path.join(out_dir, f"{name}.png")
        cv2.imwrite(path, image)
        written.append(path)

    _write("edges", (evidence.edges.astype(np.uint8) * 255))
    _write("edge_weight", (evidence.edge_weight * 255).astype(np.uint8))

    # Only write masks that have content. An all-black PNG reads as a broken
    # dump rather than as "no OCR ran", and the difference matters: with no text
    # mask, roughly half the edge pixels on a labelled map are place names.
    if evidence.text_mask.any():
        _write("text_mask", (evidence.text_mask.astype(np.uint8) * 255))
    if evidence.legend_mask.any():
        _write("legend_mask", (evidence.legend_mask.astype(np.uint8) * 255))

    # Edges over the map: kept edges green, suppressed straight ones red, so a
    # graticule that survived suppression is visible at a glance.
    overlay = image_bgr.copy() if image_bgr.ndim == 3 else cv2.cvtColor(
        image_bgr, cv2.COLOR_GRAY2BGR
    )
    overlay = (overlay * 0.45).astype(np.uint8)
    kept = evidence.edges & (evidence.edge_weight >= 1.0)
    suppressed = evidence.edges & (evidence.edge_weight < 1.0)
    overlay[kept] = (0, 255, 0)
    overlay[suppressed] = (0, 0, 255)
    _write("edges_overlay", overlay)

    if evidence.has_water:
        water_overlay = image_bgr.copy() if image_bgr.ndim == 3 else cv2.cvtColor(
            image_bgr, cv2.COLOR_GRAY2BGR
        )
        water_overlay = (water_overlay * 0.45).astype(np.uint8)
        water_overlay[evidence.ocean] = (255, 120, 0)
        water_overlay[evidence.lakes] = (255, 220, 120)
        _write("water_overlay", water_overlay)

    return written
