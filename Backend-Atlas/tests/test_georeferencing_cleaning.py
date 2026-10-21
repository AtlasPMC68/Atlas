"""The cleaning stage, and scoring before and after it."""

import json

from shapely.geometry import box, mapping, shape

from app.utils.dev_test_expected import (
    cleaned_zones_path,
    load_cleaned_zones,
    save_expected_zones,
)
from app.utils.georeferencing.cleaning import clean_expected_zones

# A box over Lake Ontario: the lake is water, the shore is land.
LAKE_ONTARIO = box(-79.5, 43.2, -76.5, 44.2)
# A box across the Gulf of St. Lawrence coast at Sept-Iles: half sea.
COAST = box(-67.0, 49.5, -65.5, 50.6)


def _fc(*zones):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": name}, "geometry": mapping(geom)}
            for name, geom in zones
        ],
    }


def test_expected_zones_lose_their_lakes_and_their_sea():
    cleaned = clean_expected_zones(_fc(("Ontario", LAKE_ONTARIO), ("Cote", COAST)))
    by_name = {f["properties"]["name"]: shape(f["geometry"]) for f in cleaned["features"]}
    assert by_name["Ontario"].area < 0.6 * LAKE_ONTARIO.area
    assert by_name["Cote"].area < 0.9 * COAST.area
    assert by_name["Cote"].area > 0.1 * COAST.area


def test_saving_writes_both_versions_and_a_stale_cleaned_one_is_redone(tmp_path):
    drawn = _fc(("Ontario", LAKE_ONTARIO))
    save_expected_zones("t", drawn, zones_dir=str(tmp_path))
    first = json.loads(open(cleaned_zones_path("t", str(tmp_path)), encoding="utf-8").read())
    assert first["cleaning"]["subtractLakes"] is True

    # The drawing changed behind the editor's back: the cleaned file is stale.
    (tmp_path / "t_zones.geojson").write_text(json.dumps(_fc(("Cote", COAST))), encoding="utf-8")
    again = load_cleaned_zones("t", str(tmp_path))
    assert [f["properties"]["name"] for f in again["features"]] == ["Cote"]
    assert again["cleaning"] != first["cleaning"]
