import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.utils.map_dictionary import (
    load_custom_dictionary,
    save_custom_dictionary_entry,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dictionary", tags=["dictionary"])


class DictionaryOverrideRequest(BaseModel):
    raw_text: str
    corrected_text: str
    category: str = "region"
    action: str = "keep"  # 'keep' or 'ignore'


@router.get("/overrides")
async def get_dictionary_overrides() -> dict[str, Any]:
    """Retrieve all user-defined dictionary overrides."""
    return load_custom_dictionary()


@router.post("/override")
async def create_or_update_override(req: DictionaryOverrideRequest) -> dict[str, Any]:
    """Save a user-defined dictionary correction rule for future OCR passes and imports."""
    entry = save_custom_dictionary_entry(
        raw_text=req.raw_text,
        corrected_text=req.corrected_text,
        category=req.category,
        action=req.action,
    )
    return {"status": "success", "entry": entry}
