import shapely
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import transform

from app.utils.georeferencing.projection import (
    lonlat_arrays_to_webmercator,
    webmercator_arrays_to_lonlat,
)
from app.utils.georeferencing.simplify import simplify_collections_for_storage

MPP = 1000.0  # metres per source pixel


def _lonlat(geom):
    return mapping(transform(webmercator_arrays_to_lonlat, geom))


def _3857(feature):
    return transform(lonlat_arrays_to_webmercator, shape(feature["geometry"]))


def _fc(*geoms, props=None):
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": dict(props or {}), "geometry": _lonlat(g)}
            for g in geoms
        ],
    }


def test_densified_edges_lose_their_extra_vertices():
    square = shapely.segmentize(box(0, 0, 500_000, 500_000), 5_000)
    out = simplify_collections_for_storage([_fc(square)], MPP)
    result = _3857(out[0]["features"][0])
    assert shapely.get_num_coordinates(result) == 5
    assert result.hausdorff_distance(square) < MPP


def test_neighbouring_zones_stay_without_gap_or_overlap():
    left = shapely.segmentize(box(0, 0, 300_000, 300_000), 3_000)
    right = shapely.segmentize(box(300_000, 0, 600_000, 300_000), 3_000)
    out = simplify_collections_for_storage([_fc(left, right)], MPP)
    a, b = (_3857(f) for f in out[0]["features"])
    assert a.intersection(b).area < 1.0
    assert abs(a.union(b).area - 600_000 * 300_000) < 1e3


def test_detail_larger_than_the_tolerance_is_kept():
    notch = Polygon(
        [(0, 0), (100_000, 0), (100_000, 50_000), (95_000, 50_000),
         (95_000, 60_000), (100_000, 60_000), (100_000, 100_000), (0, 100_000)]
    )
    out = simplify_collections_for_storage([_fc(notch)], MPP)
    assert shapely.get_num_coordinates(_3857(out[0]["features"][0])) == 9


def test_points_and_properties_pass_through():
    fc = _fc(shapely.segmentize(box(0, 0, 100_000, 100_000), 1_000), props={"name": "zone"})
    fc["features"].append(
        {"type": "Feature", "properties": {"name": "ville"},
         "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}}
    )
    out = simplify_collections_for_storage([fc], MPP)
    assert out[0]["features"][0]["properties"] == {"name": "zone"}
    assert out[0]["features"][1] == fc["features"][1]


def test_no_scale_leaves_the_zones_alone():
    fc = _fc(shapely.segmentize(box(0, 0, 100_000, 100_000), 1_000))
    assert simplify_collections_for_storage([fc], float("nan")) == [fc]
