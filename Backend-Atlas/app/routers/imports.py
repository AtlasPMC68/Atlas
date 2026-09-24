"""The import of a map: upload, the user's entries, extraction, cancellation.

    POST   /imports                      upload the image; OCR starts at once
    GET    /imports/{map_id}             entries and task states, for a reload
    GET    /imports/{map_id}/image       the uploaded image
    PUT    /imports/{map_id}/inputs      save entries as each step is confirmed
    POST   /imports/{map_id}/extract     start extraction, or queue it behind OCR
    POST   /imports/{map_id}/cancel      stop an extraction; nothing is saved
    DELETE /imports/{map_id}             abandon the import (another file)

The row disappears when the extraction saves its features, so a 404 on a map
whose extraction was running means it finished.
"""

import logging
import mimetypes
from typing import Any, Dict
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/imports", tags=["Map import"])


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


async def _owned_map_or_404(
    session: AsyncSession, map_id: UUID, user_id: str
) -> Map:
    map_obj = await get_owned_map(session, map_id, UUID(user_id))
    if not map_obj:
        raise HTTPException(status_code=404, detail="Map not found or access denied")
    return map_obj


async def _import_or_404(
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
    map_obj = await _owned_map_or_404(session, map_id, user_id)

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"File type not supported. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
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

    run_map_ocr.apply_async(kwargs={"map_id": str(map_id)}, task_id=ocr_task_id)
    logger.info(f"[IMPORT] import created for map {map_id}; OCR task {ocr_task_id}")
    return _import_out(row, map_obj)


@router.get("/{map_id}")
async def get_import_state(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    map_obj = await _owned_map_or_404(session, map_id, user_id)
    row = await _import_or_404(session, map_id)
    return _import_out(row, map_obj)


@router.get("/{map_id}/image")
async def get_import_image(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    await _owned_map_or_404(session, map_id, user_id)
    row = await _import_or_404(session, map_id)
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
    map_obj = await _owned_map_or_404(session, map_id, user_id)
    row = await _import_or_404(session, map_id, for_update=True)
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
    """Start the extraction now if the text is ready, else queue it behind OCR.

    Takes no body: everything it needs was saved step by step. The row lock
    pairs with the one the OCR task takes when it finishes, so exactly one of
    the two dispatches the extraction.
    """
    map_obj = await _owned_map_or_404(session, map_id, user_id)
    row = await _import_or_404(session, map_id, for_update=True)
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
            row = await _import_or_404(session, map_id, for_update=True)
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
    """Stop the extraction. The user's entries and the OCR result are kept.

    Waiting or queued: cancelled on the spot (a queued task is also revoked,
    and would find the row cancelled anyway). Running: marked ``cancelling``;
    the task stops at its next check and saves nothing. A 404 means the
    extraction already finished and saved its features.
    """
    map_obj = await _owned_map_or_404(session, map_id, user_id)
    row = await _import_or_404(session, map_id, for_update=True)

    if row.extraction_state in (EXTRACTION_WAITING_FOR_TEXT, EXTRACTION_QUEUED):
        if row.extraction_task_id:
            celery_app.control.revoke(row.extraction_task_id)
        row.extraction_state = EXTRACTION_CANCELLED
    elif row.extraction_state == EXTRACTION_RUNNING:
        row.extraction_state = EXTRACTION_CANCELLING
    await session.commit()
    return _import_out(row, map_obj)


@router.delete("/{map_id}")
async def abandon_import(
    map_id: UUID,
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """Drop the import, to start over with another file.

    OCR is terminated outright: it writes only at its end, under a lock, so
    killing it cannot leave anything half-written. A running extraction is
    only asked to stop -- its final transaction is atomic either way.
    """
    await _owned_map_or_404(session, map_id, user_id)
    row = await _import_or_404(session, map_id, for_update=True)
    if row.ocr_task_id and row.ocr_state != OCR_DONE:
        celery_app.control.revoke(row.ocr_task_id, terminate=True)
    if row.extraction_task_id and is_extraction_active(row):
        celery_app.control.revoke(row.extraction_task_id)
    await session.delete(row)
    await session.commit()
    return {"detail": "Import abandoned"}
