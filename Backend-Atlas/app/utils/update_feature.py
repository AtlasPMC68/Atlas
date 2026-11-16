import base64
from copy import deepcopy
from app.models.features import Feature, ValidationStatus


def normalize_feature_for_storage(feature: dict) -> dict:
    payload = deepcopy(feature) if isinstance(feature, dict) else {}

    payload.pop("id", None)
    payload.pop("map_id", None)
    payload.pop("created_at", None)
    payload.pop("updated_at", None)

    properties = payload.get("properties")
    if not isinstance(properties, dict):
        properties = {}

    raw_status = properties.get("validation_status") or properties.get("validationStatus")
    if raw_status:
        try:
            status_val = ValidationStatus(str(raw_status).lower()).value
        except ValueError:
            status_val = str(raw_status)
        properties["validation_status"] = status_val
        properties["validationStatus"] = status_val
        if status_val == ValidationStatus.ACCEPTED.value:
            properties["show"] = True
            properties["recognized"] = True
        elif status_val in (
            ValidationStatus.REJECTED.value,
            ValidationStatus.MANUAL_REVIEW.value,
        ):
            properties["show"] = False
            properties["recognized"] = False

    payload["properties"] = properties
    return payload


def to_feature_collection(feature: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [normalize_feature_for_storage(feature)],
    }


def normalize_feature_collection(data: dict | None) -> dict:
    if not isinstance(data, dict):
        return to_feature_collection({})

    features = data.get("features")
    first_feature = features[0] if isinstance(features, list) and features else {}
    return to_feature_collection(first_feature)


def serialize_db_feature(row: Feature) -> dict | None:
    if not row.data or not isinstance(row.data, dict):
        return None

    feature_data = row.data.get("features", [])
    if not isinstance(feature_data, list) or not feature_data:
        return None

    raw_feature = feature_data[0]
    if not isinstance(raw_feature, dict):
        return None

    feature = deepcopy(raw_feature)

    feature["id"] = str(row.id)
    feature["project_id"] = str(row.project_id)
    feature["map_id"] = str(row.map_id) if row.map_id else None

    if row.created_at:
        feature["created_at"] = row.created_at.isoformat()
    if hasattr(row, "updated_at") and row.updated_at:
        feature["updated_at"] = row.updated_at.isoformat()

    props = feature.setdefault("properties", {})

    raw_status = props.get("validation_status") or props.get("validationStatus")
    if raw_status:
        try:
            status_val = ValidationStatus(str(raw_status).lower()).value
        except ValueError:
            status_val = str(raw_status)
        props["validation_status"] = status_val
        props["validationStatus"] = status_val

    if getattr(row, "image", None):
        image_bytes = bytes(row.image)
        feature["image"] = base64.b64encode(image_bytes).decode("ascii")
        props["mimeType"] = props.get("mimeType", "image/png")

    return feature


def serialize_feature_rows(rows: list[Feature]) -> list[dict]:
    serialized_features: list[dict] = []
    for row in rows:
        serialized = serialize_db_feature(row)
        if serialized is not None:
            serialized_features.append(serialized)
    return serialized_features
