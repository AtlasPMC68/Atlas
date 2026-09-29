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

# Sampling cost is candidates x points, so a cap keeps the worst case bounded
# on a dense raster. Candidates are taken strongest-first, so what is dropped
# is the weak tail.
MAX_CANDIDATES = 5000

DEBUG = False


def select_spread_keypoints(keypoints, count: int, min_separation_px: float):
    """Pick `count` keypoints spread as widely as possible (farthest-point sampling).

    Seeds with the strongest response, then repeatedly takes the candidate
    farthest from everything already chosen.

    Chosen over the previous "keep anything at least D pixels from the ones
    kept so far" for two reasons:

    - **D was doing two jobs and could only do one.** Small, it deduplicates but
      leaves the points clustered on whichever stretch of coast SIFT likes;
      large, it spreads them but exhausts the candidates and silently returns
      fewer than asked. Measured on a Quebec framing box, D=10 px left a pool
      of 19 while D=200 px left 6, so no single value both spreads and fills.
      Here spread is the objective and the count is met whenever the candidates
      allow it.
    - **Spread is what the georeferencing actually needs.** Control points
      bunched together make the affine badly conditioned, which is what the
      `probe_gcp_disagreement` gate punishes. It should be maximised outright,
      not fall out of a threshold.

    `min_separation_px` only stops the selection once the best remaining
    candidate is a near-duplicate of one already chosen, which happens when the
    candidates run out before `count` is reached.
    """
    if count <= 0 or not keypoints:
        return []

    ordered = sorted(keypoints, key=lambda kp: kp.response, reverse=True)
    ordered = ordered[:MAX_CANDIDATES]
    points = np.array([kp.pt for kp in ordered], dtype=float)

    chosen = [0]  # the strongest response seeds it
    # Distance from every candidate to the nearest chosen point, kept as a
    # running minimum so each round costs one pass rather than one per pair.
    distance = np.hypot(points[:, 0] - points[0, 0], points[:, 1] - points[0, 1])

    while len(chosen) < count:
        farthest = int(np.argmax(distance))
        if distance[farthest] < min_separation_px:
            break  # everything left duplicates a point already chosen
        chosen.append(farthest)
        np.minimum(
            distance,
            np.hypot(
                points[:, 0] - points[farthest, 0],
                points[:, 1] - points[farthest, 1],
            ),
            out=distance,
        )

    return [ordered[i] for i in chosen]


def detect_sift_keypoints_on_image(gray_image: np.ndarray, apply_edge_detection: bool = True):

    height, width = gray_image.shape
    diagonal = float(np.hypot(width, height))
    border_margin = BORDER_MARGIN_RATIO * diagonal

    if apply_edge_detection:
        # Apply blur to reduce noise before edge detection
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        # Create edge mask
        edges = cv2.Canny(blurred, 75, 175)
    else:
        edges = None

    # Detect ALL keypoints on edges (no limit)
    sift = cv2.SIFT_create()
    all_keypoints, _ = sift.detectAndCompute(gray_image, mask=edges)

    if len(all_keypoints) == 0:
        return []

    # Filter out keypoints too close to image borders
    filtered_keypoints = []
    for kp in all_keypoints:
        x, y = kp.pt
        if (border_margin < x < width - border_margin and
            border_margin < y < height - border_margin):
            filtered_keypoints.append(kp)

    return select_spread_keypoints(
        filtered_keypoints,
        NUMBER_OF_KEYPOINTS,
        MIN_SEPARATION_RATIO * diagonal,
    )


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
    """
    Find SIFT keypoints on coastlines within geographic bounds.
    First tries with just coastlines. If fewer than 10 keypoints found,
    adds lakes for more detail.
    """
    geojson_dir = os.path.join(os.path.dirname(__file__), "..", "geojson")
    coastline_path = os.path.join(geojson_dir, "ne_coastline.geojson")
    lakes_path = os.path.join(geojson_dir, "ne_50m_lakes.geojson")
    
    # Step 1: Try with just coastline
    coastline_image = np.zeros((height, width), dtype=np.uint8)
    draw_geojson_features(coastline_image, coastline_path, bounds, width, height)
    
    if DEBUG:
        output_dir = os.path.join(os.path.dirname(__file__), "extracted_texts")
        os.makedirs(output_dir, exist_ok=True)
        cv2.imwrite(os.path.join(output_dir, "coastline_only_raster.png"), coastline_image)

    # TODO this is a testing modificaiton where I want to include lake
    draw_geojson_features(coastline_image, lakes_path, bounds, width, height)
    used_lakes = True
    
    # Detect keypoints on coastline only
    spaced = detect_sift_keypoints_on_image(coastline_image, apply_edge_detection=True)
    #used_lakes = False
    
    # Step 2: If we don't have enough keypoints, add lakes
    if len(spaced) < NUMBER_OF_KEYPOINTS:
        # Add lakes to the existing coastline image
        draw_geojson_features(coastline_image, lakes_path, bounds, width, height)
        used_lakes = True
        
        if DEBUG:
            cv2.imwrite(os.path.join(output_dir, "coastline_with_lakes_raster.png"), coastline_image)
        
        # Re-run SIFT detection with lakes included
        spaced = detect_sift_keypoints_on_image(coastline_image, apply_edge_detection=True)
    
    if len(spaced) == 0:
        return {"keypoints": [], "total": 0, "used_lakes": used_lakes}
    
    # Convert to lat/lon
    keypoints = []
    for i, kp in enumerate(spaced):
        px, py = kp.pt
        lon = bounds['west'] + (px / width) * (bounds['east'] - bounds['west'])
        lat = bounds['north'] - (py / height) * (bounds['north'] - bounds['south'])
        
        keypoints.append({
            "id": i + 1,
            "pixel": {"x": float(px), "y": float(py)},
            "geo": {"lat": lat, "lng": lon},
            "response": float(kp.response)
        })
    
    if DEBUG:
        img_vis = cv2.cvtColor(coastline_image, cv2.COLOR_GRAY2BGR)
        for i, kp in enumerate(spaced):
            x, y = int(kp.pt[0]), int(kp.pt[1])
            cv2.circle(img_vis, (x, y), 15, (0, 255, 0), 2)
            cv2.circle(img_vis, (x, y), 3, (0, 0, 255), -1)
            cv2.putText(img_vis, str(i + 1), (x + 20, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        
        debug_filename = "with_lakes_keypoints.png" if used_lakes else "coastline_only_keypoints.png"
        keypoints_path = os.path.join(output_dir, debug_filename)
        cv2.imwrite(keypoints_path, img_vis)
    
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