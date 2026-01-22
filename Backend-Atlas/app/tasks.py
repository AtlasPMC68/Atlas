import cv2
from celery import current_task
from .celery_app import celery_app
import time
import asyncio
import logging
import os
import tempfile
import time
import re
from datetime import datetime
from typing import Any, List
from uuid import UUID
from PIL import Image, ImageEnhance

from app.database.session import AsyncSessionLocal
from app.services.features import insert_feature_in_db
from app.utils.color_extraction import extract_colors
from app.utils.text_extraction import extract_text
from app.utils.shapes_extraction import extract_shapes
from app.utils.cities_validation import detect_cities_from_text, find_first_city
from app.utils.georeferencing import georeference_pixel_features
import numpy as np

from .celery_app import celery_app

logger = logging.getLogger(__name__)

nb_task = 6


@celery_app.task(bind=True)
def test_task(self, name: str = "World"):
    """simple test task"""
    logger.info(f"Starting test task for {name}")

    for i in range(5):
        time.sleep(1)
        self.update_state(
            state="PROGRESS",
            meta={
                "current": i + 1,
                "total": nb_task,
                "status": f"Processing step {i + 1}",
            },
        )

    result = f"Hello {name}! Task completed successfully."
    logger.info(f"Test task completed: {result}")
    return result

def bottom_edge_polyline_px(image_bytes: bytes, samples: int = 20):
    # Decode image from bytes
    img_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)  # BGR

    if img is None:
        raise ValueError("Could not read image")

    # 1) Mask the blue hexagon (simple threshold in HSV)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Blue range (adjust if needed)
    lower = np.array([90, 50, 50])
    upper = np.array([140, 255, 255])
    mask = cv2.inRange(hsv, lower, upper)

    # Clean up
    mask = cv2.medianBlur(mask, 5)

    # 2) Find the contour
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        raise ValueError("No contour found")

    cnt = max(cnts, key=cv2.contourArea)

    # 3) Approx to polygon vertices
    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)  # tweak 0.02 if needed
    pts = approx.reshape(-1, 2)  # (N,2) as [x,y]

    if len(pts) < 4:
        raise ValueError(f"Polygon approximation too small: {len(pts)} vertices")

    # Ensure consistent ordering around the shape
    # Sort by angle around centroid
    cx, cy = pts.mean(axis=0)
    angles = np.arctan2(pts[:,1] - cy, pts[:,0] - cx)
    pts = pts[np.argsort(angles)]

    # 4) Find the bottom-most edge (edge with max average y)
    best_edge = None
    best_score = -1
    n = len(pts)
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        score = (a[1] + b[1]) / 2.0  # avg y
        if score > best_score:
            best_score = score
            best_edge = (a, b)

    (x1, y1), (x2, y2) = best_edge

    # 5) Build a polyline along that edge (sample points)
    xs = np.linspace(x1, x2, samples)
    ys = np.linspace(y1, y2, samples)
    polyline = [(float(x), float(y)) for x, y in zip(xs, ys)]

    return {
        "edge_endpoints": [(int(x1), int(y1)), (int(x2), int(y2))],
        "polyline_px": polyline,
        "vertices_px": pts.tolist(),
    }

# Example usage:
# result = bottom_edge_polyline_px("hex.png", samples=10)
# print(result["edge_endpoints"])
# print(result["polyline_px"])



@celery_app.task(bind=True)
def process_map_extraction(
    self,
    filename: str,
    file_content: bytes,
    map_id: str,
    pixel_control_polyline: list | None = None,
    geo_control_polyline: list | None = None,
    pixel_points: list | None = None,
    geo_points_lonlat: list | None = None,
):
    """"""
    logger.info(f"Starting map processing for {filename}")

    # Ensure we are working with a UUID instance inside the task
    map_uuid = UUID(map_id)

    logger.info(
        f"[DEBUG] Georef input types: pixel_polyline[0]={type(pixel_control_polyline[0])}, geo_polyline[0]={type(geo_control_polyline[0])}"
    )
    logger.info(
        f"[DEBUG] First pixel point: {pixel_control_polyline[0]}, first geo point: {geo_control_polyline[0]}"
    )

    try:
        # Step 1: temp save
        self.update_state(
            state="PROGRESS",
            meta={"current": 1, "total": nb_task, "status": "Saving uploaded file"},
        )
        logger.info("Before sleep")
        time.sleep(2)
        logger.info("afternoon")
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(filename)[1]
        ) as tmp_file:
            tmp_file.write(file_content)
            tmp_file_path = tmp_file.name

        # Step 2: opening the picture
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 2,
                "total": nb_task,
                "status": "Loading and validating image",
            },
        )
        time.sleep(2)

        image = cv2.imread(tmp_file_path)
        image.flags.writeable = False # Makes image immutable
        validate_file_extension(tmp_file_path)

        # # Step 3: Extraction OCR
        # self.update_state(
        #     state="PROGRESS",
        #     meta={
        #         "current": 3,
        #         "total": nb_task,
        #         "status": "Extracting text with EasyOCR",
        #     },
        # )
        # time.sleep(2)

        # # GPU acceleration make the text extraction MUCH faster i
        # extracted_text, clean_image = extract_text(image=image, languages=['en', 'fr'], gpu_acc=False)

        # # TODO : Amener ca dans la fonction de detection de texte ===========================================================
        # # Tokenize OCR text to single words and run city detection per token
        # try:
        #     tokens = re.findall(r"\b[\w\-']+\b", extracted_text or "")
        #     for tok in tokens:
        #         try:
        #             candidate = find_first_city(tok)
        #         except Exception as e:
        #             logger.debug(f"find_first_city error for token '{tok}': {e}")
        #             # treat as not found but persist the token
        #             candidate = {"found": False, "query": tok, "name": tok, "lat": 0.0, "lon": 0.0}

        #         # Build feature using returned candidate; if not found, coordinates will be 0,0
        #         logger.info(f"City detection result for token '{tok}': {candidate}")
        #         city_feature = {
        #             "type": "Feature",
        #             "properties": {
        #                 "name": candidate.get("name") or tok,
        #                 "show": bool(candidate.get("found")),
        #                 "mapElementType": "point",
        #                 "color_name": "black",
        #                 "color_rgb": [0, 0, 0],
        #                 "start_date": "0-01-01",
        #                 "end_date": "5000-01-01",
        #             },
        #             "geometry": {"type": "Point", "coordinates": [candidate.get("lon") or 0.0, candidate.get("lat") or 0.0]},
        #         }

        #         city_feature_collection = {
        #             "type": "FeatureCollection",
        #             "features": [city_feature],
        #         }

        #         try:
        #             asyncio.run(persist_city_feature(map_uuid, city_feature_collection))
        #             logger.info(f"Persisted city token feature: {candidate.get('name')}")
        #         except Exception as e:
        #             logger.error(f"Failed to persist city token '{tok}': {e}")

        # except Exception as e:
        #     logger.error(f"City detection failed: {e}")

        # TODO : Amener ca dans la fonction de detection de texte ===========================================================

        # Step 4: Color Extraction
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 4,
                "total": nb_task,
                "status": "Extracting colors from image",
            },
        )
        time.sleep(2)

        color_result = extract_colors(tmp_file_path)
        normalized_features = color_result["normalized_features"]
        pixel_features = color_result["pixel_features"]

        # Persist normalized (0-1 box) features as before
        asyncio.run(persist_features(map_uuid, normalized_features))
        logger.info(
            f"[DEBUG] Résultat color_extraction : {color_result['colors_detected']}"
        )

        # Optional: georeference pixel-space features if control polylines are provided
        if pixel_control_polyline and geo_control_polyline:
            logger.info(
                f"[DEBUG] Georef input types: pixel_polyline[0]={type(pixel_control_polyline[0])}, geo_polyline[0]={type(geo_control_polyline[0])}"
            )
            logger.info(
                f"[DEBUG] First pixel point: {pixel_control_polyline[0]}, first geo point: {geo_control_polyline[0]}"
            )
            try:
                georef_features = georeference_pixel_features(
                    pixel_features,
                    pixel_control_polyline,
                    geo_control_polyline,
                    pixel_points,
                    geo_points_lonlat
                )
                if georef_features:
                    asyncio.run(persist_features(map_uuid, georef_features))
                    logger.info(
                        f"[DEBUG] Persisted {len(georef_features)} georeferenced feature collections for map {map_uuid}"
                    )
            except Exception as e:
                logger.error(f"Georeferencing step failed for map {map_uuid}: {e}")

        # Step 5: Shapes Extraction
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 5,
                "total": nb_task,
                "status": "Extracting shapes from image",
            },
        )
        time.sleep(2)
        shapes_result = extract_shapes(tmp_file_path)
        logger.info(f"[DEBUG] Résultat shapes_extraction : {shapes_result}")

        # Step 6: Cleanning
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 5,
                "total": nb_task,
                "status": "Cleaning up and finalizing",
            },
        )
        time.sleep(2)
        os.unlink(tmp_file_path)

        current_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(current_dir, "extracted_texts")
        try:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"[DEBUG] Directory created or already exists: {output_dir}")
        except Exception as e:
            logger.error(f"[ERROR] Failed to create directory {output_dir}: {e}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(filename)[0]
        output_filename = f"{timestamp}_{base_name}.txt"
        output_path = os.path.join(output_dir, output_filename)

        #lines = [block[1] for block in extracted_text]
        #full_text = "\n".join(lines)
        # try:
        #     with open(output_path, 'w', encoding='utf-8') as f:
        #         f.write(f"=== OCR EXTRACTION  ===\n")
        #         f.write(f"Source File: {filename}\n")
        #         f.write(f"Date extraction: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        #         f.write(f"\n=== TEXTE EXTRAIT ===\n\n")
        # #         f.write(full_text)

        #     logger.info(f"Text saved to: {output_path}")

        # except Exception as e:
        #     logger.error(f"Failed to save text file: {str(e)}")
        #     output_path = f"ERROR: Could not save to {output_path}"

        result = {
            "filename": filename,
            # "extracted_text": lines,
            "output_path": output_path,
            "shapes_result": shapes_result,
            "color_result": color_result,
            "status": "completed",
        }

        # logger.info(
        #     f"Map processing completed for {filename}: {len(extracted_text)} characters extracted"
        # )

        return result

    except Exception as e:
        if "tmp_file_path" in locals():
            try:
                os.unlink(tmp_file_path)
            except:
                pass

        logger.error(f"Error processing map {filename}: {str(e)}")
        raise e

def validate_file_extension(file_path: str) -> None:
    supported_file_ext = ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp', '.ppm', '.pgm', '.pbm')
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in supported_file_ext:
        raise ValueError(f"Extension {ext} non autorisée pour le système du consortium.")


async def persist_features(map_uuid: UUID, normalized_features: List[dict[str, Any]]):
    async with AsyncSessionLocal() as db:
        for feature in normalized_features:
            try:
                await insert_feature_in_db(
                    db=db,
                    map_id=map_uuid,
                    is_feature_collection=True,
                    data=feature,
                )
            except Exception as e:
                logger.error(f"Failed to persist feature for map {map_uuid}: {str(e)}")


async def persist_city_feature(map_uuid: UUID, feature: dict[str, Any]):
    async with AsyncSessionLocal() as db:
        try:
            await insert_feature_in_db(
                db=db,
                map_id=map_uuid,
                is_feature_collection=False,
                data=feature,
            )
        except Exception as e:
            logger.error(f"Failed to persist city feature for map {map_uuid}: {str(e)}")
