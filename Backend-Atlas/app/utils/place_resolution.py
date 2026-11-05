"""Place-name resolution for OCR labels against geographic gazetteers.

Gazetteers:
1. **Geographic entities** (countries, provinces, lakes, rivers, ...) from ``data/geographic_entities.json``.
2. **Cities** from the *geonamescache* library (~24 000 cities worldwide).

Resolution Priorities:
=====================
1. **Spatial Bounding**:
   - Matches outside map boundaries (bounds / frame_bounds) are marked ``out_of_bounds`` or rejected.
   - Strict bounds filtering is applied when selecting city candidates.

2. **Entity Classification / Political Priority**:
   - When multiple entity types share the same name (e.g. 'Ontario' as province vs lake),
     political types (country, continent, state, province, territory) take priority over physical features.

3. **Casing-Driven Gazeteer Priority**:
   - **ALL-CAPS** text (e.g. 'CANADA', 'QUEBEC') prioritizes geographic entities first, then cities.
   - **Title / lowercase** text (e.g. 'Montreal', 'Boston') prioritizes cities first, then geographic entities.

4. **Matching Confidence Stages**:
   - Exact matching is executed first across all candidates.
   - Fuzzy matching (with configurable cutoff) is only evaluated as a fallback if no exact match is found.

5. **Spatial Disambiguation (Winner Selection)**:
   - When several candidates share the same name:
     a) Closest to ``target_pos`` (georeferenced pixel coordinates on map) wins.
     b) For cities without target_pos: highest population wins.
     c) If bounds center is available: closest to bounds center wins.
"""

from __future__ import annotations

import difflib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import geonamescache

from app.utils.place_nomenclature import (
    _normalize,
    _not_found,
    format_place_result,
    is_exploitable_text,
)

# Geographic-entities gazetteer (JSON file)
_GEO_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "geographic_entities.json"

# normalized alias -> [entity, ...]
_GEO_INDEX: Dict[str, List[Dict[str, Any]]] = {}
# (floor(lat), floor(lon)) -> [entity, ...]
_SPATIAL_GEO_GRID: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
_SEEN_GEO_KEYS: Set[Tuple[str, str, float, float]] = set()
_GEO_DATA_LOADED = False
_GEO_INDEX_KEYS: List[str] = []


def _ensure_geo_data() -> None:
    """Load geographic entities data lazily (once, on first use)."""
    global _GEO_DATA_LOADED, _GEO_INDEX_KEYS
    if _GEO_DATA_LOADED:
        return
    if _GEO_DATA_PATH.exists():
        with open(_GEO_DATA_PATH, "r", encoding="utf-8") as _f:
            for _entry in json.load(_f):
                for _alias in _entry.get("aliases", []):
                    _key = _normalize(_alias)
                    if _key:
                        _GEO_INDEX.setdefault(_key, []).append(_entry)
                if _entry.get("lat") is not None and _entry.get("lon") is not None:
                    try:
                        _glat, _glon = float(_entry["lat"]), float(_entry["lon"])
                        _gkey = (str(_entry.get("type", "")), str(_entry.get("name", "")), _glat, _glon)
                        if _gkey not in _SEEN_GEO_KEYS:
                            _SEEN_GEO_KEYS.add(_gkey)
                            _cell = (math.floor(_glat), math.floor(_glon))
                            _SPATIAL_GEO_GRID.setdefault(_cell, []).append(_entry)
                    except (ValueError, TypeError):
                        pass
    _GEO_INDEX_KEYS = list(_GEO_INDEX.keys())
    _GEO_DATA_LOADED = True


# Political types take priority when multiple entity types share the same name
# (e.g. "Ontario" = province AND lake -> province wins).
_POLITICAL_TYPES = frozenset({"country", "continent", "state", "province", "territory"})


# Configuration table for matching thresholds
MATCHING_CONFIG = {
    "exact_threshold": 1.0,
    "default_confidence_threshold": 0.80,
    "ocr_fuzzy_threshold": 0.60,
    "max_fuzzy_distance_km": 75.0,
    "suggestion_radius_km": 150.0,
}


def polygon_centroid(coords: Any) -> Optional[Tuple[float, float]]:
    """Compute the centroid (x, y) of a sequence of 2D points."""
    if not coords:
        return None
    try:
        n = len(coords)
        if n == 0:
            return None
        return (
            sum(float(point[0]) for point in coords) / n,
            sum(float(point[1]) for point in coords) / n,
        )
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None


def is_in_bounds(lat: float, lon: float, bounds: Optional[Dict[str, float]]) -> bool:
    """True when *(lat, lon)* falls inside *bounds* (or if bounds is None)."""
    if bounds is None:
        return True
    s = bounds.get("south", bounds.get("min_lat"))
    n = bounds.get("north", bounds.get("max_lat"))
    w = bounds.get("west", bounds.get("min_lon"))
    e = bounds.get("east", bounds.get("max_lon"))
    if None in (s, n, w, e):
        return True

    assert s is not None and n is not None and w is not None and e is not None
    return s <= lat <= n and w <= lon <= e


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def resolve_best_candidate(
    candidates: List[Dict[str, Any]],
    target_pos: Optional[Tuple[float, float]] = None,
    bounds: Optional[Dict[str, float]] = None,
    *,
    prefer_political: bool = True,
    prefer_population: bool = False,
    strict_bounds: bool = False,
) -> Optional[Dict[str, Any]]:
    """Select the best candidate from a candidate list following resolution priorities:

    1. Bounds Filtering (strict if requested, or prefers in-bounds candidates).
    2. Target Position Proximity (closest to target_pos wins).
    3. Political Entity Priority (prefers political entities over lakes/physical features).
    4. Population / Bounds Center (highest population or closest to map center).
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        if strict_bounds and bounds is not None:
            c = candidates[0]
            lat, lon = c.get("lat"), c.get("lon")
            if lat is None or lon is None or not is_in_bounds(float(lat), float(lon), bounds):
                return None
        return candidates[0]

    in_bounds = [
        c
        for c in candidates
        if c.get("lat") is not None
        and c.get("lon") is not None
        and (bounds is None or is_in_bounds(float(c["lat"]), float(c["lon"]), bounds))
    ]

    if strict_bounds and bounds is not None:
        pool = in_bounds
        if not pool:
            return None
    else:
        pool = in_bounds or candidates
    if target_pos is not None:
        ref_lat, ref_lon = target_pos

        def _dist(c: Dict[str, Any]) -> float:
            lat, lon = c.get("lat"), c.get("lon")
            return (
                math.hypot(float(lat) - ref_lat, float(lon) - ref_lon)
                if lat is not None and lon is not None
                else float("inf")
            )

        return min(pool, key=_dist)
    
    if prefer_political:
        political = [c for c in pool if c.get("type") in _POLITICAL_TYPES]
        if political and len(political) < len(pool):
            pool = political

    

    if prefer_population:
        return max(pool, key=lambda c: c.get("population", 0))

    if bounds is not None:
        s = bounds.get("south", bounds.get("min_lat", 0.0))
        n = bounds.get("north", bounds.get("max_lat", 0.0))
        w = bounds.get("west", bounds.get("min_lon", 0.0))
        e = bounds.get("east", bounds.get("max_lon", 0.0))
        ref_lat = (n + s) / 2.0
        ref_lon = (e + w) / 2.0

        def _dist_bounds(c: Dict[str, Any]) -> float:
            lat, lon = c.get("lat"), c.get("lon")
            return (
                math.hypot(float(lat) - ref_lat, float(lon) - ref_lon)
                if lat is not None and lon is not None
                else float("inf")
            )

        return min(pool, key=_dist_bounds)

    return pool[0]


def find_geo_entity(
    text: str,
    *,
    fuzzy: bool = False,
    cutoff: float = MATCHING_CONFIG["default_confidence_threshold"],
    target_pos: Optional[Tuple[float, float]] = None,
    bounds: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Look up *text* in the geographic-entities JSON.

    Returns the best-matching entity dict or ``None``.
    When *fuzzy=True*, tolerates OCR typos up to *cutoff*.
    """
    _ensure_geo_data()
    norm = _normalize(text)
    if not norm:
        return None

    hits = _GEO_INDEX.get(norm)
    if hits:
        return resolve_best_candidate(hits, target_pos=target_pos, bounds=bounds, prefer_political=True)

    if fuzzy and cutoff < MATCHING_CONFIG["exact_threshold"]:
        close = difflib.get_close_matches(norm, _GEO_INDEX_KEYS, n=1, cutoff=cutoff)
        if close:
            return resolve_best_candidate(_GEO_INDEX[close[0]], target_pos=target_pos, bounds=bounds, prefer_political=True)

    return None


# City gazetteer (geonamescache)
def _parse_pop(val: Any) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


_gc = getattr(geonamescache, "GeonamesCache")()
_CITY_INDEX: Dict[str, List[Dict[str, Any]]] = {}
_SPATIAL_CITY_GRID: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
_SEEN_CITY_IDS: Set[Any] = set()

for _info in _gc.get_cities().values():
    _name = _info.get("name") or ""
    try:
        _lat, _lon = float(_info["latitude"]), float(_info["longitude"])
    except Exception:
        continue
    _city = {
        "geonameid": _info.get("geonameid"),
        "name": _name,
        "lat": _lat,
        "lon": _lon,
        "population": _parse_pop(_info.get("population")),
    }
    _ck = _normalize(_name)
    _CITY_INDEX.setdefault(_ck, []).append(_city)
    if _ck.endswith(" city"):
        _base = _ck[:-5].strip()
        if _base:
            _CITY_INDEX.setdefault(_base, []).append(_city)

    _gid = _city.get("geonameid") or (_name, _lat, _lon)
    if _gid not in _SEEN_CITY_IDS:
        _SEEN_CITY_IDS.add(_gid)
        _cell = (math.floor(_lat), math.floor(_lon))
        _SPATIAL_CITY_GRID.setdefault(_cell, []).append(_city)

_CITY_INDEX_KEYS = list(_CITY_INDEX.keys())


def _get_spatial_cells(lat: float, lon: float, radius_km: float) -> List[Tuple[int, int]]:
    """Return all 1x1 degree grid cells overlapping a circular bounding box."""
    lat_delta = radius_km / 111.0
    lat_min = lat - lat_delta
    lat_max = lat + lat_delta

    max_lat_abs = min(89.0, max(abs(lat_min), abs(lat_max)))
    cos_lat = math.cos(math.radians(max_lat_abs))
    lon_delta = 180.0 if cos_lat < 0.05 else radius_km / (111.0 * cos_lat)

    min_cell_lat = math.floor(lat_min)
    max_cell_lat = math.floor(lat_max)
    min_cell_lon = math.floor(lon - lon_delta)
    max_cell_lon = math.floor(lon + lon_delta)

    cells = []
    for c_lat in range(min_cell_lat, max_cell_lat + 1):
        for c_lon in range(min_cell_lon, max_cell_lon + 1):
            norm_lon = ((c_lon + 180) % 360) - 180
            cells.append((c_lat, norm_lon))
    return cells


def find_nearby_candidate_place(
    text: str,
    coords: List[float],
    radius_km: float = 75.0,
    min_similarity: float = 0.80,
) -> Optional[Dict[str, Any]]:
    """Find a nearby city or geographic entity matching OCR text for review."""
    if not is_exploitable_text(text) or not coords or len(coords) < 2:
        return None

    _ensure_geo_data()

    lon, lat = float(coords[0]), float(coords[1])
    normalized_query = _normalize(text)
    if not normalized_query:
        return None

    query_tokens = [
        token
        for token in normalized_query.split()
        if len(token) >= 3
        and token
        not in {
            "de", "del", "des", "du", "la", "le", "les", "of", "the",
            "province", "territoire", "territory", "state", "état",
        }
    ]

    cells = _get_spatial_cells(lat, lon, radius_km)
    candidates: Dict[Tuple[str, str, float, float], Dict[str, Any]] = {}
    seen_cities: set[Tuple[Any, float, float]] = set()

    for cell in cells:
        for city in _SPATIAL_CITY_GRID.get(cell, []):
            city_key = (city.get("geonameid"), city["lat"], city["lon"])
            if city_key in seen_cities:
                continue
            seen_cities.add(city_key)
            if haversine_distance_km(lat, lon, city["lat"], city["lon"]) > radius_km:
                continue
            candidate = dict(city)
            key = ("city", candidate["name"], candidate["lat"], candidate["lon"])
            candidates[key] = candidate

    seen_entities: set[Tuple[str, str, float, float]] = set()
    for cell in cells:
        for entity in _SPATIAL_GEO_GRID.get(cell, []):
            if entity.get("lat") is None or entity.get("lon") is None:
                continue
            entity_key = (
                str(entity.get("type", "")),
                str(entity.get("name", "")),
                float(entity["lat"]),
                float(entity["lon"]),
            )
            if entity_key in seen_entities:
                continue
            seen_entities.add(entity_key)
            if haversine_distance_km(lat, lon, float(entity["lat"]), float(entity["lon"])) > radius_km:
                continue
            candidates[entity_key] = entity

    scored: List[Tuple[float, float, Dict[str, Any]]] = []
    for candidate in candidates.values():
        variants = {
            _normalize(str(value))
            for value in (
                candidate.get("name"),
                candidate.get("name_fr"),
                *candidate.get("aliases", []),
            )
            if value
        }
        similarity = max(
            (
                difflib.SequenceMatcher(None, normalized_query, variant).ratio()
                for variant in variants
            ),
            default=0.0,
        )

        if query_tokens:
            variant_tokens = {token for variant in variants for token in variant.split()}
            token_matches = [
                max(
                    (
                        difflib.SequenceMatcher(None, query_token, candidate_token).ratio()
                        for candidate_token in variant_tokens
                    ),
                    default=0.0,
                )
                for query_token in query_tokens
            ]
            if all(score >= min_similarity for score in token_matches):
                similarity = max(similarity, min(token_matches))

        if similarity >= min_similarity:
            distance = haversine_distance_km(lat, lon, candidate["lat"], candidate["lon"])
            scored.append((similarity, -distance, candidate))

    if not scored:
        return None
    return max(scored, key=lambda match: (match[0], match[1]))[2]


# Sentinel for "matched but out of bounds -> reject immediately"
_BLOCKED = object()


def resolve_place(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
    confidence_threshold: float = 0.80,
    geo_bounds: Optional[Dict[str, float]] = None,
    target_pos: Optional[Tuple[float, float]] = None,
) -> Dict[str, Any]:
    """Resolve an OCR text string to a geographic place (entity or city).

    Priorities:
    - **ALL-CAPS** -> geographic entities first (provinces, countries, ...), then cities.
    - **Title / lower** -> cities first, then geographic entities.
    - Exact matching first, then fuzzy matching with threshold.

    Returns a dict containing at minimum ``found`` (bool).
    """
    key = _normalize(text)
    if not key:
        return _not_found(text)

    bounds = frame_bounds if frame_bounds is not None else geo_bounds
    base = _not_found(text)
    blocked = {**base, "out_of_bounds": True}

    def _match_geo(fuzzy: bool = False, cutoff: float = MATCHING_CONFIG["default_confidence_threshold"]) -> Any:
        ent = find_geo_entity(key, fuzzy=fuzzy, cutoff=cutoff, target_pos=target_pos, bounds=bounds)
        if ent is None:
            return None
        if not is_in_bounds(ent["lat"], ent["lon"], bounds):
            return _BLOCKED
        result = format_place_result(ent, text, base=base, default_type="country")
        result["matchMethod"] = "fuzzy" if fuzzy else "exact"
        return result

    def _match_city(fuzzy: bool = False, cutoff: float = MATCHING_CONFIG["default_confidence_threshold"]) -> Any:
        if not fuzzy:
            cands = _CITY_INDEX.get(key, [])
        else:
            close = difflib.get_close_matches(
                key, _CITY_INDEX_KEYS, n=1, cutoff=cutoff
            )
            if not close:
                return None
            cands = _CITY_INDEX.get(close[0], [])

        best = resolve_best_candidate(
            cands,
            target_pos=target_pos,
            bounds=bounds,
            prefer_political=False,
            prefer_population=True,
            strict_bounds=True,
        )
        if not best:
            if bounds is not None and cands and not any(
                is_in_bounds(float(candidate["lat"]), float(candidate["lon"]), bounds)
                for candidate in cands
                if candidate.get("lat") is not None and candidate.get("lon") is not None
            ):
                return _BLOCKED
            return None
        result = format_place_result(best, text)
        result["matchMethod"] = "fuzzy" if fuzzy else "exact"
        return result

    if text.isupper():
        # ALL-CAPS -> prefer geographic entity
        geo = _match_geo(fuzzy=False)
        if geo is _BLOCKED:
            return blocked
        if geo:
            return geo
        city = _match_city(fuzzy=False)
        if city is _BLOCKED:
            return blocked
        if city:
            return city
    else:
        # Title / lowercase -> prefer city
        city = _match_city(fuzzy=False)
        if city is _BLOCKED:
            return blocked
        if city:
            return city
        geo = _match_geo(fuzzy=False)
        if geo is _BLOCKED:
            return blocked
        if geo:
            return geo

    if confidence_threshold < MATCHING_CONFIG["exact_threshold"]:
        geo_f = _match_geo(fuzzy=True, cutoff=confidence_threshold)
        if geo_f is _BLOCKED:
            return blocked
        if geo_f:
            return geo_f

        city_f = _match_city(fuzzy=True, cutoff=confidence_threshold)
        if city_f is _BLOCKED:
            return blocked
        if city_f:
            return city_f

    return base


def match_ocr_label(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
    target_pos: Optional[Tuple[float, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Match an OCR text label against both gazetteers following resolution stages:

    Stage 1: Exact matches (whole text, then line-by-line).
    Stage 2: Fuzzy matches (line-by-line if multiline, else whole text).
    """
    clean = str(text or "").strip()
    if not clean:
        return None

    def _try(query: str, threshold: float) -> Optional[Dict[str, Any]]:
        if not is_exploitable_text(query):
            return None
        try:
            res = resolve_place(query, frame_bounds=frame_bounds, confidence_threshold=threshold, target_pos=target_pos)
            return res if res.get("found") or res.get("out_of_bounds") else None
        except Exception:
            return None

    whole = clean.replace("\n", " ")
    lines = [ln.strip() for ln in clean.split("\n") if ln.strip()]

    # Stage 1: Exact matches (whole text, then line-by-line)
    exact_candidates = [whole] if len(lines) <= 1 else [whole, *lines]
    for q in exact_candidates:
        hit = _try(q, MATCHING_CONFIG["exact_threshold"])
        if hit:
            return hit

    # Stage 2: Fuzzy matches (line-by-line if multiline, else whole text)
    fuzzy_candidates = lines if len(lines) > 1 else [whole]
    for q in fuzzy_candidates:
        hit = _try(q, MATCHING_CONFIG["ocr_fuzzy_threshold"])
        if hit:
            return hit

    return None


__all__ = [
    "resolve_place",
    "resolve_best_candidate",
    "match_ocr_label",
    "find_geo_entity",
    "find_nearby_candidate_place",
    "polygon_centroid",
    "is_in_bounds",
    "haversine_distance_km",
    "MATCHING_CONFIG",
    "_GEO_INDEX",
    "_CITY_INDEX",
]
