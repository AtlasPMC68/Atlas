"""User-side evidence: what the scanned map itself offers to align against.

Three products, all in the user's image pixel space:

    edge_weight   Canny edges, text masked out, long straight lines down-weighted
    water         the water pipette's colour, split into ocean and lakes
    text_mask     dilated OCR regions, so labels do not become edges

**Straight-line suppression is the cheapest anti-failure measure in the plan**
(section 10.1). Graticules, neatlines, inset frames and legend boxes are
straight; coastlines are not. Those straight lines are the dominant attractors
for wrong-feature lock, and a fit locked onto the wrong feature has *low* chamfer
residual by construction, so nothing downstream will notice. They are separated
from real geography by straightness alone, which is why this belongs here rather
than in a later, cleverer stage.

They are **down-weighted, not deleted**. A real coastline can run straight for a
while, and a neatline that happens to sit on a coast should not take the coast
with it.

**Not doing: toponym water cues.** Parsing labels for *Baie*, *Lac*, *Mer* to
infer water where colour fails is cut from the plan entirely, not deferred. The
consequence is accepted knowingly: on a map like Leclerc with an unpainted white
Atlantic, the water pipette yields nothing and there is no water evidence at all.
That is exactly why the GCP-based gate is primary and the water gate secondary,
and why the recovery ladder cannot depend on a water mask existing.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from skimage.color import deltaE_ciede2000, rgb2lab

from app.utils.color_in_legends_extraction import sample_color_at

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
    """Mask of the OCR regions, dilated outwards.

    Dilated because Canny fires on the *outside* of a glyph as readily as the
    inside, so a mask tight to the bounding box still leaves a rectangle of
    edges around every label.
    """
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
        size = 2 * int(dilation_px) + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        mask = cv2.dilate(mask, kernel)

    return mask.astype(bool)


# --------------------------------------------------------------------------
# Edges
# --------------------------------------------------------------------------


def build_edge_map(
    image_bgr: np.ndarray,
    text_mask: Optional[np.ndarray] = None,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> np.ndarray:
    """Canny edges of the user's map, with text regions removed."""
    if image_bgr.ndim == 3:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = image_bgr

    ksize = int(config.edge_blur_ksize) | 1  # Gaussian kernels must be odd
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)
    edges = cv2.Canny(blurred, config.edge_canny_low, config.edge_canny_high) > 0

    if text_mask is not None and text_mask.any():
        edges = edges & ~text_mask

    return edges


def detect_straight_lines(
    edges: np.ndarray,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> List[Tuple[int, int, int, int]]:
    """Long straight segments in the edge map, as (x1, y1, x2, y2).

    The length threshold is a fraction of the image diagonal, not an absolute
    pixel count, so it means the same thing on a 900 px scan and a 6000 px one.
    """
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
    """Flatten whatever `HoughLinesP` returned into a list of 4-tuples.

    The shape is not stable across OpenCV majors: 4.x returns `(N, 1, 4)` and
    5.0 returns `(N, 4)`. `opencv-python-headless` is unpinned in
    `requirements.txt`, so two images built weeks apart disagree -- which is
    exactly how this was found. Reshaping to `(-1, 4)` accepts either.
    """
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
    """Turn the binary edge map into a weight map, down-weighting straight runs.

    Returns float32 in [0, 1]: 1.0 on an ordinary edge pixel,
    `config.straight_line_weight` on one lying under a detected straight
    segment, 0.0 where there is no edge at all.
    """
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
    """Pixels close in colour to any water pick.

    Same colour space and metric as zone extraction (CIELAB, CIEDE2000), so a
    water pick behaves like a zone pick -- it simply never becomes a zone.
    """
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
    """Split a water mask into (ocean, lakes).

    The ocean is the largest connected component touching the image border: the
    sea runs off the edge of a map, a lake does not. Everything else above a
    minimum area is a lake.

    Known limitation: a sea cut into two pieces by a peninsula at the frame edge
    contributes its smaller piece to `lakes`. Harmless for a gate that compares
    total water, which is what section 8.2 does.
    """
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
) -> UserEvidence:
    """Build the edge map, the straight-line weighting and the water mask.

    Args:
        image_bgr: the user's map as OpenCV reads it (BGR, uint8).
        text_regions: OCR polygons, when text extraction ran. Optional -- the
            dev-test path skips text extraction entirely.
        water_click_positions: normalised (x, y) water pipette picks.
        water_sampling_radii: per-pick sampling radius in pixels.
    """
    height, width = image_bgr.shape[:2]

    text_mask = build_text_mask(
        (height, width), text_regions, config.text_mask_dilation_px
    )
    edges = build_edge_map(image_bgr, text_mask, config)
    lines = detect_straight_lines(edges, config)
    edge_weight = suppress_straight_lines(edges, lines, config)

    image_rgb = (
        cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        if image_bgr.ndim == 3
        else cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2RGB)
    )
    water = build_water_mask(
        image_rgb, water_click_positions, water_sampling_radii, config
    )
    ocean, lakes = split_ocean_and_lakes(water, config)

    pixels = float(width * height) or 1.0
    suppressed = int((edges & (edge_weight < 1.0)).sum())
    stats = {
        "edgeFraction": float(edges.sum()) / pixels,
        "textMaskFraction": float(text_mask.sum()) / pixels,
        "straightLineCount": len(lines),
        "suppressedEdgePixels": suppressed,
        "suppressedEdgeFraction": (
            suppressed / float(edges.sum()) if edges.any() else 0.0
        ),
        "waterFraction": float(water.sum()) / pixels,
        "oceanFraction": float(ocean.sum()) / pixels,
        "lakeFraction": float(lakes.sum()) / pixels,
        "hasWater": bool(water.any()),
    }

    return UserEvidence(
        width=width,
        height=height,
        edges=edges,
        edge_weight=edge_weight,
        straight_lines=lines,
        text_mask=text_mask,
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
