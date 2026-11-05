# region Imports
import logging
import mimetypes
import os
import uuid as uuid_module
from typing import Any, Dict
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.database.session import get_async_session
from app.models.map import Map
from app.models.map_import import (
    EXTRACTION_CANCELLED,
    EXTRACTION_CANCELLING,
    EXTRACTION_FAILED,
    EXTRACTION_QUEUED,
    EXTRACTION_RUNNING,
    EXTRACTION_WAITING_FOR_TEXT,
    OCR_DONE,
    OCR_FAILED,
    OCR_PENDING,
    MapImport,
)
from app.services.imports import (
    apply_inputs_patch,
    delete_stale_imports,
    get_import,
    get_owned_map,
    is_extraction_active,
    missing_inputs,
    parse_import_inputs,
)
from app.tasks import process_map_extraction, run_map_ocr
from app.utils.auth import get_current_user_id
from app.utils.file_utils import ALLOWED_EXTENSIONS, MAX_FILE_SIZE
# endregion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/imports", tags=["Map import"])
REFERENCE_IMAGE_CONTENT_TYPES = {
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}

MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/app/media")
REFERENCE_IMAGES_DIR = os.path.join(MEDIA_ROOT, "reference_images")


@router.get("/{map_id}/reference-image")
async def get_reference_image(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    map_obj = await _require_owned_map(session, map_id, user_id)
    if not map_obj.reference_image_path:
        raise HTTPException(status_code=404, detail="No reference image for this map")
    abs_path = os.path.join(MEDIA_ROOT, map_obj.reference_image_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Reference image file not found")
    media_type = map_obj.reference_image_content_type or "application/octet-stream"
    # Stream the file
    return FileResponse(abs_path, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.put("/{map_id}/reference-image")
async def save_reference_image(
    map_id: UUID,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    map_obj = await _require_owned_map(session, map_id, user_id)
    content_type = (file.content_type or "").lower()
    if content_type not in REFERENCE_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported reference image type")
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    # Read in chunks to avoid loading 25MB into memory at once
    chunk_size = 1024 * 256  # 256 KB chunks
    os.makedirs(REFERENCE_IMAGES_DIR, exist_ok=True)
    ext = mimetypes.guess_extension(content_type) or ".bin"
    # Normalize common extensions
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
               "image/gif": ".gif", "image/avif": ".avif"}
    ext = ext_map.get(content_type, ext)
    filename = f"{map_id}{ext}"
    abs_path = os.path.join(REFERENCE_IMAGES_DIR, filename)
    rel_path = os.path.join("reference_images", filename)
    total = 0
    # Delete old file if exists
    old_path = None
    if map_obj.reference_image_path:
        old_path = os.path.join(MEDIA_ROOT, map_obj.reference_image_path)
    try:
        with open(abs_path, "wb") as out:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    out.close()
                    os.unlink(abs_path)
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(abs_path):
            os.unlink(abs_path)
        raise HTTPException(status_code=500, detail=f"Could not save reference image: {e}")
    if total == 0:
        os.unlink(abs_path)
        raise HTTPException(status_code=400, detail="Empty reference image")
    # Delete old file after successful write
    if old_path and old_path != abs_path and os.path.isfile(old_path):
        try:
            os.unlink(old_path)
        except OSError:
            pass
    map_obj.reference_image_path = rel_path
    map_obj.reference_image_content_type = content_type
    await session.commit()
    return {"detail": "Reference image saved"}


@router.delete("/{map_id}/reference-image")
async def delete_reference_image(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    map_obj = await _require_owned_map(session, map_id, user_id)
    if map_obj.reference_image_path:
        abs_path = os.path.join(MEDIA_ROOT, map_obj.reference_image_path)
        if os.path.isfile(abs_path):
            try:
                os.unlink(abs_path)
            except OSError:
                pass
    map_obj.reference_image_path = None
    map_obj.reference_image_content_type = None
    await session.commit()
    return {"detail": "Reference image deleted"}


def _task_progress(task_id: str | None) -> Dict[str, Any]:
    if not task_id:
        return {"progress": 0, "status": ""}
    info = celery_app.AsyncResult(task_id).info
    if not isinstance(info, dict):
        return {"progress": 0, "status": ""}
    current = info.get("current", 0)
    total = info.get("total", 1) or 1
    return {
        "progress": round(current / total * 100, 2),
        "status": info.get("status", ""),
    }


def _import_out(row: MapImport, map_obj: Map) -> Dict[str, Any]:
    extraction: Dict[str, Any] = {
        "state": row.extraction_state,
        "taskId": row.extraction_task_id,
        "error": row.extraction_error,
        "progress": 0,
        "status": "",
    }
    if row.extraction_state == EXTRACTION_RUNNING:
        extraction.update(_task_progress(row.extraction_task_id))

    return {
        "mapId": str(row.map_id),
        "projectId": str(map_obj.project_id),
        "mapTitle": map_obj.title,
        "filename": row.filename,
        "inputs": row.inputs or {},
        "ocr": {"state": row.ocr_state},
        "extraction": extraction,
    }


async def _require_owned_map(
    session: AsyncSession, map_id: UUID, user_id: str
) -> Map:
    try:
        user_uuid = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid user")
    map_obj = await get_owned_map(session, map_id, user_uuid)
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found or access denied")
    return map_obj


async def _require_import(
    session: AsyncSession, map_id: UUID, *, for_update: bool = False
) -> MapImport:
    row = await get_import(session, map_id, for_update=for_update)
    if row is None:
        raise HTTPException(status_code=404, detail="No import in progress for this map")
    return row


@router.post("")
async def create_import(
    map_id: UUID = Form(...),
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """Store the image and start OCR right away."""
    map_obj = await _require_owned_map(session, map_id, user_id)

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    # Checked before reading, so an oversized file is not loaded into memory.
    # The upload itself has already arrived by now; capping that belongs to
    # the reverse proxy in front of the API.
    if file.size is not None and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    if await get_import(session, map_id):
        raise HTTPException(
            status_code=409, detail="An import is already in progress for this map"
        )

    await delete_stale_imports(session)
    ocr_task_id = str(uuid4())
    row = MapImport(
        map_id=map_id,
        image=content,
        filename=filename,
        inputs={},
        ocr_state=OCR_PENDING,
        ocr_task_id=ocr_task_id,
    )
    session.add(row)
    await session.commit()

    try:
        run_map_ocr.apply_async(kwargs={"map_id": str(map_id)}, task_id=ocr_task_id)
    except Exception as e:
        # Marked failed rather than left pending with no task behind it:
        # starting the extraction retries a failed OCR.
        logger.error(f"[IMPORT] Could not dispatch OCR for {map_id}: {e}")
        row = await _require_import(session, map_id, for_update=True)
        row.ocr_state = OCR_FAILED
        await session.commit()
        return _import_out(row, map_obj)
    logger.info(f"[IMPORT] import created for map {map_id}; OCR task {ocr_task_id}")
    return _import_out(row, map_obj)


@router.get("/{map_id}")
async def get_import_state(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    map_obj = await _require_owned_map(session, map_id, user_id)
    row = await _require_import(session, map_id)
    return _import_out(row, map_obj)


@router.get("/{map_id}/image")
async def get_import_image(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    await _require_owned_map(session, map_id, user_id)
    row = await _require_import(session, map_id)
    media_type = mimetypes.guess_type(row.filename)[0] or "application/octet-stream"
    return Response(content=row.image, media_type=media_type)


@router.put("/{map_id}/inputs")
async def update_import_inputs(
    map_id: UUID,
    patch: Dict[str, Any] = Body(...),
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """Merge the given entries into the saved ones. ``null`` clears one."""
    map_obj = await _require_owned_map(session, map_id, user_id)
    row = await _require_import(session, map_id, for_update=True)
    if is_extraction_active(row):
        raise HTTPException(
            status_code=409,
            detail="Extraction in progress: cancel it before changing the inputs",
        )
    try:
        row.inputs = apply_inputs_patch(row.inputs, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid inputs: {e}")
    await session.commit()
    return _import_out(row, map_obj)


@router.post("/{map_id}/extract")
async def start_extraction(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """Start the extraction now if the text is ready, else queue it behind OCR."""
    map_obj = await _require_owned_map(session, map_id, user_id)
    row = await _require_import(session, map_id, for_update=True)
    if is_extraction_active(row):
        raise HTTPException(status_code=409, detail="Extraction already in progress")

    missing = missing_inputs(parse_import_inputs(row.inputs))
    if missing:
        raise HTTPException(
            status_code=400, detail="Étapes manquantes : " + ", ".join(missing)
        )

    row.extraction_error = None
    ocr_to_send = None
    extraction_to_send = None
    if row.ocr_state == OCR_DONE:
        extraction_to_send = str(uuid4())
        row.extraction_task_id = extraction_to_send
        row.extraction_state = EXTRACTION_QUEUED
    else:
        # Known gap: an OCR task whose worker died leaves ocr_state at
        # "running" for good. It is neither done nor failed, so it is not
        # retried below: the extraction waits for text that never comes, and
        # only cancelling, or abandoning the import, gets the user out. Fixing
        # it needs a way to tell a dead OCR task from a slow one (a heartbeat
        # or a started-at timeout).
        if row.ocr_state == OCR_FAILED:
            # A failed OCR is retried rather than leaving the import stuck.
            ocr_to_send = str(uuid4())
            row.ocr_task_id = ocr_to_send
            row.ocr_state = OCR_PENDING
        row.extraction_task_id = None
        row.extraction_state = EXTRACTION_WAITING_FOR_TEXT
    await session.commit()

    # Sent after the commit, so a task never starts before the state it checks.
    if ocr_to_send:
        run_map_ocr.apply_async(kwargs={"map_id": str(map_id)}, task_id=ocr_to_send)
    if extraction_to_send:
        try:
            process_map_extraction.apply_async(
                kwargs={"map_id": str(map_id)}, task_id=extraction_to_send
            )
        except Exception as e:
            logger.error(f"[IMPORT] Could not dispatch extraction for {map_id}: {e}")
            row = await _require_import(session, map_id, for_update=True)
            row.extraction_state = EXTRACTION_FAILED
            row.extraction_error = "Impossible de lancer l'extraction"
            await session.commit()
            raise HTTPException(status_code=500, detail="Failed to start extraction")

    return _import_out(row, map_obj)


@router.post("/{map_id}/cancel")
async def cancel_extraction(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """Stop the extraction. The user's entries and the OCR result are kept."""
    map_obj = await _require_owned_map(session, map_id, user_id)
    row = await _require_import(session, map_id, for_update=True)

    if row.extraction_state in (EXTRACTION_WAITING_FOR_TEXT, EXTRACTION_QUEUED):
        if row.extraction_task_id:
            celery_app.control.revoke(row.extraction_task_id)
        row.extraction_state = EXTRACTION_CANCELLED
    elif row.extraction_state == EXTRACTION_RUNNING:
        row.extraction_state = EXTRACTION_CANCELLING
    elif row.extraction_state == EXTRACTION_CANCELLING:
        # A second cancel. The running task normally moves the row from
        # cancelling to cancelled at its next check; when the worker died
        # mid-run nothing ever will, and an active row refuses new inputs and
        # a new extraction. Close it here so the import is usable again. The
        # task, if it is alive after all, finds the state changed and saves
        # nothing.
        if row.extraction_task_id:
            celery_app.control.revoke(row.extraction_task_id)
        row.extraction_state = EXTRACTION_CANCELLED
    await session.commit()
    return _import_out(row, map_obj)


@router.delete("/{map_id}")
async def abandon_import(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """Drop the import, to start over with another file."""
    await _require_owned_map(session, map_id, user_id)
    row = await _require_import(session, map_id, for_update=True)
    if row.ocr_task_id and row.ocr_state != OCR_DONE:
        celery_app.control.revoke(row.ocr_task_id, terminate=True)
    if row.extraction_task_id and is_extraction_active(row):
        celery_app.control.revoke(row.extraction_task_id)
    await session.delete(row)
    await session.commit()
    return {"detail": "Import abandoned"}
