"""
Merge the OCR boxes of a label split over several boxes.

The detector finds one box per line of text, so a label written on two lines
("Burkina" / "Faso") or with a wide gap ("Lac" "Érié") comes out as separate
boxes, and each piece alone matches no place, or the wrong one.

Two boxes are merged when they look like one label:
    - same text height (font size) and angle
    - touching once grown by a margin, side by side or stacked
and either:
    - one of them is a generic word missing its name ("Lac", "Golfe du", "Saint",
      or "City", "Bay" after it)
    - or the joined text is a place while neither piece is one on its own
"""

import logging
import math

import numpy as np

from app.utils.place_nomenclature import _normalize
from app.utils.place_resolution import _PREFIX_TYPE_MAP, MATCHING_CONFIG, resolve_place

logger = logging.getLogger(__name__)

# Two boxes have the same font size when their heights differ by at most this
# ratio, or this many pixels for small text where one pixel is already 8%
HEIGHT_TOLERANCE_RATIO = 0.10
HEIGHT_TOLERANCE_PX = 2.0

# Maximal angle difference, in degrees, between two boxes of the same label
ANGLE_TOLERANCE_DEG = 5.0

# Each box is grown by this ratio of the text height: two boxes whose grown
# versions touch are close enough to be one label
MERGE_MARGIN_RATIO = 0.5

# Joined text must match a place at least this closely. The OCR runs before the
# map frame is known, so the match is against the whole world: at the usual
# 0.80, "très Sols" from a legend matched Três Passos (Brazil), while a real
# label misread as "Base d'Hudson" matches Baie d'Hudson at about 0.92
MERGE_MATCH_THRESHOLD = 0.90

# Words that start a place name and need the name after them
GENERIC_PREFIXES = set(_PREFIX_TYPE_MAP) | {
    "fort", "saint", "sainte", "st", "ste", "pointe", "port",
    "grand", "grande", "haut", "haute", "bas", "basse",
    "nouveau", "nouvel", "nouvelle", "petit", "petite", "monts",
}

# Words that end a place name and need the name before them
GENERIC_SUFFIXES = {
    "city", "lake", "lakes", "bay", "bays", "gulf", "strait", "sea", "ocean",
    "river", "mountain", "mountains", "peak", "cape", "island", "islands",
    "peninsula", "county", "state", "territory", "kingdom",
}

# Small words allowed around a generic word ("Golfe du", "Baie des")
PARTICLES = {"de", "du", "des", "d", "la", "le", "les", "l", "au", "aux", "of", "the"}


def merge_split_labels(detections):
    """
    Merge the boxes of labels split over several boxes, until no pair is left.
    Detections are {"text", "score", "quad"} dicts, quads in (tl, tr, br, bl) order.
    """
    boxes = list(detections)

    merged_any = True
    while merged_any:
        merged_any = False

        # Every compatible pair, the closest first
        pairs = []
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                layout = _pair_layout(boxes[i], boxes[j], i, j)
                if layout is not None:
                    pairs.append(layout)
        pairs.sort(key=lambda pair: pair["gap"])

        # Each box is merged at most once per pass, a merged box can merge
        # again on the next pass (labels on three lines)
        used = set()
        replacements = {}
        for pair in pairs:
            first, second = pair["first"], pair["second"]
            if first in used or second in used:
                continue
            separator = " " if pair["layout"] == "line" else "\n"
            text = f"{boxes[first]['text']}{separator}{boxes[second]['text']}"
            if not _should_merge(boxes[first]["text"], boxes[second]["text"], text):
                continue

            logger.debug(f"[OCR] Merged {boxes[first]['text']!r} and {boxes[second]['text']!r}")
            used.update((first, second))
            replacements[min(first, second)] = {
                "text": text,
                "score": min(boxes[first]["score"], boxes[second]["score"]),
                "quad": _union_quad(boxes[first]["quad"], boxes[second]["quad"]),
                # A box of several lines is compared to others by the height of one line
                "line_height": max(_box_size(boxes[first])[0], _box_size(boxes[second])[0]),
            }
            merged_any = True

        # The merged box takes the place of the first of its two boxes
        boxes = [replacements.get(k, box) for k, box in enumerate(boxes) if k not in used or k in replacements]

    for box in boxes:
        box.pop("line_height", None)
    return boxes


def _should_merge(first_text, second_text, joined_text):
    """Tell if two geometrically compatible boxes are the same label."""
    if _is_lone_prefix(first_text) or _is_lone_suffix(second_text):
        return True
    return _is_place(joined_text, MERGE_MATCH_THRESHOLD) and not (
        _is_place(first_text, MATCHING_CONFIG["exact_threshold"])
        or _is_place(second_text, MATCHING_CONFIG["exact_threshold"])
    )


def _is_lone_prefix(text):
    """A generic word waiting for its name: "Lac", "Golfe du", "Île de", "Saint"."""
    tokens = _normalize(text).split()
    return bool(tokens) and tokens[0] in GENERIC_PREFIXES and all(t in GENERIC_PREFIXES | PARTICLES for t in tokens)


def _is_lone_suffix(text):
    """A generic word following its name: "City", "Bay", "Island"."""
    tokens = _normalize(text).split()
    return bool(tokens) and tokens[-1] in GENERIC_SUFFIXES and all(t in GENERIC_SUFFIXES | PARTICLES for t in tokens)


def _is_place(text, threshold):
    """Tell if a text matches a known place, anywhere in the world."""
    try:
        return bool(resolve_place(text.replace("\n", " "), confidence_threshold=threshold).get("found"))
    except Exception:
        return False


def _frame(quad):
    """The text direction of a box: origin, unit vectors along (u) and across (v) it."""
    tl, tr, _, _ = np.asarray(quad, dtype=float)
    u = (tr - tl) / max(np.linalg.norm(tr - tl), 1e-6)
    v = np.array([-u[1], u[0]])
    return tl, u, v


def _box_size(box):
    """Line height (across the text) and angle in degrees (along the text) of a box."""
    tl, tr, br, bl = np.asarray(box["quad"], dtype=float)
    height = box.get("line_height") or (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2.0
    angle = math.degrees(math.atan2(tr[1] - tl[1], tr[0] - tl[0]))
    return height, angle


def _extent(quad, origin, u, v):
    """Bounds of a box along (u) and across (v) a text direction."""
    points = np.asarray(quad, dtype=float) - origin
    along, across = points @ u, points @ v
    return along.min(), along.max(), across.min(), across.max()


def _pair_layout(a, b, i, j):
    """
    How two boxes sit together if they can be one label: on the same line or
    stacked, which one comes first, and the gap between them. None otherwise.
    """
    height_a, angle_a = _box_size(a)
    height_b, angle_b = _box_size(b)

    # Same font size
    height = max(height_a, height_b)
    if abs(height_a - height_b) > max(HEIGHT_TOLERANCE_RATIO * height, HEIGHT_TOLERANCE_PX):
        return None

    # Same angle
    angle_diff = abs(angle_a - angle_b) % 360
    if min(angle_diff, 360 - angle_diff) > ANGLE_TOLERANCE_DEG:
        return None

    # Both boxes measured in the text direction of the first one
    origin, u, v = _frame(a["quad"])
    a_left, a_right, a_top, a_bottom = _extent(a["quad"], origin, u, v)
    b_left, b_right, b_top, b_bottom = _extent(b["quad"], origin, u, v)
    max_gap = 2 * MERGE_MARGIN_RATIO * height
    overlap_across = min(a_bottom, b_bottom) - max(a_top, b_top)
    overlap_along = min(a_right, b_right) - max(a_left, b_left)

    # Same line: mostly the same height band, with a small gap along the text
    if overlap_across >= 0.5 * min(height_a, height_b):
        gap = max(b_left - a_right, a_left - b_right)
        if gap <= max_gap:
            first, second = (i, j) if a_left <= b_left else (j, i)
            return {"layout": "line", "first": first, "second": second, "gap": gap}
        return None

    # Stacked: overlapping along the text, with a small gap across it
    if overlap_along > 0:
        gap = max(b_top - a_bottom, a_top - b_bottom)
        if gap <= max_gap:
            first, second = (i, j) if a_top <= b_top else (j, i)
            return {"layout": "stack", "first": first, "second": second, "gap": gap}

    return None


def _union_quad(quad_a, quad_b):
    """Smallest box in the text direction of quad_a covering both quads."""
    origin, u, v = _frame(quad_a)
    a_extent = _extent(quad_a, origin, u, v)
    b_extent = _extent(quad_b, origin, u, v)
    left, right = min(a_extent[0], b_extent[0]), max(a_extent[1], b_extent[1])
    top, bottom = min(a_extent[2], b_extent[2]), max(a_extent[3], b_extent[3])
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
    return [(origin + along * u + across * v).tolist() for along, across in corners]
