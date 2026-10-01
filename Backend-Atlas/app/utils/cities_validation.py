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
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


def _normalize_query(s: str) -> str:
    """Like _normalize but also replaces punctuation and extra whitespace with single spaces."""
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
        "name": name,
        "lat": lat,
        "lon": lon,
        "country": country,
        "population": _parse_population(info.get("population")),
    }

    key = _normalize(name)
    _city_map.setdefault(key, []).append(city_entry)

    query_key = _normalize_query(name)
    if query_key != key:
        _city_map.setdefault(query_key, []).append(city_entry)

import difflib

__all__ = ["_city_map", "find_first_city"]


def find_first_city(
    text: str,
    geo_bounds: Optional[Dict[str, float]] = None,
    confidence_threshold: float = 0.60,
) -> Dict[str, Any]:
    """Return a standardized result for a city search.

    Performs a direct full-string match (accent/case insensitive, punctuation stripped)
    against the city gazetteer, with a fallback to difflib.get_close_matches using
    confidence_threshold (default 0.80) to recover minor OCR typos.
    When geo_bounds is provided (``{'min_lon': ..., 'max_lon': ..., 'min_lat': ..., 'max_lat': ...}``),
    only candidates whose coordinates fall inside that rectangle are considered.

    Always returns a dict with at least the keys:
      - ``found``: bool
      - ``query``: the original text passed in
      - ``name``, ``lat``, ``lon``: populated when ``found`` is True
      - ``matched_text``: normalised query string when found, else None
    """
    result: Dict[str, Any] = {
        "found": False,
        "query": text,
        "name": text,
        "lat": 0.0,
        "lon": 0.0,
        "matched_text": None,
    }

    key = _normalize_query(text)
    if not key:
        return result

    candidates: List[Dict[str, Any]] = list(_city_map.get(key, []))

    # Fuzzy matching fallback if no exact match found
    matched_key = key
    if not candidates and confidence_threshold < 1.0:
        close_matches = difflib.get_close_matches(key, _city_map.keys(), n=1, cutoff=confidence_threshold)
        if close_matches:
            matched_key = close_matches[0]
            candidates = list(_city_map.get(matched_key, []))

    if not candidates:
        return result

    if geo_bounds is not None:
        bounded = [c for c in candidates if geo_bounds["min_lat"] <= c["lat"] <= geo_bounds["max_lat"] and geo_bounds["min_lon"] <= c["lon"] <= geo_bounds["max_lon"]]
        candidates = bounded if bounded else []

    if not candidates:
        return result

    best = max(candidates, key=lambda c: c.get("population", 0))
    result.update(
        {
            "found": True,
            "name": best.get("name"),
            "lat": best.get("lat"),
            "lon": best.get("lon"),
            "matched_text": matched_key,
        }
    )
    return result
