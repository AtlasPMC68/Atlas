"""A test map's expected zones, drawn and cleaned.

Two versions of every drawn zone file, both under ``georef_zones/``:

    <test_id>_zones.geojson          as drawn in the test editor; what the raw,
                                     pre-cleaning output is scored against
    <test_id>_zones_cleaned.geojson  the same zones through the pipeline's
                                     geographic cuts (ocean, lakes); what the
                                     shipped output is scored against

The cleaned file is written whenever the drawn one is saved, and stamped with a
hash of the drawn file and the cleaning version. A cleaned file whose stamp no
longer matches -- the drawing changed outside the editor, the cleaning changed,
or the file predates this -- is recomputed when it is next read: it is derived
data, like the OCR cache, never a second source of truth.
"""

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

from app.utils.dev_test_assets import ZONES_DIR

logger = logging.getLogger(__name__)

DRAWN_SUFFIX = "_zones.geojson"
CLEANED_SUFFIX = "_zones_cleaned.geojson"


def drawn_zones_path(test_id: str, zones_dir: str = ZONES_DIR) -> str:
    return os.path.join(zones_dir, f"{test_id}{DRAWN_SUFFIX}")


def cleaned_zones_path(test_id: str, zones_dir: str = ZONES_DIR) -> str:
    return os.path.join(zones_dir, f"{test_id}{CLEANED_SUFFIX}")


def _stamp(drawn: Dict[str, Any]) -> Dict[str, Any]:
    from app.utils.georeferencing.cleaning import CLEANING_VERSION, SUBTRACT_LAKES

    blob = json.dumps(drawn, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {
        "version": CLEANING_VERSION,
        "subtractLakes": SUBTRACT_LAKES,
        "drawnSha256": hashlib.sha256(blob).hexdigest(),
    }


def _write(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _clean(drawn: Dict[str, Any]) -> Dict[str, Any]:
    from app.utils.georeferencing.cleaning import clean_expected_zones

    return {**clean_expected_zones(drawn), "cleaning": _stamp(drawn)}


def save_expected_zones(
    test_id: str, drawn: Dict[str, Any], zones_dir: str = ZONES_DIR
) -> Dict[str, Any]:
    """Write the drawn zones and their cleaned version. Returns the cleaned."""
    _write(drawn_zones_path(test_id, zones_dir), drawn)
    cleaned = _clean(drawn)
    _write(cleaned_zones_path(test_id, zones_dir), cleaned)
    return cleaned


def load_drawn_zones(test_id: str, zones_dir: str = ZONES_DIR) -> Optional[Dict[str, Any]]:
    path = drawn_zones_path(test_id, zones_dir)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cleaned_zones(test_id: str, zones_dir: str = ZONES_DIR) -> Optional[Dict[str, Any]]:
    """The cleaned expected zones, recomputed if missing or stale.

    None when the map has no drawn zones at all.
    """
    drawn = load_drawn_zones(test_id, zones_dir)
    if drawn is None:
        return None

    path = cleaned_zones_path(test_id, zones_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cleaned = json.load(f)
            if cleaned.get("cleaning") == _stamp(drawn):
                return cleaned
        except (OSError, ValueError):
            pass

    logger.info(f"[DEV-TEST] (re)cleaning the expected zones of {test_id}")
    cleaned = _clean(drawn)
    try:
        _write(path, cleaned)
    except OSError as e:
        # A cache that cannot be written is a slower read, not a failed one.
        logger.warning(f"[DEV-TEST] Could not persist cleaned zones for {test_id}: {e}")
    return cleaned


def delete_expected_zones(test_id: str, zones_dir: str = ZONES_DIR) -> None:
    for path in (drawn_zones_path(test_id, zones_dir), cleaned_zones_path(test_id, zones_dir)):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"[DEV-TEST] Could not delete {path}: {e}")
