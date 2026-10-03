"""
Test that maps with text extraction enabled are routed to "maps_ocr" queue, while maps without text extraction are routed to "maps" queue.
Reason for this is that OCR only has a concurrency of 1 to avoid memory bottlenecks, so the routing logic ensures that non-OCR tasks are
segregated to a different queue.
"""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.routers.projects import upload_and_process_map

def _make_upload_file(filename: str = "map.png", content: bytes = b"fake-image-bytes") -> UploadFile:
    return UploadFile(filename=filename, file=BytesIO(content))


@pytest.mark.parametrize(
    "enable_text,expected_queue",
    [
        (True, "maps_ocr"),
        (False, "maps"),
    ],
)
@pytest.mark.asyncio
async def test_upload_and_process_map_routing(enable_text: bool, expected_queue: str):
    map_id = uuid4()
    project_id = uuid4()
    user_id = str(uuid4())
    upload = _make_upload_file()

    mock_db_result = MagicMock()
    mock_db_result.scalar_one_or_none.return_value = SimpleNamespace(
        id=map_id,
        project_id=project_id,
    )
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_db_result

    mock_task = SimpleNamespace(id="task-routing")
    mock_apply_async = MagicMock(return_value=mock_task)

    with patch("app.routers.projects.process_map_extraction.apply_async", mock_apply_async):
        response = await upload_and_process_map(
            image_points=None,
            world_points=None,
            legend_bounds=None,
            imposed_colors=None,
            imposed_shape_clicks=None,
            enable_georeferencing=False,
            enable_color_extraction=True,
            enable_text_extraction=enable_text,
            project_id=str(project_id),
            map_id=str(map_id),
            file=upload,
            user_id=user_id,
            session=mock_session,
        )

    assert response["task_id"] == "task-routing"
    mock_apply_async.assert_called_once()
    _, kwargs = mock_apply_async.call_args
    assert kwargs["queue"] == expected_queue
    assert kwargs["kwargs"]["enable_text_extraction"] is enable_text