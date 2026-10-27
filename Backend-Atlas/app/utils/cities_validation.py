"""City detection and geocoding helpers.

This module provides:
- an in-memory city gazetteer (from geonamescache) for fast word/phrase matching
- a Nominatim-based fallback geocoder (via geopy) with rate-limiting and requests caching

Usage:
    from app.utils.geocoding import detect_cities_from_text, geocode_fallback

    matches = detect_cities_from_text(text)
    for m in matches:
        if not m['candidates']:
            # no local match, fall back to Nominatim
            geocoded = geocode_fallback(m['text'])
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Dict, Any, Optional

import geonamescache

_WORD_RE = re.compile(r"\b[\w\-']+\b", flags=re.UNICODE)


def _normalize(s: str) -> str:
    """Normalize text by removing accents, punctuation, and extra whitespace."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s)
    return s.casefold().strip()


def _parse_population(pop_val: Any) -> int:
    try:
        return int(pop_val or 0)
    except (TypeError, ValueError):
        return 0


# Load geonamescache cities into a mapping: normalized name -> list of candidate dicts
_gc = geonamescache.GeonamesCache()
_city_map: Dict[str, List[Dict[str, Any]]] = {}
for info in _gc.get_cities().values():
    name = info.get("name") or ""
    country = info.get("countrycode") or ""
    try:
        lat = float(info.get("latitude"))
        lon = float(info.get("longitude"))
    except Exception:
        continue
    city_entry = {
        "geonameid": info.get("geonameid"),
        "name": name,
        "lat": lat,
        "lon": lon,
        "country": country,
        "population": _parse_population(info.get("population")),
    }

    key = _normalize(name)
    _city_map.setdefault(key, []).append(city_entry)

import difflib
import math

__all__ = ["_city_map", "get_city_with_max_population", "match_ocr_label", "find_nearby_candidate_city"]


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
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
    for city_list in _city_map.values():
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


def get_city_with_max_population(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
    confidence_threshold: float = 0.80,
    geo_bounds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Return a standardized result for a city search.

    Performs a direct full-string match (accent/case insensitive, punctuation stripped)
    against the city gazetteer, with a fallback to difflib.get_close_matches using
    confidence_threshold (default 0.80) to recover minor OCR typos.
    When frame_bounds (or geo_bounds) is provided, only candidates whose coordinates fall
    inside that rectangle are considered. Supports both {'west', 'south', 'east', 'north'}
    and {'min_lon', 'max_lon', 'min_lat', 'max_lat'}.

    Always returns a dict with at least the keys:
      - ``found``: bool
      - ``query``: the original text passed in
      - ``geonameid``: geoname identifier when found, else None
      - ``name``, ``lat``, ``lon``: populated when ``found`` is True
      - ``matched_text``: normalised query string when found, else None
    """
    result: Dict[str, Any] = {
        "found": False,
        "query": text,
        "name": text,
        "lat": 0.0,
        "lon": 0.0,
        "geonameid": None,
        "matched_text": None,
    }

    key = _normalize(text)
    if not key:
        return result

    bounds = frame_bounds if frame_bounds is not None else geo_bounds

    def filter_by_bounds(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if bounds is None:
            return cands
        min_lat = bounds.get("south", bounds.get("min_lat"))
        max_lat = bounds.get("north", bounds.get("max_lat"))
        min_lon = bounds.get("west", bounds.get("min_lon"))
        max_lon = bounds.get("east", bounds.get("max_lon"))
        if min_lat is None or max_lat is None or min_lon is None or max_lon is None:
            return cands
        return [
            c
            for c in cands
            if min_lat <= c["lat"] <= max_lat and min_lon <= c["lon"] <= max_lon
        ]

    matched_key = key
    candidates = filter_by_bounds(list(_city_map.get(key, [])))

    # Fuzzy matching fallback if no valid exact match found
    if not candidates and confidence_threshold < 1.0:
        if bounds is not None:
            valid_keys = [k for k, v in _city_map.items() if filter_by_bounds(v)]
        else:
            valid_keys = list(_city_map.keys())

        close_matches = difflib.get_close_matches(key, valid_keys, n=1, cutoff=confidence_threshold)
        if close_matches:
            matched_key = close_matches[0]
            candidates = filter_by_bounds(list(_city_map.get(matched_key, [])))

    if not candidates:
        return result

    best = max(candidates, key=lambda c: c.get("population", 0))

    result.update(
        {
            "found": True,
            "geonameid": best.get("geonameid"),
            "name": best.get("name"),
            "lat": best.get("lat"),
            "lon": best.get("lon"),
            "country": best.get("country"),
            "population": best.get("population"),
            "matched_text": matched_key,
            "is_exact": matched_key == key,
        }
    )
    return result


def match_ocr_label(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Match OCR text against known cities within bounds."""
    clean = str(text or "").strip()
    if not clean:
        return None

    cand = get_city_with_max_population(
        clean.replace("\n", " "), frame_bounds=frame_bounds, confidence_threshold=0.85
    )
    if cand.get("found"):
        return cand

    if "\n" in clean:
        for line in clean.splitlines():
            line = line.strip()
            if line:
                cand = get_city_with_max_population(
                    line, frame_bounds=frame_bounds, confidence_threshold=0.85
                )
                if cand.get("found"):
                    return cand

    return None
