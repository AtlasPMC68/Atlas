"""Place-name resolution for OCR labels.

Matches text detected by Florence (OCR) against the city gazetteer
from the geonamescache library (~24 000 cities worldwide).

When several candidates share the same name in the bounding area,
the winner is picked by highest population.

Public API (used by tasks.py and tests):
    resolve_place, get_city_with_max_population, match_ocr_label, is_in_bounds,
    capitalize_first, haversine_distance_km, find_nearby_candidate_city, is_exploitable_text
"""

from __future__ import annotations

import difflib
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import geonamescache


def _normalize(text: str) -> str:
    """Lower-case, strip accents, collapse whitespace."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.casefold().strip()


def capitalize_first(s: str) -> str:
    """``'québec'`` → ``'Québec'``."""
    return s[:1].upper() + s[1:] if s else s


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
    return s <= lat <= n and w <= lon <= e


def _parse_pop(val: Any) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


# City gazetteer (geonamescache)
_gc = geonamescache.GeonamesCache()
_CITY_INDEX: Dict[str, List[Dict[str, Any]]] = {}

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

_city_map = _CITY_INDEX


def _city_map_in_bounds(norm_key: str, bounds: Optional[Dict[str, float]]) -> List[Dict[str, Any]]:
    cands = _CITY_INDEX.get(norm_key, [])
    return [c for c in cands if is_in_bounds(c["lat"], c["lon"], bounds)] if bounds else list(cands)


def _any_in_bounds(cands: List[Dict[str, Any]], bounds: Optional[Dict[str, float]]) -> bool:
    return any(is_in_bounds(c["lat"], c["lon"], bounds) for c in cands)


def _not_found(text: str) -> Dict[str, Any]:
    """Canonical 'not found' result."""
    return {
        "found": False,
        "query": text,
        "name": text,
        "lat": 0.0,
        "lon": 0.0,
        "geonameid": None,
        "matched_text": None,
        "is_exact": False,
    }


def _city_result(
    city: Dict[str, Any],
    query: str,
    is_exact: bool = True,
    matched_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Format a city match as a result dict."""
    raw_name = city.get("name") or query
    return {
        "found": True,
        "query": query,
        "geonameid": city.get("geonameid"),
        "name": raw_name,
        "lat": city.get("lat"),
        "lon": city.get("lon"),
        "population": city.get("population"),
        "mapElementType": "point",
        "matched_text": matched_text or _normalize(query),
        "is_exact": is_exact,
    }


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def find_nearby_candidate_city(
    text: str,
    coords: List[float],
    radius_km: float = 75.0,
) -> Optional[Dict[str, Any]]:
    """Find a candidate city within radius_km of coordinates [lon, lat]."""
    if not coords or len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    key = _normalize(text)

    nearby_cities: List[tuple[float, Dict[str, Any]]] = []
    for city_list in _CITY_INDEX.values():
        for c in city_list:
            if abs(c["lat"] - lat) * 111.0 > radius_km:
                continue
            dist = haversine_distance_km(lat, lon, c["lat"], c["lon"])
            if dist <= radius_km:
                nearby_cities.append((dist, c))

    if not nearby_cities:
        return None

    if key:
        scored = [
            (difflib.SequenceMatcher(None, key, _normalize(c.get("name", ""))).ratio(), -dist, c)
            for dist, c in nearby_cities
        ]
        best_sim, _, best_city = max(scored, key=lambda x: (x[0], x[1]))
        if best_sim >= 0.45:
            return best_city

    return min(nearby_cities, key=lambda x: x[0])[1]


def resolve_place(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
    confidence_threshold: float = 0.80,
    geo_bounds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Resolve an OCR text string to a known city.

    Performs a direct match against the city gazetteer, with a fallback
    to difflib fuzzy matching using confidence_threshold.
    """
    key = _normalize(text)
    if not key:
        return _not_found(text)

    bounds = frame_bounds if frame_bounds is not None else geo_bounds

    # Exact match
    cands = _city_map_in_bounds(key, bounds)
    if cands:
        best = max(cands, key=lambda c: c.get("population", 0))
        return _city_result(best, text, is_exact=True, matched_text=key)

    # Fuzzy match fallback
    if confidence_threshold < 1.0:
        valid_keys = [k for k, v in _CITY_INDEX.items() if _any_in_bounds(v, bounds)] if bounds else list(_CITY_INDEX.keys())
        close = difflib.get_close_matches(key, valid_keys, n=1, cutoff=confidence_threshold)
        if close:
            cands = _city_map_in_bounds(close[0], bounds)
            if cands:
                best = max(cands, key=lambda c: c.get("population", 0))
                return _city_result(best, text, is_exact=False, matched_text=close[0])

    return _not_found(text)


get_city_with_max_population = resolve_place


def is_exploitable_text(text: str) -> bool:
    """Check if text is usable:
    - empty string -> reject
    - numbers or symbols only -> reject
    - legend / scale / annotation keywords -> reject
    - noisy / parasitic text -> reject
    - word too short / OCR noise -> reject
    """
    if not text:
        return False
    s = str(text).strip()
    if not s:
        return False
    if not any(c.isalpha() for c in s):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    s_lower = s.lower()
    for kw in ("echelle", "échelle", "scale", "legende", "légende", "annotation"):
        if kw in s_lower and len(s_lower.split()) <= 4:
            return False
    return True


def match_ocr_label(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Match an OCR text label against the city gazetteer.

    Tries the whole text first (exact then fuzzy),
    then falls back to matching line-by-line for multi-line blocks.
    Returns the matched city dict or ``None``.
    """
    clean = str(text or "").strip()
    if not clean:
        return None

    def _try(query: str, threshold: float) -> Optional[Dict[str, Any]]:
        if not is_exploitable_text(query):
            return None
        try:
            res = resolve_place(query, frame_bounds=frame_bounds, confidence_threshold=threshold)
            return res if res.get("found") else None
        except Exception:
            return None

    whole = clean.replace("\n", " ")

    # 1) Exact on whole text
    hit = _try(whole, 1.0)
    if hit:
        return hit

    lines = [ln.strip() for ln in clean.split("\n") if ln.strip()]

    # 2) Exact on each line
    if len(lines) > 1:
        for ln in lines:
            hit = _try(ln, 1.0)
            if hit:
                return hit

    # 3) Fuzzy
    if len(lines) > 1:
        for ln in lines:
            hit = _try(ln, 0.85)
            if hit:
                return hit
    else:
        hit = _try(whole, 0.85)
        if hit:
            return hit

    return None


__all__ = [
    "resolve_place",
    "get_city_with_max_population",
    "match_ocr_label",
    "is_in_bounds",
    "capitalize_first",
    "haversine_distance_km",
    "find_nearby_candidate_city",
    "is_exploitable_text",
    "_normalize",
    "_city_map",
]
