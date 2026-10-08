"""The cleaning stage: what happens to zones once the transform has placed them.

Three steps :

    snapping     zone vertices near the reference coastline move onto it
                 (``snap_to_coastline``; corrects transform error after the fact)
    ocean clip   the part of a zone at sea is cut off (``clip_to_land_mask``)
    lakes        Natural Earth lakes are cut out of zones, as part of the clip
"""

import logging
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.utils.coastline_land_mask import (
    GEOJSON_DIR,
    clip_zone_to_land_mask,
    load_land_mask_from_coastline_and_ocean_points,
)

from .projection import lonlat_arrays_to_webmercator, webmercator_arrays_to_lonlat
from .reference import LAKES_FILE, load_reference_polygons

logger = logging.getLogger(__name__)

CLEANING_VERSION = "1"

#: Lakes are water: cut out of zones by the clip. Production behaviour, and so
#: the convention every expected zone is cleaned with. Turning it off here turns
#: it off for both, which is the point of having one switch.
SUBTRACT_LAKES = True

_MASK_SOURCES = ("ne_coastline.geojson", "ne_ocean_points.geojson", LAKES_FILE)


def _mtime(filename: str) -> Optional[float]:
    try:
        return os.path.getmtime(os.path.join(GEOJSON_DIR, filename))
    except OSError:
        return None


def mask_sources() -> Dict[str, Optional[float]]:
    """The reference files the mask is built from, with their mtimes."""
    return {name: _mtime(name) for name in _MASK_SOURCES}


@lru_cache(maxsize=2)
def _land_mask_3857_cached(
    subtract_lakes: bool, _versions: Tuple[Optional[float], ...]
) -> Optional[BaseGeometry]:
    land_wgs84 = load_land_mask_from_coastline_and_ocean_points()
    if land_wgs84 is None:
        logger.warning("Land/ocean mask unavailable; ocean clipping will be skipped.")
        return None
    land = transform(lonlat_arrays_to_webmercator, land_wgs84)
    if subtract_lakes:
        lakes = load_reference_polygons(LAKES_FILE)
        if lakes is None:
            logger.warning("Lake polygons unavailable; keeping lakes in zones.")
        else:
            # The land mask comes from the coastline, which has no lakes in it,
            # so an inland lake is land until it is cut out here.
            land = land.difference(transform(lonlat_arrays_to_webmercator, lakes))
    return land


def land_mask_3857() -> Optional[BaseGeometry]:
    """Land minus lakes, in EPSG:3857: what zones are clipped to."""

    return _land_mask_3857_cached(SUBTRACT_LAKES, tuple(mask_sources().values()))


def clean_expected_zones(feature_collection: Dict[str, Any]) -> Dict[str, Any]:
    """The expected zones with the pipeline's geographic cuts applied."""
    mask = land_mask_3857()
    features = []
    for feature in feature_collection.get("features", []):
        geometry = feature.get("geometry")
        if not geometry:
            continue
        if mask is None:
            features.append(feature)
            continue
        geom_3857 = transform(lonlat_arrays_to_webmercator, shape(geometry))
        clipped = clip_zone_to_land_mask(geom_3857, mask, land_coverage_threshold=0.0)
        if clipped is None:
            name = (feature.get("properties") or {}).get("name")
            logger.warning(f"Expected zone {name!r} lies entirely in water; left out.")
            continue
        features.append(
            {
                **feature,
                "geometry": mapping(transform(webmercator_arrays_to_lonlat, clipped)),
            }
        )
    return {"type": "FeatureCollection", "features": features}
