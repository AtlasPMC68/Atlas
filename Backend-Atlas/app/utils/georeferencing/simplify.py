import logging
from typing import Any, Dict, List, Sequence

import numpy as np
import shapely
from shapely.geometry import mapping, shape
from shapely.ops import transform

from .projection import lonlat_arrays_to_webmercator, webmercator_arrays_to_lonlat

logger = logging.getLogger(__name__)

JSONDict = Dict[str, Any]

#: Source-image pixels. Extraction simplifies at 1 px, so anything finer than
#: that is resampling, not the map.
STORAGE_SIMPLIFY_PX = 1.0

_SIMPLIFIABLE = {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}


def simplify_collections_for_storage(
    collections: Sequence[JSONDict],
    meters_per_pixel: float,
    tolerance_px: float = STORAGE_SIMPLIFY_PX,
) -> List[JSONDict]:
    if not isinstance(meters_per_pixel, (int, float)):
        return list(collections)
    tolerance_m = tolerance_px * meters_per_pixel
    if not (tolerance_m > 0 and np.isfinite(tolerance_m)):
        return list(collections)
    return [_simplify_collection(fc, tolerance_m) for fc in collections]


def _simplify_collection(fc: JSONDict, tolerance_m: float) -> JSONDict:
    features = fc.get("features") or []
    indices: List[int] = []
    geoms_3857: List[Any] = []
    for i, feat in enumerate(features):
        geometry = feat.get("geometry") or {}
        if geometry.get("type") not in _SIMPLIFIABLE:
            continue
        try:
            geoms_3857.append(transform(lonlat_arrays_to_webmercator, shape(geometry)))
            indices.append(i)
        except Exception as e:
            logger.warning(f"Not simplifying feature {i}: {e}")
    if not geoms_3857:
        return fc

    simplified = _simplify(np.array(geoms_3857, dtype=object), tolerance_m)

    out = list(features)
    before = after = 0
    for i, original, geom in zip(indices, geoms_3857, simplified):
        if geom is None or geom.is_empty or not geom.is_valid:
            continue
        try:
            lonlat = transform(webmercator_arrays_to_lonlat, geom)
        except Exception as e:
            logger.warning(f"Keeping feature {i} unsimplified: {e}")
            continue
        before += shapely.get_num_coordinates(original)
        after += shapely.get_num_coordinates(geom)
        out[i] = {**features[i], "geometry": mapping(lonlat)}
    if before:
        logger.info(
            f"[GEOREF] simplified for storage: {before} -> {after} vertices"
            f" ({tolerance_m:.0f} m tolerance)"
        )
    return {**fc, "features": out}


def _simplify(geoms: np.ndarray, tolerance_m: float) -> np.ndarray:
    polygonal = all(g.geom_type in ("Polygon", "MultiPolygon") for g in geoms)
    if polygonal and len(geoms) > 1:
        try:
            if bool(shapely.coverage_is_valid(geoms)):
                return shapely.coverage_simplify(geoms, tolerance_m)
        except Exception as e:
            logger.warning(f"Coverage simplification failed, per zone instead: {e}")
    return np.array(
        [g.simplify(tolerance_m, preserve_topology=True) for g in geoms], dtype=object
    )
