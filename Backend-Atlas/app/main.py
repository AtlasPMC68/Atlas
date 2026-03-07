import os
import json
from uuid import uuid4
from datetime import datetime

from fastapi import FastAPI, Body, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routers import celery_router
from .routers import auth
from .routers import maps
from .routers import user

app = FastAPI(
    title="Maps Processing API",
    description="API pour traitement et analyse de cartes historiques",
    version="0.1.0",
)
app.include_router(celery_router.router)
app.include_router(maps.router)
app.include_router(auth.router)
app.include_router(user.router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve test assets (images, GeoJSON, etc.) as static files under /dev-test
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
TEST_ASSETS_DIR = os.path.join(ROOT_DIR, "tests", "assets")
ZONES_DIR = os.path.join(TEST_ASSETS_DIR, "georef_zones")
MAPS_DIR = os.path.join(TEST_ASSETS_DIR, "maps")
TESTS_METADATA_PATH = os.path.join(TEST_ASSETS_DIR, "tests_metadata.json")

if os.path.isdir(TEST_ASSETS_DIR):
    app.mount("/dev-test", StaticFiles(directory=TEST_ASSETS_DIR), name="dev-test")


@app.put("/dev-test-api/georef_zones/{map_id}")
async def save_dev_test_zones(map_id: str, payload: dict = Body(...)):
    """Save or overwrite the dev-test zones GeoJSON file for a given map.

    This is used only by the internal test editor UI.
    """

    os.makedirs(ZONES_DIR, exist_ok=True)
    zones_output_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")

    with open(zones_output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "map_id": map_id}


@app.get("/dev-test-api/georef_zones/{map_id}")
async def get_dev_test_zones(map_id: str):
    """Return the current dev-test zones GeoJSON for a given map.

    This mirrors the static file under /dev-test/georef_zones but avoids any
    browser caching issues by serving it via the API layer.
    """

    zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
    if not os.path.exists(zones_path):
        raise HTTPException(status_code=404, detail="Zones file not found")

    with open(zones_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data


@app.get("/dev-test-api/tests")
async def list_dev_tests():
    """List available dev tests based on files in tests/assets/maps.

    Each test corresponds to an image file whose stem is the map_id.
    If metadata exists in tests_metadata.json, use it to enrich the response.
    """

    if not os.path.isdir(MAPS_DIR):
        return []

    # Load optional metadata file
    metadata: dict[str, dict] = {}
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                if isinstance(meta_data, dict):
                    metadata = meta_data
        except Exception:
            # Ignore corrupted metadata in dev-only context
            metadata = {}

    tests = []
    for filename in os.listdir(MAPS_DIR):
        # Basic filter for image files
        if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
            continue

        map_id, _ext = os.path.splitext(filename)
        meta_entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}

        zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
        has_zones = os.path.exists(zones_path)

        tests.append(
            {
                "mapId": map_id,
                "name": meta_entry.get("name") or map_id,
                "imageFilename": filename,
                "hasZones": has_zones,
                "createdAt": meta_entry.get("createdAt"),
            }
        )

    # Sort by creation time if available, otherwise by filename
    tests.sort(key=lambda t: (t.get("createdAt") or "", t["imageFilename"]))
    return tests


@app.post("/dev-test-api/tests")
async def register_dev_test(payload: dict = Body(...)):
    """Register or update metadata for a dev test.

    Expects a JSON body with at least {"mapId": str, "name": str}.
    """

    map_id = payload.get("mapId")
    name = payload.get("name")
    if not map_id or not isinstance(map_id, str):
        raise HTTPException(status_code=400, detail="mapId is required")
    if not name or not isinstance(name, str):
        raise HTTPException(status_code=400, detail="name is required")

    # Load existing metadata
    metadata: dict[str, dict] = {}
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                if isinstance(meta_data, dict):
                    metadata = meta_data
        except Exception:
            metadata = {}

    entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}
    entry["name"] = name
    entry.setdefault("createdAt", datetime.utcnow().isoformat() + "Z")
    metadata[map_id] = entry

    os.makedirs(os.path.dirname(TESTS_METADATA_PATH), exist_ok=True)
    with open(TESTS_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "mapId": map_id, "name": name}


@app.post("/dev-test-api/tests/upload")
async def upload_dev_test(
    file: UploadFile = File(...),
    name: str = Form(...),
):
    """Create a dev test by saving the map image and metadata.

    - Saves the uploaded image into tests/assets/maps.
    - Generates a mapId (UUID).
    - Registers the test name in tests_metadata.json.
    """

    os.makedirs(MAPS_DIR, exist_ok=True)

    original_filename = file.filename or "map"
    _base, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ".jpg"

    map_id = str(uuid4())
    image_filename = f"{map_id}{ext}"
    dest_path = os.path.join(MAPS_DIR, image_filename)

    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)

    # Update metadata (reuse same format as register_dev_test)
    metadata: dict[str, dict] = {}
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                if isinstance(meta_data, dict):
                    metadata = meta_data
        except Exception:
            metadata = {}

    entry = metadata.get(map_id, {}) if isinstance(metadata, dict) else {}
    entry["name"] = name
    entry.setdefault("createdAt", datetime.utcnow().isoformat() + "Z")
    metadata[map_id] = entry

    os.makedirs(os.path.dirname(TESTS_METADATA_PATH), exist_ok=True)
    with open(TESTS_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return {
        "status": "ok",
        "mapId": map_id,
        "name": name,
        "imageFilename": image_filename,
    }


@app.delete("/dev-test-api/tests/{map_id}")
async def delete_dev_test(map_id: str):
    """Delete a dev test: image file, zones GeoJSON, and metadata entry.

    This is a best-effort operation for the internal test browser.
    """

    # Delete image file matching the map_id stem
    if os.path.isdir(MAPS_DIR):
        for filename in os.listdir(MAPS_DIR):
            stem, _ext = os.path.splitext(filename)
            if stem == map_id:
                try:
                    os.remove(os.path.join(MAPS_DIR, filename))
                except OSError:
                    pass
                break

    # Delete zones file if it exists
    zones_path = os.path.join(ZONES_DIR, f"{map_id}_zones.geojson")
    if os.path.exists(zones_path):
        try:
            os.remove(zones_path)
        except OSError:
            pass

    # Remove metadata entry
    if os.path.exists(TESTS_METADATA_PATH):
        try:
            with open(TESTS_METADATA_PATH, "r", encoding="utf-8") as f:
                meta_data = json.load(f)
                metadata: dict[str, dict] = (
                    meta_data if isinstance(meta_data, dict) else {}
                )
        except Exception:
            metadata = {}

        if map_id in metadata:
            del metadata[map_id]
            try:
                with open(TESTS_METADATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    return {"status": "ok", "mapId": map_id}


@app.get("/")
def read_root():
    return {"message": "Maps Processing API", "status": "running"}


@app.get("/ping")
def ping():
    return {"message": "pong"}
