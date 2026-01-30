import cv2  
import numpy as np
import os
import json
import math

NUMBER_OF_KEYPOINTS = 5
BORDER_MARGIN = 20  # pixels from edge
MIN_DISTANCE_BETWEEN_KEYPOINTS = 10  

# TODO REMOVE PRINTS BUDDY

def detect_sift_keypoints_on_image(gray_image: np.ndarray, apply_edge_detection: bool = True):
    """
    Core SIFT keypoint detection with filtering.
    Returns list of cv2.KeyPoint objects.
    """
    height, width = gray_image.shape
    
    if apply_edge_detection:
        # Apply blur to reduce noise before edge detection
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        # Create edge mask 
        edges = cv2.Canny(blurred, 75, 175)
        print(f"Edge mask: {np.count_nonzero(edges)} edge pixels")
    else:
        edges = None
    
    # Detect ALL keypoints on edges (no limit)
    sift = cv2.SIFT_create()
    all_keypoints, _ = sift.detectAndCompute(gray_image, mask=edges)
    
    print(f"Total keypoints detected: {len(all_keypoints)}")
    
    if len(all_keypoints) == 0:
        return []
    
    # Filter out keypoints too close to image borders
    filtered_keypoints = []
    for kp in all_keypoints:
        x, y = kp.pt
        if (BORDER_MARGIN < x < width - BORDER_MARGIN and 
            BORDER_MARGIN < y < height - BORDER_MARGIN):
            filtered_keypoints.append(kp)
    
    print(f"After border filtering: {len(filtered_keypoints)} keypoints")
    
    # Sort by response (strength) first
    filtered_keypoints = sorted(filtered_keypoints, key=lambda x: x.response, reverse=True)
    
    # Filter out keypoints too close to each other
    spaced_keypoints = []
    
    for kp in filtered_keypoints:
        # Check distance to all already selected keypoints
        too_close = False
        for selected_kp in spaced_keypoints:
            dx = kp.pt[0] - selected_kp.pt[0]
            dy = kp.pt[1] - selected_kp.pt[1]
            distance = (dx**2 + dy**2)**0.5
            
            if distance < MIN_DISTANCE_BETWEEN_KEYPOINTS:
                too_close = True
                break
        
        if not too_close:
            spaced_keypoints.append(kp)
            
        # Stop when we have enough keypoints
        if len(spaced_keypoints) >= NUMBER_OF_KEYPOINTS:
            break
    
    print(f"After spacing filter: {len(spaced_keypoints)} keypoints (min distance: {MIN_DISTANCE_BETWEEN_KEYPOINTS}px)")
    
    return spaced_keypoints

def find_key_points(file_content: bytes):
    """Detect SIFT key points and descriptors in the given image."""
    print("Finding SIFT key points...")
    # Transforming bytes to numpy array 
    nparr = np.frombuffer(file_content, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Use shared SIFT detection function
    key_points = detect_sift_keypoints_on_image(gray, apply_edge_detection=True)
    
    print(f"Selected top {len(key_points)} keypoints")
    
    # Print keypoint locations for debugging
    for i, kp in enumerate(key_points):
        print(f"  Keypoint {i+1}: ({kp.pt[0]:.1f}, {kp.pt[1]:.1f}), size: {kp.size:.1f}, response: {kp.response:.3f}")

    # Convert to color image to draw colored circles
    img_with_keypoints = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    # Draw large, visible circles for each keypoint
    for i, kp in enumerate(key_points):
        x, y = int(kp.pt[0]), int(kp.pt[1])
        cv2.circle(img_with_keypoints, (x, y), 15, (0, 255, 0), 2)
        cv2.circle(img_with_keypoints, (x, y), 3, (0, 0, 255), -1)
        cv2.putText(img_with_keypoints, str(i+1), (x+20, y-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(current_dir, "extracted_texts")
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "sift_keypoints.png")
    
    success = cv2.imwrite(output_path, img_with_keypoints)
    
    if success:
        print(f"✓ Successfully saved keypoints image to: {output_path}")
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"✓ File exists and is {file_size} bytes")
        else:
            print(f"✗ File does not exist after write: {output_path}")
    else:
        print(f"✗ cv2.imwrite() failed for: {output_path}")
    
    return output_path

def find_coastline_keypoints(bounds: dict, width: int = 1024, height: int = 768):
    """Find SIFT keypoints on coastlines from GeoJSON within geographic bounds."""
    
    # Load ne_coastline.geojson
    geojson_path = os.path.join(os.path.dirname(__file__), "..", "geojson", "ne_coastline.geojson")
    
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)
    
    print(f"Loaded coastline GeoJSON from: {geojson_path}")
    
    # Create blank image
    coastline_image = np.zeros((height, width), dtype=np.uint8)
    
    # Draw coastlines
    features = geojson_data.get('features', [])
    for feature in features:
        geometry = feature.get('geometry', {})
        coords = geometry.get('coordinates', [])
        geom_type = geometry.get('type')
        
        if geom_type == 'LineString':
            draw_coastline(coastline_image, coords, bounds, width, height)
        elif geom_type == 'MultiLineString':
            for line in coords:
                draw_coastline(coastline_image, line, bounds, width, height)
    
    print(f"Rasterized coastlines: {np.count_nonzero(coastline_image)} white pixels")
    
    # Save raster for debugging
    output_dir = os.path.join(os.path.dirname(__file__), "extracted_texts")
    os.makedirs(output_dir, exist_ok=True)
    cv2.imwrite(os.path.join(output_dir, "coastline_raster.png"), coastline_image)
    
    # Use shared SIFT detection function
    spaced = detect_sift_keypoints_on_image(coastline_image, apply_edge_detection=True)
    
    print(f"Selected {len(spaced)} keypoints")
    
    if len(spaced) == 0:
        return {"keypoints": [], "total": 0}
    
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
        print(f"  KP {i+1}: pixel({px:.1f},{py:.1f}) → ({lat:.4f},{lon:.4f})")
    
    # Draw keypoints on the coastline image
    img_vis = cv2.cvtColor(coastline_image, cv2.COLOR_GRAY2BGR)
    for i, kp in enumerate(spaced):
        x, y = int(kp.pt[0]), int(kp.pt[1])
        cv2.circle(img_vis, (x, y), 15, (0, 255, 0), 2)
        cv2.circle(img_vis, (x, y), 3, (0, 0, 255), -1)
        cv2.putText(img_vis, str(i+1), (x+20, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
    
    keypoints_path = os.path.join(output_dir, "coastline_keypoints.png")
    cv2.imwrite(keypoints_path, img_vis)
    print(f"✓ Saved coastline with keypoints to: {keypoints_path}")
    
    return {"keypoints": keypoints, "total": len(keypoints)}

def draw_coastline(img, coords, bounds, width, height):
    """Draw a coastline on the image."""
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