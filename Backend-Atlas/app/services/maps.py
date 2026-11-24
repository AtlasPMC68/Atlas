import asyncio
import logging
import os
import shutil
from copy import deepcopy
from datetime import date
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import String, cast as sa_cast, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.features import Feature
from app.models.map import Map
from app.models.map_import import MapImport
from app.models.project import Project

logger = logging.getLogger(__name__)


def _get_feature_props(data: dict[str, Any], *, create: bool = False) -> dict[str, Any] | None:
    """Return the properties dict of a FeatureCollection's first feature or a Feature."""
    features_list = data.get("features")
    if isinstance(features_list, list) and features_list:
        first = features_list[0]
        if not isinstance(first, dict):
            return None
        return first.setdefault("properties", {}) if create else first.get("properties")
    props = data.get("properties")
    return props if isinstance(props, dict) else None


def extract_feature_map_ids(feat_data: dict[str, Any] | None) -> list[str]:
    """Extract list of mapIds from feature data dictionary (handling Feature or FeatureCollection)."""
    if not isinstance(feat_data, dict):
        return []
    props = _get_feature_props(feat_data) or {}
    raw = props.get("mapIds") or feat_data.get("mapIds") or []
    return [str(m) for m in raw] if isinstance(raw, list) else []


def update_feature_map_ids(feat_data: dict[str, Any] | None, new_map_ids: list[str]) -> dict[str, Any]:
    """Return a deepcopy of feat_data with updated mapIds and mapId/map_id."""
    data: dict[str, Any] = deepcopy(feat_data) if isinstance(feat_data, dict) else {}
    primary_id = new_map_ids[0] if new_map_ids else None

    targets = [data]
    props = _get_feature_props(data, create=True)
    if props is not None:
        targets.append(props)

    for target in targets:
        target["mapIds"] = new_map_ids
        if primary_id:
            target["mapId"] = primary_id
            target["map_id"] = primary_id

    return data


def _adapt_year(
    yr: int | float | None,
    src_start: int,
    src_end: int | None,
    new_start: int,
    new_end: int | None,
) -> int | None:
    if yr is None:
        return None
    try:
        yr_num = int(yr)
    except (ValueError, TypeError):
        return cast(Any, yr)

    src_duration = (src_end - src_start) if (src_end is not None and src_end > src_start) else 0
    new_duration = (new_end - new_start) if (new_end is not None and new_end > new_start) else 0

    if src_duration == 0 or yr_num == src_start:
        return new_start
    if src_end is not None and yr_num == src_end:
        return new_end
    if src_end is not None and new_end is not None and src_start <= yr_num <= src_end:
        ratio = (yr_num - src_start) / src_duration
        adapted = round(new_start + ratio * new_duration)
        return max(new_start, min(new_end, adapted))
    return yr_num + (new_start - src_start)


def _rewrite_feature_dict(
    f_dict: dict[str, Any],
    *,
    new_map_id_str: str,
    new_title: str,
    source_map: Map,
    new_map: Map,
) -> None:
    f_dict["id"] = str(uuid4())
    for target in (f_dict, f_dict.setdefault("properties", {})):
        if not isinstance(target, dict):
            continue
        target["mapId"] = new_map_id_str
        target["map_id"] = new_map_id_str
        if "mapIds" in target:
            target["mapIds"] = [new_map_id_str]
        if "mapTitle" in target:
            target["mapTitle"] = new_title

    props = f_dict.get("properties")
    if not isinstance(props, dict):
        return

    src_start = cast(date | None, source_map.start_date)
    src_end = cast(date | None, source_map.end_date) or src_start
    new_start = cast(date | None, new_map.start_date)
    new_end = cast(date | None, new_map.end_date) or new_start

    if src_start is not None and new_start is not None:
        src_end_val = src_end or src_start
        new_end_val = new_end or new_start

        for key in ("startYear", "endYear"):
            if props.get(key) is not None:
                props[key] = _adapt_year(
                    props[key],
                    src_start.year,
                    src_end_val.year,
                    new_start.year,
                    new_end_val.year,
                )

        if props.get("startDate") == src_start.isoformat():
            props["startDate"] = new_start.isoformat()
        if props.get("endDate") == src_end_val.isoformat():
            props["endDate"] = new_end_val.isoformat()


def _media_root() -> str:
    return os.getenv("MEDIA_ROOT", "/app/media")


def _is_under_media_root(abs_path: str, media_root_abs: str) -> bool:
    return abs_path == media_root_abs or abs_path.startswith(media_root_abs + os.sep)


def _delete_reference_image_file(map_obj: Map) -> None:
    rel_path = cast(str | None, map_obj.reference_image_path)
    if not rel_path:
        return
    media_root = _media_root()
    abs_path = os.path.abspath(os.path.join(media_root, rel_path))
    media_root_abs = os.path.abspath(media_root)
    if not _is_under_media_root(abs_path, media_root_abs) or not os.path.isfile(abs_path):
        return
    try:
        os.unlink(abs_path)
    except OSError:
        logger.warning("Could not delete reference image %s", abs_path, exc_info=True)


async def _copy_reference_image(source_map: Map, new_map: Map) -> str | None:
    src_ref_path = cast(str | None, source_map.reference_image_path)
    if not src_ref_path:
        setattr(new_map, "reference_image_content_type", None)
        return None

    media_root = _media_root()
    media_root_abs = os.path.abspath(media_root)
    source_abs = os.path.abspath(os.path.join(media_root, src_ref_path))
    if not _is_under_media_root(source_abs, media_root_abs) or not os.path.isfile(source_abs):
        setattr(new_map, "reference_image_path", None)
        setattr(new_map, "reference_image_content_type", None)
        return None

    ref_dir = os.path.join(media_root, "reference_images")
    os.makedirs(ref_dir, exist_ok=True)
    ext = os.path.splitext(src_ref_path)[1]
    new_filename = f"{new_map.id}{ext}"
    dest_abs = os.path.join(ref_dir, new_filename)
    try:
        await asyncio.to_thread(shutil.copy2, source_abs, dest_abs)
        setattr(new_map, "reference_image_path", os.path.join("reference_images", new_filename))
        return dest_abs
    except OSError:
        setattr(new_map, "reference_image_path", None)
        setattr(new_map, "reference_image_content_type", None)
        return None


async def _get_owned_project(db: AsyncSession, project_id: UUID, user_id: UUID) -> Project | None:
    res = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    return res.scalar_one_or_none()


async def _get_owned_map(
    db: AsyncSession, project_id: UUID, map_id: UUID, user_id: UUID
) -> Map | None:
    if not await _get_owned_project(db, project_id, user_id):
        return None
    res = await db.execute(
        select(Map).where(Map.id == map_id, Map.project_id == project_id)
    )
    return res.scalar_one_or_none()


async def create_map_in_db(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    title: str,
    start_date: date,
    end_date: date,
    exact_date: bool,
) -> UUID | None:
    if not await _get_owned_project(db, project_id, user_id):
        return None

    new_map = Map(
        project_id=project_id,
        title=title,
        start_date=start_date,
        end_date=end_date,
        exact_date=exact_date,
    )
    db.add(new_map)
    await db.commit()
    await db.refresh(new_map)
    return cast(UUID, new_map.id)


async def delete_map_in_db(
    db: AsyncSession,
    project_id: UUID,
    map_id: UUID,
    user_id: UUID,
) -> bool:
    map_obj = await _get_owned_map(db, project_id, map_id, user_id)
    if not map_obj:
        return False

    map_id_str = str(map_id)
    features_result = await db.execute(
        select(Feature).where(
            Feature.project_id == project_id,
            or_(
                Feature.map_id == map_id,
                sa_cast(Feature.data, String).contains(map_id_str),
            ),
        )
    )

    for feat in features_result.scalars().all():
        feat_map_id = cast(UUID | None, feat.map_id)
        feat_map_id_str = str(feat_map_id) if feat_map_id is not None else None
        feat_data = cast(dict[str, Any] | None, feat.data)
        all_map_ids = extract_feature_map_ids(feat_data)

        if feat_map_id_str != map_id_str and map_id_str not in all_map_ids:
            continue

        other_map_ids = [m for m in all_map_ids if m != map_id_str]

        if other_map_ids:
            try:
                next_map_uuid = UUID(other_map_ids[0])
                if feat_map_id_str == map_id_str or feat_map_id_str is None:
                    setattr(feat, "map_id", next_map_uuid)
                setattr(feat, "data", update_feature_map_ids(feat_data, other_map_ids))
                flag_modified(feat, "data")
            except ValueError:
                logger.warning(
                    "Invalid mapIds while deleting map %s from feature %s",
                    map_id,
                    getattr(feat, "id", None),
                    exc_info=True,
                )
                await db.delete(feat)
        else:
            await db.delete(feat)

    await db.execute(delete(MapImport).where(MapImport.map_id == map_id))
    await db.execute(delete(Map).where(Map.id == map_id))
    await db.commit()
    _delete_reference_image_file(map_obj)
    return True


async def duplicate_map_in_project(
    db: AsyncSession,
    project_id: UUID,
    source_map_id: UUID,
    user_id: UUID,
    new_title: str,
    start_date: date | None = None,
    end_date: date | None = None,
    exact_date: bool = False,
) -> UUID | None:
    source_map = await _get_owned_map(db, project_id, source_map_id, user_id)
    if not source_map:
        return None

    new_map = Map(
        id=uuid4(),
        project_id=project_id,
        title=new_title,
        start_date=start_date or cast(date | None, source_map.start_date),
        end_date=end_date or cast(date | None, source_map.end_date),
        exact_date=exact_date,
        georef_inputs=deepcopy(source_map.georef_inputs),
        reference_image_content_type=source_map.reference_image_content_type,
    )
    db.add(new_map)
    await db.flush()
    copied_abs = await _copy_reference_image(source_map, new_map)

    features_result = await db.execute(
        select(Feature).where(
            Feature.project_id == project_id,
            Feature.map_id == source_map_id,
        )
    )
    new_map_id_str = str(new_map.id)

    for feat in features_result.scalars().all():
        raw_data = cast(Any, feat.data)
        new_data = deepcopy(raw_data) if isinstance(raw_data, dict) else raw_data
        if isinstance(new_data, dict):
            if new_data.get("type") == "FeatureCollection" and isinstance(new_data.get("features"), list):
                new_data["id"] = str(uuid4())
                new_data["mapId"] = new_map_id_str
                new_data["map_id"] = new_map_id_str
                for inner in new_data["features"]:
                    if isinstance(inner, dict):
                        _rewrite_feature_dict(
                            inner,
                            new_map_id_str=new_map_id_str,
                            new_title=new_title,
                            source_map=source_map,
                            new_map=new_map,
                        )
            else:
                _rewrite_feature_dict(
                    new_data,
                    new_map_id_str=new_map_id_str,
                    new_title=new_title,
                    source_map=source_map,
                    new_map=new_map,
                )

        db.add(
            Feature(
                project_id=project_id,
                map_id=new_map.id,
                data=new_data,
                image=feat.image,
            )
        )

    try:
        await db.commit()
    except Exception:
        if copied_abs:
            try:
                os.unlink(copied_abs)
            except OSError:
                logger.warning("Could not remove orphaned reference image %s", copied_abs, exc_info=True)
        raise
    await db.refresh(new_map)
    return cast(UUID, new_map.id)


async def copy_maps_between_projects(
    db: AsyncSession,
    source_project_id: UUID,
    target_project_id: UUID,
    user_id: UUID,
) -> dict[str, str] | None:
    """Copy the maps (periods) and label styles of a project the user can read
    into a project the user owns. Returns {source_map_id: new_map_id}, or None
    when either project is missing or not accessible.

    The reference image is not copied: its file is replaced (and the old one
    deleted) on re-upload, so sharing the path would let the copy delete the
    source's image.
    """
    target_project = await _get_owned_project(db, target_project_id, user_id)
    source_result = await db.execute(
        select(Project).where(
            Project.id == source_project_id,
            (Project.user_id == user_id) | (Project.is_private.is_(False)),
        )
    )
    source_project = source_result.scalar_one_or_none()
    if not target_project or not source_project:
        return None

    maps_result = await db.execute(
        select(Map)
        .where(Map.project_id == source_project_id)
        .order_by(Map.start_date.asc(), Map.created_at.asc())
    )

    mapping: dict[str, Map] = {}
    for source_map in maps_result.scalars().all():
        new_map = Map(
            project_id=target_project_id,
            title=source_map.title,
            start_date=source_map.start_date,
            end_date=source_map.end_date,
            exact_date=bool(cast(bool | None, source_map.exact_date)),
            georef_inputs=source_map.georef_inputs,
        )
        db.add(new_map)
        mapping[str(source_map.id)] = new_map

    if not cast(Any, target_project.label_styles) and cast(Any, source_project.label_styles):
        setattr(target_project, "label_styles", source_project.label_styles)

    await db.commit()
    return {old_id: str(new_map.id) for old_id, new_map in mapping.items()}