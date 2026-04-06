import base64
import json
import os
from typing import Any, Optional
from uuid import uuid4

import cv2
import numpy as np

NUMBER_OF_KEYPOINTS = 10
BORDER_MARGIN = 20  # pixels from edge
MIN_DISTANCE_BETWEEN_KEYPOINTS = 10
DEBUG = False


def detect_sift_keypoints_and_descriptors_on_image(
    gray_image: np.ndarray,
    apply_edge_detection: bool = True,
    max_keypoints: Optional[int] = NUMBER_OF_KEYPOINTS,
    min_distance: int = MIN_DISTANCE_BETWEEN_KEYPOINTS,
):
    height, width = gray_image.shape

    if apply_edge_detection:
        blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
        edges = cv2.Canny(blurred, 75, 175)
    else:
        edges = None

    sift = cv2.SIFT_create()
    all_keypoints, all_descriptors = sift.detectAndCompute(gray_image, mask=edges)

    if not all_keypoints or all_descriptors is None:
        return [], None

    filtered_entries = []
    for i, kp in enumerate(all_keypoints):
        x, y = kp.pt
        if (
            BORDER_MARGIN < x < width - BORDER_MARGIN
            and BORDER_MARGIN < y < height - BORDER_MARGIN
        ):
            filtered_entries.append((kp, all_descriptors[i]))

    if not filtered_entries:
        return [], None

    filtered_entries.sort(key=lambda pair: pair[0].response, reverse=True)

    spaced_keypoints = []
    spaced_descriptors = []

    for kp, descriptor in filtered_entries:
        too_close = False
        for selected_kp in spaced_keypoints:
            dx = kp.pt[0] - selected_kp.pt[0]
            dy = kp.pt[1] - selected_kp.pt[1]
            distance = (dx**2 + dy**2) ** 0.5

            if distance < min_distance:
                too_close = True
                break

        if too_close:
            continue

        spaced_keypoints.append(kp)
        spaced_descriptors.append(descriptor)

        if max_keypoints is not None and len(spaced_keypoints) >= max_keypoints:
            break

    if not spaced_keypoints:
        return [], None

    return spaced_keypoints, np.asarray(spaced_descriptors, dtype=np.float32)


def detect_sift_keypoints_on_image(
    gray_image: np.ndarray,
    apply_edge_detection: bool = True,
):
    keypoints, _ = detect_sift_keypoints_and_descriptors_on_image(
        gray_image,
        apply_edge_detection=apply_edge_detection,
        max_keypoints=NUMBER_OF_KEYPOINTS,
        min_distance=MIN_DISTANCE_BETWEEN_KEYPOINTS,
    )
    return keypoints


def draw_coastline(img, coords, bounds, width, height):
    points = []
    for lon, lat in coords:
        if not (
            bounds["west"] <= lon <= bounds["east"]
            and bounds["south"] <= lat <= bounds["north"]
        ):
            continue

        px = int((lon - bounds["west"]) / (bounds["east"] - bounds["west"]) * width)
        py = int((bounds["north"] - lat) / (bounds["north"] - bounds["south"]) * height)
        px = max(0, min(width - 1, px))
        py = max(0, min(height - 1, py))
        points.append([px, py])

    if len(points) > 1:
        cv2.polylines(img, [np.array(points, dtype=np.int32)], False, 255, 3, cv2.LINE_AA)


def draw_geojson_features(
    img: np.ndarray,
    geojson_path: str,
    bounds: dict,
    width: int,
    height: int,
):
    with open(geojson_path, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    features = geojson_data.get("features", [])
    for feature in features:
        geometry = feature.get("geometry", {})
        coords = geometry.get("coordinates", [])
        geom_type = geometry.get("type")

        if geom_type == "LineString":
            draw_coastline(img, coords, bounds, width, height)
        elif geom_type == "MultiLineString":
            for line in coords:
                draw_coastline(img, line, bounds, width, height)
        elif geom_type == "Polygon":
            if len(coords) > 0:
                draw_coastline(img, coords[0], bounds, width, height)
        elif geom_type == "MultiPolygon":
            for polygon in coords:
                if len(polygon) > 0:
                    draw_coastline(img, polygon[0], bounds, width, height)


def find_coastline_keypoints(bounds: dict, width: int = 1024, height: int = 768):
    geojson_dir = os.path.join(os.path.dirname(__file__), "..", "geojson")
    coastline_path = os.path.join(geojson_dir, "ne_coastline.geojson")
    lakes_path = os.path.join(geojson_dir, "ne_50m_lakes.geojson")

    coastline_image = np.zeros((height, width), dtype=np.uint8)
    draw_geojson_features(coastline_image, coastline_path, bounds, width, height)

    if DEBUG:
        output_dir = os.path.join(os.path.dirname(__file__), "extracted_texts")
        os.makedirs(output_dir, exist_ok=True)
        cv2.imwrite(os.path.join(output_dir, "coastline_only_raster.png"), coastline_image)

    spaced = detect_sift_keypoints_on_image(coastline_image, apply_edge_detection=True)
    used_lakes = False

    if len(spaced) < NUMBER_OF_KEYPOINTS:
        draw_geojson_features(coastline_image, lakes_path, bounds, width, height)
        used_lakes = True

        if DEBUG:
            cv2.imwrite(
                os.path.join(output_dir, "coastline_with_lakes_raster.png"), coastline_image
            )

        spaced = detect_sift_keypoints_on_image(coastline_image, apply_edge_detection=True)

    if len(spaced) == 0:
        return {"keypoints": [], "total": 0, "used_lakes": used_lakes}

    keypoints = []
    for i, kp in enumerate(spaced):
        px, py = kp.pt
        lon = bounds["west"] + (px / width) * (bounds["east"] - bounds["west"])
        lat = bounds["north"] - (py / height) * (bounds["north"] - bounds["south"])

        keypoints.append(
            {
                "id": i + 1,
                "pixel": {"x": float(px), "y": float(py)},
                "geo": {"lat": lat, "lng": lon},
                "response": float(kp.response),
            }
        )

    if DEBUG:
        img_vis = cv2.cvtColor(coastline_image, cv2.COLOR_GRAY2BGR)
        for i, kp in enumerate(spaced):
            x, y = int(kp.pt[0]), int(kp.pt[1])
            cv2.circle(img_vis, (x, y), 15, (0, 255, 0), 2)
            cv2.circle(img_vis, (x, y), 3, (0, 0, 255), -1)
            cv2.putText(
                img_vis,
                str(i + 1),
                (x + 20, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 0, 0),
                2,
            )

        debug_filename = "with_lakes_keypoints.png" if used_lakes else "coastline_only_keypoints.png"
        keypoints_path = os.path.join(output_dir, debug_filename)
        cv2.imwrite(keypoints_path, img_vis)

    return {"keypoints": keypoints, "total": len(keypoints), "used_lakes": used_lakes}


def _to_png_base64(img: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("Failed to encode debug image as PNG")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _save_sift_debug_images(
    uploaded_keypoints_img: np.ndarray,
    geojson_keypoints_img: np.ndarray,
    matches_img: np.ndarray,
) -> dict[str, str]:
    output_dir = os.path.join(os.path.dirname(__file__), "..", "extracted_texts")
    os.makedirs(output_dir, exist_ok=True)

    run_id = uuid4().hex[:10]
    uploaded_name = f"sift_upload_keypoints_{run_id}.png"
    geojson_name = f"sift_geojson_keypoints_{run_id}.png"
    matches_name = f"sift_matches_{run_id}.png"

    uploaded_path = os.path.join(output_dir, uploaded_name)
    geojson_path = os.path.join(output_dir, geojson_name)
    matches_path = os.path.join(output_dir, matches_name)

    cv2.imwrite(uploaded_path, uploaded_keypoints_img)
    cv2.imwrite(geojson_path, geojson_keypoints_img)
    cv2.imwrite(matches_path, matches_img)

    return {
        "uploaded_keypoints": uploaded_path,
        "geojson_keypoints": geojson_path,
        "matches": matches_path,
    }


def _draw_colored_matches(
    left_gray: np.ndarray,
    left_keypoints,
    right_gray: np.ndarray,
    right_keypoints,
    matches,
    max_matches: Optional[int],
) -> np.ndarray:
    left = cv2.cvtColor(left_gray, cv2.COLOR_GRAY2BGR)
    right = cv2.cvtColor(right_gray, cv2.COLOR_GRAY2BGR)

    h1, w1 = left.shape[:2]
    h2, w2 = right.shape[:2]
    canvas_h = max(h1, h2)
    canvas_w = w1 + w2
    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    canvas[:h1, :w1] = left
    canvas[:h2, w1 : w1 + w2] = right

    palette = [
        (255, 99, 71),
        (60, 179, 113),
        (30, 144, 255),
        (255, 215, 0),
        (218, 112, 214),
        (0, 206, 209),
        (255, 140, 0),
        (127, 255, 0),
    ]

    draw_matches = matches if max_matches is None else matches[:max_matches]
    for i, m in enumerate(draw_matches):
        color = palette[i % len(palette)]
        left_pt = left_keypoints[m.queryIdx].pt
        right_pt = right_keypoints[m.trainIdx].pt

        p1 = (int(left_pt[0]), int(left_pt[1]))
        p2 = (int(right_pt[0] + w1), int(right_pt[1]))

        cv2.circle(canvas, p1, 4, color, -1, cv2.LINE_AA)
        cv2.circle(canvas, p2, 4, color, -1, cv2.LINE_AA)
        cv2.line(canvas, p1, p2, color, 2, cv2.LINE_AA)

    return canvas


def _draw_standard_keypoints(
    gray_img: np.ndarray,
    keypoints,
    color: tuple[int, int, int],
) -> np.ndarray:
    """Draw keypoints with a fixed-size marker for cleaner debug visuals."""
    out = cv2.cvtColor(gray_img, cv2.COLOR_GRAY2BGR)
    for kp in keypoints:
        x, y = int(kp.pt[0]), int(kp.pt[1])
        cv2.circle(out, (x, y), 4, color, -1, cv2.LINE_AA)
        cv2.circle(out, (x, y), 7, color, 1, cv2.LINE_AA)
    return out


def _match_descriptors_robust(
    upload_desc: np.ndarray,
    geo_desc: np.ndarray,
    ratio: float = 0.72,
):
    """
    Build robust matches with mutual ratio test.
    Returns DMatch objects in upload->geo direction.
    """
    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)

    knn_upload_to_geo = bf.knnMatch(upload_desc, geo_desc, k=2)
    knn_geo_to_upload = bf.knnMatch(geo_desc, upload_desc, k=2)

    forward = {}
    backward = {}

    for pair in knn_upload_to_geo:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < ratio * n.distance:
            forward[m.queryIdx] = m

    for pair in knn_geo_to_upload:
        if len(pair) < 2:
            continue
        m, n = pair
        if m.distance < ratio * n.distance:
            backward[m.queryIdx] = m

    mutual = []
    for q_idx, f in forward.items():
        b = backward.get(f.trainIdx)
        if b is not None and b.trainIdx == q_idx:
            mutual.append(f)

    mutual.sort(key=lambda m: m.distance)
    return mutual


def _filter_matches_with_ransac(matches, upload_keypoints, geo_keypoints):
    """Keep only geometrically consistent matches using homography RANSAC."""
    if len(matches) < 4:
        return matches

    src_pts = np.float32([upload_keypoints[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([geo_keypoints[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

    _, inlier_mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 8.0)
    if inlier_mask is None:
        return matches

    inliers = [m for i, m in enumerate(matches) if inlier_mask[i][0] == 1]
    return inliers if inliers else matches


def _filter_matches_with_affine_ransac(matches, upload_keypoints, geo_keypoints):
    """Affine fallback for maps that are not well explained by a homography."""
    if len(matches) < 3:
        return matches

    src_pts = np.float32([upload_keypoints[m.queryIdx].pt for m in matches]).reshape(-1, 2)
    dst_pts = np.float32([geo_keypoints[m.trainIdx].pt for m in matches]).reshape(-1, 2)

    _, inlier_mask = cv2.estimateAffinePartial2D(
        src_pts,
        dst_pts,
        method=cv2.RANSAC,
        ransacReprojThreshold=8.0,
        maxIters=3000,
        confidence=0.99,
        refineIters=10,
    )
    if inlier_mask is None:
        return matches

    inliers = [m for i, m in enumerate(matches) if inlier_mask[i][0] == 1]
    return inliers if inliers else matches


def _decode_uploaded_image_to_gray(image_bytes: bytes) -> np.ndarray:
    upload_np = np.frombuffer(image_bytes, dtype=np.uint8)
    upload_bgr = cv2.imdecode(upload_np, cv2.IMREAD_COLOR)
    if upload_bgr is None:
        raise ValueError("Could not decode uploaded image")
    gray = cv2.cvtColor(upload_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def find_coastline_sift_matches_debug(
    image_bytes: bytes,
    bounds: dict,
    width: Optional[int] = None,
    height: Optional[int] = None,
    max_matches: Optional[int] = None,
) -> dict[str, Any]:
    """
    Build coastline/lakes edge image from bounds, match SIFT points against uploaded image,
    and return debug visuals and match metadata.
    """
    upload_gray = _decode_uploaded_image_to_gray(image_bytes)
    upload_h, upload_w = upload_gray.shape[:2]

    target_w = int(width) if width and width > 0 else upload_w
    target_h = int(height) if height and height > 0 else upload_h

    if (target_w, target_h) != (upload_w, upload_h):
        upload_gray = cv2.resize(upload_gray, (target_w, target_h), interpolation=cv2.INTER_AREA)

    geojson_dir = os.path.join(os.path.dirname(__file__), "..", "geojson")
    coastline_path = os.path.join(geojson_dir, "ne_coastline.geojson")
    lakes_path = os.path.join(geojson_dir, "ne_50m_lakes.geojson")

    geo_edge = np.zeros((target_h, target_w), dtype=np.uint8)
    draw_geojson_features(geo_edge, coastline_path, bounds, target_w, target_h)

    def _detect_geo_features(mask: np.ndarray):
        # Primary mode: Canny-assisted detection (same family as legacy behavior).
        kps, desc = detect_sift_keypoints_and_descriptors_on_image(
            mask,
            apply_edge_detection=True,
            max_keypoints=None,
            min_distance=3,
        )

        # Fallback 1: Direct SIFT on the rasterized mask (no Canny).
        if len(kps) < 8:
            kps, desc = detect_sift_keypoints_and_descriptors_on_image(
                mask,
                apply_edge_detection=False,
                max_keypoints=None,
                min_distance=2,
            )

        # Fallback 2: Slightly thicken linework, then run direct SIFT.
        if len(kps) < 8:
            kernel = np.ones((3, 3), dtype=np.uint8)
            thick_mask = cv2.dilate(mask, kernel, iterations=1)
            kps, desc = detect_sift_keypoints_and_descriptors_on_image(
                thick_mask,
                apply_edge_detection=False,
                max_keypoints=None,
                min_distance=1,
            )

        return kps, desc

    geo_keypoints, geo_desc = _detect_geo_features(geo_edge)

    used_lakes = False
    if len(geo_keypoints) < 20:
        draw_geojson_features(geo_edge, lakes_path, bounds, target_w, target_h)
        used_lakes = True
        geo_keypoints, geo_desc = _detect_geo_features(geo_edge)

    upload_keypoints, upload_desc = detect_sift_keypoints_and_descriptors_on_image(
        upload_gray,
        apply_edge_detection=True,
        max_keypoints=2000,
        min_distance=6,
    )

    upload_vis = _draw_standard_keypoints(upload_gray, upload_keypoints, (0, 255, 0))
    geo_vis = _draw_standard_keypoints(geo_edge, geo_keypoints, (255, 140, 0))

    if (
        upload_desc is None
        or geo_desc is None
        or len(upload_keypoints) == 0
        or len(geo_keypoints) == 0
    ):
        empty_matches = np.zeros(
            (
                max(upload_vis.shape[0], geo_vis.shape[0]),
                upload_vis.shape[1] + geo_vis.shape[1],
                3,
            ),
            dtype=np.uint8,
        )
        empty_matches[: upload_vis.shape[0], : upload_vis.shape[1]] = upload_vis
        empty_matches[: geo_vis.shape[0], upload_vis.shape[1] :] = geo_vis
        saved_images = _save_sift_debug_images(upload_vis, geo_vis, empty_matches)
        print("NUMBER OF MATCHES = 0")

        return {
            "used_lakes": used_lakes,
            "uploaded_keypoints_total": len(upload_keypoints),
            "geojson_keypoints_total": len(geo_keypoints),
            "matches_total": 0,
            "match_points": [],
            "saved_images": saved_images,
            "images": {
                "uploaded_keypoints": _to_png_base64(upload_vis),
                "geojson_keypoints": _to_png_base64(geo_vis),
                "matches": _to_png_base64(empty_matches),
            },
        }

    good_matches = _match_descriptors_robust(upload_desc, geo_desc, ratio=0.72)

    # If strict matching is too sparse, relax ratio slightly to recover candidates.
    if len(good_matches) < 8:
        good_matches = _match_descriptors_robust(upload_desc, geo_desc, ratio=0.82)

    inlier_matches = _filter_matches_with_ransac(
        good_matches,
        upload_keypoints,
        geo_keypoints,
    )

    # Historical maps often deform locally; affine RANSAC can recover usable inliers.
    if len(inlier_matches) < 6 and len(good_matches) >= 3:
        affine_inliers = _filter_matches_with_affine_ransac(
            good_matches,
            upload_keypoints,
            geo_keypoints,
        )
        if len(affine_inliers) > len(inlier_matches):
            inlier_matches = affine_inliers

    if max_matches is None:
        selected_matches = sorted(inlier_matches, key=lambda m: m.distance)
    else:
        selected_matches = sorted(inlier_matches, key=lambda m: m.distance)[:max_matches]

    print(f"NUMBER OF MATCHES = {len(selected_matches)}")

    match_vis = _draw_colored_matches(
        upload_gray,
        upload_keypoints,
        geo_edge,
        geo_keypoints,
        selected_matches,
        max_matches=max_matches,
    )

    match_points = []
    for i, m in enumerate(selected_matches):
        upload_pt = upload_keypoints[m.queryIdx].pt
        geo_pt = geo_keypoints[m.trainIdx].pt
        match_points.append(
            {
                "id": i + 1,
                "upload_pixel": {"x": float(upload_pt[0]), "y": float(upload_pt[1])},
                "geojson_pixel": {"x": float(geo_pt[0]), "y": float(geo_pt[1])},
                "distance": float(m.distance),
            }
        )

    saved_images = _save_sift_debug_images(upload_vis, geo_vis, match_vis)

    return {
        "used_lakes": used_lakes,
        "uploaded_keypoints_total": len(upload_keypoints),
        "geojson_keypoints_total": len(geo_keypoints),
        "raw_matches_total": len(good_matches),
        "inlier_matches_total": len(inlier_matches),
        "matches_total": len(selected_matches),
        "match_points": match_points,
        "saved_images": saved_images,
        "images": {
            "uploaded_keypoints": _to_png_base64(upload_vis),
            "geojson_keypoints": _to_png_base64(geo_vis),
            "matches": _to_png_base64(match_vis),
        },
    }
