"""Derived artifacts for dev-test maps: extracted once, reused by every case."""

import hashlib
import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.utils.dev_test_assets import GEOREF_ASSETS_DIR

logger = logging.getLogger(__name__)

DERIVED_DIR = os.path.join(GEOREF_ASSETS_DIR, "derived")

#: Bump when the on-disk shape of an artifact changes.
DERIVED_SCHEMA_VERSION = "1"

TEXT_REGIONS_KEY = "textRegions"

_ARTIFACT_FILENAMES = {
    TEXT_REGIONS_KEY: "text_regions.json",
}


def derived_dir_for(test_id: str) -> str:
    return os.path.join(DERIVED_DIR, test_id)


def derived_path(test_id: str, key: str) -> str:
    filename = _ARTIFACT_FILENAMES.get(key)
    if not filename:
        raise KeyError(f"Unknown derived artifact: {key}")
    return os.path.join(derived_dir_for(test_id), filename)


def _image_fingerprint(image_path: str) -> str:
    """Content hash of the map image."""
    digest = hashlib.sha256()

    with open(image_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:32]


def _ocr_producer_versions() -> Dict[str, str]:
    try:
        import easyocr
        import torch

        return {
            "easyocr": str(getattr(easyocr, "__version__", "?")),
            "torch": str(torch.__version__),
        }
    except Exception:  # pragma: no cover - only when the OCR stack is absent
        return {}


@dataclass(frozen=True)
class DerivedArtifact:
    """A stored artifact and everything needed to decide whether to trust it."""

    key: str
    payload: Any
    image_sha: str
    producer: Dict[str, str]
    produced_at: str
    schema_version: str = DERIVED_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "key": self.key,
            "imageSha256": self.image_sha,
            "producer": self.producer,
            "producedAt": self.produced_at,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class DerivedState:
    """Whether a stored artifact can be used, and why not when it cannot."""

    key: str
    present: bool
    usable: bool
    detail: Optional[str] = None
    artifact: Optional[DerivedArtifact] = None

    def as_presence(self) -> Tuple[bool, Optional[str]]:
        """The ``(present, detail)`` pair ``check_requirements`` expects."""
        return (self.usable, self.detail)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "present": self.present,
            "usable": self.usable,
            "detail": self.detail,
            "producedAt": self.artifact.produced_at if self.artifact else None,
            "producer": self.artifact.producer if self.artifact else None,
        }


def _load_artifact(test_id: str, key: str) -> Optional[DerivedArtifact]:
    path = derived_path(test_id, key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning(f"[DEV-TEST] Unreadable derived artifact {path}: {e}")
        return None

    if not isinstance(raw, dict):
        return None

    return DerivedArtifact(
        key=str(raw.get("key") or key),
        payload=raw.get("payload"),
        image_sha=str(raw.get("imageSha256") or ""),
        producer=raw.get("producer") if isinstance(raw.get("producer"), dict) else {},
        produced_at=str(raw.get("producedAt") or ""),
        schema_version=str(raw.get("schemaVersion") or "0"),
    )


def _store_artifact(test_id: str, artifact: DerivedArtifact) -> str:
    path = derived_path(test_id, artifact.key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(artifact.to_dict(), f, indent=2, ensure_ascii=False)
    return path


def inspect_derived(
    test_id: str,
    key: str,
    image_path: str,
    producer_versions: Optional[Dict[str, str]] = None,
) -> DerivedState:
    """Resolve a stored artifact against the map it is supposed to describe."""

    artifact = _load_artifact(test_id, key)
    if artifact is None:
        return DerivedState(key=key, present=False, usable=False, detail=None)

    if artifact.schema_version != DERIVED_SCHEMA_VERSION:
        return DerivedState(
            key=key,
            present=True,
            usable=False,
            detail=(
                f"stale: written under schema v{artifact.schema_version},"
                f" current is v{DERIVED_SCHEMA_VERSION}"
            ),
            artifact=artifact,
        )

    try:
        current_sha = _image_fingerprint(image_path)
    except OSError as e:
        return DerivedState(
            key=key,
            present=True,
            usable=False,
            detail=f"stale: could not read the map image ({e})",
            artifact=artifact,
        )

    if artifact.image_sha and artifact.image_sha != current_sha:
        return DerivedState(
            key=key,
            present=True,
            usable=False,
            detail="stale: produced from a different image",
            artifact=artifact,
        )

    # Producer drift is recorded, not acted on. The text mask is evidence for
    # alignment, not the measurement, so a library bump is not worth 135 s.
    detail = None
    current_producer = producer_versions or {}
    drift = {
        name: (artifact.producer.get(name), version)
        for name, version in current_producer.items()
        if artifact.producer.get(name) and artifact.producer.get(name) != version
    }
    if drift:
        detail = "cached under " + ", ".join(
            f"{name} {was} (now {now})" for name, (was, now) in sorted(drift.items())
        )

    return DerivedState(
        key=key, present=True, usable=True, detail=detail, artifact=artifact
    )


def inspect_text_regions(test_id: str, image_path: str) -> DerivedState:
    return inspect_derived(
        test_id, TEXT_REGIONS_KEY, image_path, _ocr_producer_versions()
    )


def _regions_to_payload(regions: Any) -> List[List[List[float]]]:
    """Normalise OCR regions to plain JSON-able nested lists."""

    payload: List[List[List[float]]] = []
    for region in regions or []:
        try:
            payload.append([[float(pt[0]), float(pt[1])] for pt in region])
        except (TypeError, ValueError, IndexError):
            continue
    return payload


@contextmanager
def _compute_lock(test_id: str):
    """Serialise OCR per map across worker processes."""

    try:
        import fcntl
    except ImportError:
        yield
        return

    os.makedirs(derived_dir_for(test_id), exist_ok=True)
    with open(os.path.join(derived_dir_for(test_id), ".ocr.lock"), "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def ensure_text_regions(
    test_id: str,
    image_path: str,
    image_bgr: Any,
    *,
    refresh: bool = True,
    allow_compute: bool = True,
) -> Tuple[Optional[List[Any]], DerivedState]:
    """Return the map's OCR text regions, computing and persisting them if needed."""

    state = inspect_text_regions(test_id, image_path)

    if state.usable and not refresh and state.artifact is not None:
        return list(state.artifact.payload or []), state

    if not allow_compute:
        return None, state

    with _compute_lock(test_id):
        # Whoever held the lock may just have filled the cache.
        if not refresh:
            state = inspect_text_regions(test_id, image_path)
            if state.usable and state.artifact is not None:
                return list(state.artifact.payload or []), state
        return _compute_text_regions(test_id, image_path, image_bgr)


def _compute_text_regions(
    test_id: str, image_path: str, image_bgr: Any
) -> Tuple[List[Any], DerivedState]:
    from app.utils.text_extraction import extract_text

    blocks, _ = extract_text(image=image_bgr, languages=["en", "fr"], gpu_acc=False)
    regions = _regions_to_payload([block[0] for block in blocks])

    artifact = DerivedArtifact(
        key=TEXT_REGIONS_KEY,
        payload=regions,
        image_sha=_image_fingerprint(image_path),
        producer=_ocr_producer_versions(),
        produced_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        path = _store_artifact(test_id, artifact)
        logger.info(f"[DEV-TEST] Cached {len(regions)} text regions -> {path}")
    except OSError as e:
        # A cache that cannot be written is a slow run, not a failed one.
        logger.warning(f"[DEV-TEST] Could not persist text regions for {test_id}: {e}")

    return regions, DerivedState(
        key=TEXT_REGIONS_KEY,
        present=True,
        usable=True,
        detail="recomputed",
        artifact=artifact,
    )


def text_regions_if_cached(test_id: str, image_path: str) -> Optional[List[Any]]:
    """The cached regions, or None. Never runs OCR."""
    regions, _ = ensure_text_regions(
        test_id, image_path, None, refresh=False, allow_compute=False
    )
    return regions


def text_regions_for_run(
    test_id: str,
    image_path: Optional[str],
    image_bgr: Any,
    config: Any,
    *,
    allow_compute: Optional[bool] = None,
    refresh: bool = False,
) -> Optional[List[Any]]:
    """The OCR regions a dev-test run uses, decided the same way everywhere."""
    
    compute = config.enable_curve_alignment if allow_compute is None else allow_compute
    if not compute and not config.text_aware_zone_fill:
        return None
    if not image_path:
        return None

    try:
        regions, state = ensure_text_regions(
            test_id,
            image_path,
            image_bgr,
            refresh=refresh and compute,
            allow_compute=compute,
        )
    except Exception as e:
        logger.warning(f"[DEV-TEST] Could not obtain text regions for {test_id}: {e}")
        return None

    if regions is None:
        logger.info(
            f"[DEV-TEST] no cached text regions for {test_id};"
            " skipping the text-aware zone fill (alignment is off)"
        )
        return None
    logger.info(
        f"[DEV-TEST] text regions for {test_id}: {len(regions)}"
        f" ({state.detail or 'reused from cache'})"
    )
    return regions


def delete_derived(test_id: str) -> None:
    """Drop every derived artifact for a map. Called when the map is deleted."""
    import shutil

    directory = derived_dir_for(test_id)
    if os.path.isdir(directory):
        try:
            shutil.rmtree(directory)
        except OSError as e:
            logger.warning(f"[DEV-TEST] Could not delete derived dir {directory}: {e}")
