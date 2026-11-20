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

    await db.execute(
        delete(Feature).where(
            Feature.map_id == map_id, Feature.project_id == project_id
        )
    )
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

    def _update_feature_dict(f_dict: dict) -> None:
        f_dict["id"] = str(uuid4())
        f_dict["mapId"] = str(new_map.id)
        f_dict["map_id"] = str(new_map.id)
        props = f_dict.setdefault("properties", {})
        if isinstance(props, dict):
            props["mapId"] = str(new_map.id)
            props["map_id"] = str(new_map.id)
            if src_start_yr is not None and new_start_yr is not None:
                feat_sy = props.get("startYear")
                feat_ey = props.get("endYear")
                if feat_sy is not None and (feat_sy == src_start_yr or feat_sy == src_end_yr):
                    props["startYear"] = new_start_yr
                if feat_ey is not None and (feat_ey == src_end_yr or feat_ey == src_start_yr):
                    props["endYear"] = new_end_yr

    for feat in source_features:
        new_feat_data = deepcopy(feat.data) if isinstance(feat.data, dict) else feat.data
        if isinstance(new_feat_data, dict):
            new_feat_data["id"] = str(uuid4())
            new_feat_data["mapId"] = str(new_map.id)
            new_feat_data["map_id"] = str(new_map.id)

            if new_feat_data.get("type") == "FeatureCollection" and isinstance(new_feat_data.get("features"), list):
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
