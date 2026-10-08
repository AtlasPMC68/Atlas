import cv2  
import numpy as np
import os
import json

NUMBER_OF_KEYPOINTS = 15

# Ratios of the image diagonal, not pixels: this module rasterizes the framing
# box at whatever size the caller asks for (the endpoint takes width/height),
# and a constant in pixels silently means something different at each size.
BORDER_MARGIN_RATIO = 0.02  # ~25 px on the 1024x768 default
# Only a duplicate floor, *not* how the points get spread out -- that is the
# sampling below. SIFT reports several keypoints at one location (different
# scales and orientations), and two control points in the same spot constrain
# nothing.
MIN_SEPARATION_RATIO = 0.01  # ~13 px on the 1024x768 default
# What "well spaced" means when choosing between a coastline and a lake
# keypoint: a lake point is only taken when no coastline point is at least this
# far from every point already chosen. Measured on the test cases' framing
# boxes: at 5% of the diagonal, 6 of 14 boxes gain 1-5 lake points and the
# points' hull roughly doubles there (~0.25 -> ~0.45 of the frame); the others
# stay all coastline.
WELL_SPACED_RATIO = 0.05  # ~64 px on the 1024x768 default

COASTLINE = "coastline"
LAKE = "lake"

# Sampling cost is candidates x points, so a cap keeps the worst case bounded
# on a dense raster. Candidates are taken strongest-first, so what is dropped
# is the weak tail.
MAX_CANDIDATES = 5000

DEBUG = False


def select_spread_keypoints(
    coastline_keypoints,
    lake_keypoints,
    count: int,
    well_spaced_px: float,
    min_separation_px: float,
):
    """Pick up to `count` keypoints spread as widely as possible, coastline first.

    Farthest-point sampling: seed with the strongest coastline keypoint (the
    strongest lake one when the box has no coast), then repeatedly take the
    candidate farthest from everything already chosen. Spread is the objective
    because clustered control points make the affine badly conditioned; a
    single "at least D px apart" threshold could not both spread the points and
    fill the request.

    Lakes are always candidates but never preferred. A user's map may omit a
    lake or draw it schematically, while it always draws the coast. So each
    round takes the farthest *coastline* candidate that is still well spaced
    (`well_spaced_px` from every chosen point), and a lake only when no
    coastline candidate is. Once neither is, the same rule continues down to
    `min_separation_px`, which is only a duplicate floor: SIFT reports several
    keypoints at one spot, and two control points there constrain nothing.

    Returns:
        ``(keypoint, feature)`` pairs, feature being ``COASTLINE`` or ``LAKE``,
        in the order chosen.
    """
    candidates = [
        (kp, feature)
        for feature, keypoints in ((COASTLINE, coastline_keypoints), (LAKE, lake_keypoints))
        for kp in sorted(keypoints, key=lambda kp: kp.response, reverse=True)[:MAX_CANDIDATES]
    ]
    if count <= 0 or not candidates:
        return []

    points = np.array([kp.pt for kp, _ in candidates], dtype=float)
    is_coast = np.array([feature == COASTLINE for _, feature in candidates])

    # Candidates are strongest-first within each feature, coastline first.
    chosen = [0]
    # Distance from every candidate to the nearest chosen point, kept as a
    # running minimum so each round costs one pass rather than one per pair.
    distance = np.hypot(points[:, 0] - points[0, 0], points[:, 1] - points[0, 1])

    for spacing in (well_spaced_px, min_separation_px):
        while len(chosen) < count:
            eligible = distance >= spacing
            pool = eligible & is_coast
            if not pool.any():
                pool = eligible & ~is_coast
            if not pool.any():
                break
            index = np.flatnonzero(pool)
            pick = int(index[np.argmax(distance[index])])
            chosen.append(pick)
            np.minimum(
                distance,
                np.hypot(points[:, 0] - points[pick, 0], points[:, 1] - points[pick, 1]),
                out=distance,
            )

    return [candidates[i] for i in chosen]


def detect_sift_candidates(gray_image: np.ndarray, apply_edge_detection: bool = True):
    """Every SIFT keypoint on the render's edges, away from its borders."""
    height, width = gray_image.shape
    border_margin = BORDER_MARGIN_RATIO * float(np.hypot(width, height))

    if apply_edge_detection:
        # Apply blur to reduce noise before edge detection
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        # Create edge mask
        edges = cv2.Canny(blurred, 75, 175)
    else:
        edges = None

    sift = cv2.SIFT_create()
    keypoints, _ = sift.detectAndCompute(gray_image, mask=edges)

    return [
        kp
        for kp in keypoints
        if border_margin < kp.pt[0] < width - border_margin
        and border_margin < kp.pt[1] < height - border_margin
    ]


def draw_geojson_features(img: np.ndarray, geojson_path: str, bounds: dict, width: int, height: int):
    """Draw GeoJSON features (coastlines, lakes, etc.) onto an image."""
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    features = geojson_data.get('features', [])
    for feature in features:
        geometry = feature.get('geometry', {})
        coords = geometry.get('coordinates', [])
        geom_type = geometry.get('type')
        
        if geom_type == 'LineString':
            draw_coastline(img, coords, bounds, width, height)
        elif geom_type == 'MultiLineString':
            for line in coords:
                draw_coastline(img, line, bounds, width, height)
        elif geom_type == 'Polygon':
            # For polygons (like lakes), draw the outer ring
            if len(coords) > 0:
                draw_coastline(img, coords[0], bounds, width, height)
        elif geom_type == 'MultiPolygon':
            # For multi-polygons, draw all outer rings
            for polygon in coords:
                if len(polygon) > 0:
                    draw_coastline(img, polygon[0], bounds, width, height)


def find_coastline_keypoints(bounds: dict, width: int = 1024, height: int = 768):
    """Suggest SIFT keypoints for the user to match, inside geographic bounds.

    The coastline and the lake shorelines are rendered separately, so each
    keypoint knows which it came from, and `select_spread_keypoints` prefers
    the coastline: lakes fill in only where the coast leaves the frame
    uncovered.
    """
    geojson_dir = os.path.join(os.path.dirname(__file__), "..", "geojson")
    diagonal = float(np.hypot(width, height))

    renders = {}
    candidates = {}
    for feature, filename in ((COASTLINE, "ne_coastline.geojson"), (LAKE, "ne_50m_lakes.geojson")):
        render = np.zeros((height, width), dtype=np.uint8)
        draw_geojson_features(render, os.path.join(geojson_dir, filename), bounds, width, height)
        renders[feature] = render
        candidates[feature] = detect_sift_candidates(render, apply_edge_detection=True)

    selected = select_spread_keypoints(
        candidates[COASTLINE],
        candidates[LAKE],
        NUMBER_OF_KEYPOINTS,
        WELL_SPACED_RATIO * diagonal,
        MIN_SEPARATION_RATIO * diagonal,
    )
    used_lakes = any(feature == LAKE for _, feature in selected)

    # Convert to lat/lon
    keypoints = []
    for i, (kp, feature) in enumerate(selected):
        px, py = kp.pt
        lon = bounds['west'] + (px / width) * (bounds['east'] - bounds['west'])
        lat = bounds['north'] - (py / height) * (bounds['north'] - bounds['south'])

        keypoints.append({
            "id": i + 1,
            "pixel": {"x": float(px), "y": float(py)},
            "geo": {"lat": lat, "lng": lon},
            "response": float(kp.response),
            "feature": feature,
        })

    if DEBUG:
        output_dir = os.path.join(os.path.dirname(__file__), "extracted_texts")
        os.makedirs(output_dir, exist_ok=True)
        img_vis = cv2.cvtColor(np.maximum(renders[COASTLINE], renders[LAKE]), cv2.COLOR_GRAY2BGR)
        for i, (kp, feature) in enumerate(selected):
            x, y = int(kp.pt[0]), int(kp.pt[1])
            colour = (0, 255, 0) if feature == COASTLINE else (255, 160, 0)
            cv2.circle(img_vis, (x, y), 15, colour, 2)
            cv2.circle(img_vis, (x, y), 3, (0, 0, 255), -1)
            cv2.putText(img_vis, str(i + 1), (x + 20, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        cv2.imwrite(os.path.join(output_dir, "sift_keypoints.png"), img_vis)

    return {"keypoints": keypoints, "total": len(keypoints), "used_lakes": used_lakes}


def draw_coastline(img, coords, bounds, width, height):
    points = []
    for lon, lat in coords:
        if not (bounds['west'] <= lon <= bounds['east'] and bounds['south'] <= lat <= bounds['north']):
            continue
        
        px = int((lon - bounds['west']) / (bounds['east'] - bounds['west']) * width)
        py = int((bounds['north'] - lat) / (bounds['north'] - bounds['south']) * height)
        px = max(0, min(width - 1, px))
        py = max(0, min(height - 1, py))
        points.append([px, py])
    
    if len(points) > 1:
        cv2.polylines(img, [np.array(points, dtype=np.int32)], False, 255, 3, cv2.LINE_AA)