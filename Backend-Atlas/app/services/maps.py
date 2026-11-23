import os
import shutil
from copy import deepcopy
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.features import Feature
from app.models.map import Map
from app.models.map_import import MapImport
from app.models.project import Project


async def create_map_in_db(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID,
    title: str,
    start_date: date,
    end_date: date,
    exact_date: bool,
) -> UUID | None:
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project_obj = project_result.scalar_one_or_none()
    if not project_obj:
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
    return new_map.id

async def delete_map_in_db(
    db: AsyncSession,
    project_id: UUID,
    map_id: UUID,
    user_id: UUID,
) -> bool:
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project_obj = project_result.scalar_one_or_none()
    if not project_obj:
        return False

    map_result = await db.execute(
        select(Map).where(Map.id == map_id, Map.project_id == project_id)
    )
    map_obj = map_result.scalar_one_or_none()
    if not map_obj:
        return False

    features_result = await db.execute(
        select(Feature).where(
            Feature.map_id == map_id, Feature.project_id == project_id
        )
    )
    map_features = features_result.scalars().all()
    map_id_str = str(map_id)

    for feat in map_features:
        other_map_ids: list[str] = []
        if isinstance(feat.data, dict):
            features_list = feat.data.get("features", [])
            if isinstance(features_list, list) and features_list:
                inner_props = (features_list[0] or {}).get("properties") or {}
                raw_map_ids = inner_props.get("mapIds") or (feat.data.get("mapIds") or [])
                if isinstance(raw_map_ids, list):
                    other_map_ids = [str(m) for m in raw_map_ids if str(m) != map_id_str]

        if other_map_ids:
            try:
                next_map_uuid = UUID(other_map_ids[0])
                feat.map_id = next_map_uuid
                feat.data["mapId"] = other_map_ids[0]
                feat.data["map_id"] = other_map_ids[0]
                feat.data["mapIds"] = other_map_ids
                if isinstance(feat.data.get("features"), list) and feat.data["features"]:
                    props = feat.data["features"][0].setdefault("properties", {})
                    props["mapIds"] = other_map_ids
                    props["mapId"] = other_map_ids[0]
                    props["map_id"] = other_map_ids[0]
            except Exception:
                await db.delete(feat)
        else:
            await db.delete(feat)

    await db.execute(delete(MapImport).where(MapImport.map_id == map_id))
    await db.execute(delete(Map).where(Map.id == map_id))
    await db.commit()
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
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project_obj = project_result.scalar_one_or_none()
    if not project_obj:
        return None

    map_result = await db.execute(
        select(Map).where(Map.id == source_map_id, Map.project_id == project_id)
    )
    source_map = map_result.scalar_one_or_none()
    if not source_map:
        return None

    new_map = Map(
        id=uuid4(),
        project_id=project_id,
        title=new_title,
        start_date=start_date or source_map.start_date,
        end_date=end_date or source_map.end_date,
        exact_date=exact_date,
        georef_inputs=source_map.georef_inputs,
        reference_image_content_type=source_map.reference_image_content_type,
    )
    db.add(new_map)
    await db.flush()

    if source_map.reference_image_path:
        media_root = os.getenv("MEDIA_ROOT", "/app/media")
        source_abs = os.path.abspath(os.path.join(media_root, source_map.reference_image_path))
        if os.path.isfile(source_abs):
            ref_dir = os.path.join(media_root, "reference_images")
            os.makedirs(ref_dir, exist_ok=True)
            ext = os.path.splitext(source_map.reference_image_path)[1]
            new_filename = f"{new_map.id}{ext}"
            dest_abs = os.path.join(ref_dir, new_filename)
            try:
                shutil.copy2(source_abs, dest_abs)
                new_map.reference_image_path = os.path.join("reference_images", new_filename)
            except OSError:
                new_map.reference_image_path = None
                new_map.reference_image_content_type = None

    features_result = await db.execute(
        select(Feature).where(
            Feature.project_id == project_id,
            Feature.map_id == source_map_id,
        )
    )
    source_features = features_result.scalars().all()

    src_start_yr = source_map.start_date.year if source_map.start_date else None
    src_end_yr = source_map.end_date.year if source_map.end_date else src_start_yr
    new_start_yr = new_map.start_date.year if new_map.start_date else None
    new_end_yr = new_map.end_date.year if new_map.end_date else new_start_yr
    src_start_date_str = source_map.start_date.isoformat() if source_map.start_date else None
    src_end_date_str = source_map.end_date.isoformat() if source_map.end_date else src_start_date_str
    new_start_date_str = new_map.start_date.isoformat() if new_map.start_date else None
    new_end_date_str = new_map.end_date.isoformat() if new_map.end_date else new_start_date_str

    def _update_feature_dict(f_dict: dict) -> None:
        f_dict["id"] = str(uuid4())
        f_dict["mapId"] = str(new_map.id)
        f_dict["map_id"] = str(new_map.id)
        if "mapIds" in f_dict:
            f_dict["mapIds"] = [str(new_map.id)]
        if "mapTitle" in f_dict:
            f_dict["mapTitle"] = new_title
        props = f_dict.setdefault("properties", {})
        if isinstance(props, dict):
            props["mapId"] = str(new_map.id)
            props["map_id"] = str(new_map.id)
            if "mapIds" in props:
                props["mapIds"] = [str(new_map.id)]
            if "mapTitle" in props:
                props["mapTitle"] = new_title
            if src_start_yr is not None and new_start_yr is not None:
                src_duration = (
                    (src_end_yr - src_start_yr)
                    if (src_end_yr is not None and src_end_yr > src_start_yr)
                    else 0
                )
                new_duration = (
                    (new_end_yr - new_start_yr)
                    if (new_end_yr is not None and new_end_yr > new_start_yr)
                    else 0
                )

                def _adapt_year(yr: int | float | None) -> int | None:
                    if yr is None:
                        return None
                    try:
                        yr_num = int(yr)
                    except (ValueError, TypeError):
                        return yr
                    if src_duration == 0 or yr_num == src_start_yr:
                        return new_start_yr
                    if src_end_yr is not None and yr_num == src_end_yr:
                        return new_end_yr
                    # Relative position inside source map period
                    if src_end_yr is not None and src_start_yr <= yr_num <= src_end_yr:
                        ratio = (yr_num - src_start_yr) / src_duration
                        adapted = round(new_start_yr + ratio * new_duration)
                        return max(new_start_yr, min(new_end_yr, adapted))
                    else:
                        year_offset = new_start_yr - src_start_yr
                        return yr_num + year_offset

                feat_sy = props.get("startYear")
                feat_ey = props.get("endYear")
                if feat_sy is not None:
                    props["startYear"] = _adapt_year(feat_sy)
                if feat_ey is not None:
                    props["endYear"] = _adapt_year(feat_ey)
            if src_start_date_str and new_start_date_str:
                if props.get("startDate") == src_start_date_str:
                    props["startDate"] = new_start_date_str
                if props.get("endDate") == src_end_date_str:
                    props["endDate"] = new_end_date_str

    for feat in source_features:
        new_feat_data = deepcopy(feat.data) if isinstance(feat.data, dict) else feat.data
        if isinstance(new_feat_data, dict):
            if new_feat_data.get("type") == "FeatureCollection" and isinstance(new_feat_data.get("features"), list):
                new_feat_data["id"] = str(uuid4())
                new_feat_data["mapId"] = str(new_map.id)
                new_feat_data["map_id"] = str(new_map.id)
                for inner in new_feat_data["features"]:
                    if isinstance(inner, dict):
                        _update_feature_dict(inner)
            else:
                _update_feature_dict(new_feat_data)

        new_feature = Feature(
            project_id=project_id,
            map_id=new_map.id,
            data=new_feat_data,
            image=feat.image,
        )
        db.add(new_feature)

    await db.commit()
    await db.refresh(new_map)
    return new_map.id


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
    target_result = await db.execute(
        select(Project).where(
            Project.id == target_project_id, Project.user_id == user_id
        )
    )
    target_project = target_result.scalar_one_or_none()
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
            exact_date=bool(source_map.exact_date),
            georef_inputs=source_map.georef_inputs,
        )
        db.add(new_map)
        mapping[str(source_map.id)] = new_map

    if not target_project.label_styles and source_project.label_styles:
        target_project.label_styles = source_project.label_styles

    await db.commit()
    return {old_id: str(new_map.id) for old_id, new_map in mapping.items()}
