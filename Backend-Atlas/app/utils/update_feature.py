from copy import deepcopy
from app.models.features import Feature


def normalize_feature_for_storage(feature: dict) -> dict:
	payload = deepcopy(feature) if isinstance(feature, dict) else {}

	payload.pop("id", None)
	payload.pop("map_id", None)
	payload.pop("created_at", None)
	payload.pop("updated_at", None)

	properties = payload.get("properties")
	if not isinstance(properties, dict):
		properties = {}

	start_date = payload.pop("start_date", None)
	end_date = payload.pop("end_date", None)
	if start_date is not None:
		properties["start_date"] = start_date
	if end_date is not None:
		properties["end_date"] = end_date

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
    feature_data = row.data.get("features", [])
    if not feature_data:
        return None

    feature = deepcopy(feature_data[0])
    feature["id"] = str(row.id)
    feature["map_id"] = str(row.map_id)

    if row.created_at:
        feature["created_at"] = row.created_at.isoformat()
    if hasattr(row, "updated_at") and row.updated_at:
        feature["updated_at"] = row.updated_at.isoformat()

    return feature