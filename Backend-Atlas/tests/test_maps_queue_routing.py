from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.routers.maps import upload_and_process_map


"""
Test that maps with text extraction enabled are routed to "maps_ocr" queue, while maps without text extraction are routed to "maps" queue.
Reason for this is that OCR only has a concurrency of 1 to avoid memory bottlenecks, so the routing logic ensures that non-OCR tasks are
segregated to a different queue.
"""

def _make_upload_file(filename: str = "map.png", content: bytes = b"fake-image-bytes") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


@pytest.mark.asyncio
async def test_upload_and_process_map_routes_text_extraction_to_maps_ocr_queue():
    map_id = uuid4()
    user_id = str(uuid4())
    upload = _make_upload_file()

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = SimpleNamespace(id=map_id)
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_db_result

    mock_task = SimpleNamespace(id="task-text")
    mock_apply_async = MagicMock(return_value=mock_task)

    with patch("app.routers.maps.process_map_extraction.apply_async", mock_apply_async):
        response = await upload_and_process_map(
            image_points=None,
            world_points=None,
            legend_bounds=None,
            enable_georeferencing=False,
            enable_color_extraction=True,
            enable_shapes_extraction=False,
            enable_text_extraction=True,
            map_id=str(map_id),
            file=upload,
            user_id=user_id,
            session=mock_session,
        )

    assert response["task_id"] == "task-text"
    mock_apply_async.assert_called_once()
    _, kwargs = mock_apply_async.call_args
    assert kwargs["queue"] == "maps_ocr"
    assert kwargs["kwargs"]["enable_text_extraction"] is True


@pytest.mark.asyncio
async def test_upload_and_process_map_routes_non_text_extraction_to_maps_queue():
    map_id = uuid4()
    user_id = str(uuid4())
    upload = _make_upload_file()

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = SimpleNamespace(id=map_id)
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_db_result

    mock_task = SimpleNamespace(id="task-no-text")
    mock_apply_async = MagicMock(return_value=mock_task)

    # Simply calls routers.maps.process_map_extraction with enable_text_extraction=False, which should
    # route to "maps" queue instead of "maps_ocr"
    with patch("app.routers.maps.process_map_extraction.apply_async", mock_apply_async):
        response = await upload_and_process_map(
            image_points=None,
            world_points=None,
            legend_bounds=None,
            enable_georeferencing=False,
            enable_color_extraction=True,
            enable_shapes_extraction=False,
            enable_text_extraction=False,
            map_id=str(map_id),
            file=upload,
            user_id=user_id,
            session=mock_session,
        )

    assert response["task_id"] == "task-no-text"
    mock_apply_async.assert_called_once()
    _, kwargs = mock_apply_async.call_args
    assert kwargs["queue"] == "maps"
    assert kwargs["kwargs"]["enable_text_extraction"] is False