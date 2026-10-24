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

import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

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


# Offline geographic entities dataset (countries, continents, lakes, seas, oceans, rivers)

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "geographic_entities.json"
_GEOGRAPHIC_ENTITIES: Dict[str, Dict[str, Any]] = {}

if _DATA_PATH.exists():
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        for _entry in json.load(f):
            for _alias in _entry.get("aliases", []):
                _norm = _normalize(_alias)
                if _norm:
                    _GEOGRAPHIC_ENTITIES[_norm] = _entry


def get_geographic_entity(text: str, fuzzy: bool = False, cutoff: float = 0.80) -> Optional[Dict[str, Any]]:
    """Return entity (country, continent, ocean, sea, lake) if text matches, else None.

    Supports exact lookup by default, or fuzzy matching when fuzzy=True to recover OCR typos.
    """
    norm = _normalize(text)
    if not norm:
        return None
    entity = _GEOGRAPHIC_ENTITIES.get(norm)
    if entity is not None:
        return entity
    if fuzzy and cutoff < 1.0:
        matches = difflib.get_close_matches(norm, _GEOGRAPHIC_ENTITIES.keys(), n=1, cutoff=cutoff)
        if matches:
            return _GEOGRAPHIC_ENTITIES[matches[0]]
    return None


def is_country_or_continent(text: str, fuzzy: bool = False, cutoff: float = 0.80) -> Optional[Dict[str, Any]]:
    """Alias for get_geographic_entity: returns non-city geographic entity or None."""
    return get_geographic_entity(text, fuzzy=fuzzy, cutoff=cutoff)


# Load geonamescache cities into a mapping: normalized name -> list of candidates
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
    if key.endswith(" city"):
        base_key = key[:-5].strip()
        if base_key:
            _city_map.setdefault(base_key, []).append(city_entry)


def is_in_bounds(lat: float, lon: float, bounds: Optional[Dict[str, float]]) -> bool:
    """Check if a coordinate (lat, lon) falls inside a geographic bounding box."""
    if bounds is None:
        return True
    min_lat = bounds.get("south", bounds.get("min_lat"))
    max_lat = bounds.get("north", bounds.get("max_lat"))
    min_lon = bounds.get("west", bounds.get("min_lon"))
    max_lon = bounds.get("east", bounds.get("max_lon"))
    if min_lat is None or max_lat is None or min_lon is None or max_lon is None:
        return True
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def capitalize_first(s: str) -> str:
    """Capitalize the first character of a string while preserving the rest."""
    if not s:
        return s
    return s[0].upper() + s[1:]


__all__ = [
    "_city_map",
    "get_city_with_max_population",
    "match_ocr_label",
    "get_geographic_entity",
    "is_country_or_continent",
    "is_in_bounds",
    "capitalize_first",
]


def get_city_with_max_population(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
    confidence_threshold: float = 0.80,
    geo_bounds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Return a standardized result for a city or geographic feature search.

    Checks offline geographic entities (countries, continents, oceans, seas, lakes):
       if matched, validates coordinates against frame_bounds (or geo_bounds).
       If within bounds, returns the geographic entity. If out of bounds, rejects immediately
       to prevent false fuzzy city matching.
    Performs an exact city gazetteer lookup (accent/case insensitive) filtered by bounds.
    As a last resort, uses difflib.get_close_matches among in-bounds cities to recover OCR typos.

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

    def _format_geo_result(geo: Dict[str, Any], query_key: str) -> Dict[str, Any]:
        raw_name = geo.get("name_fr") or geo.get("name", text)
        geo_type = geo.get("type")
        if geo_type in ("country", "continent", "state", "province", "territory"):
            entity_name = raw_name.upper()
        else:
            entity_name = capitalize_first(raw_name)
        res = dict(result)
        res.update(
            {
                "found": True,
                "name": entity_name,
                "lat": geo["lat"],
                "lon": geo["lon"],
                "geonameid": geo.get("geonameid") or f"{geo.get('type', 'geo')}:{geo.get('name')}",
                "type": geo.get("type"),
                "matched_text": query_key,
            }
        )
        return res

    _BLOCKED_OUT_OF_BOUNDS = object()

    def filter_by_bounds(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if bounds is None:
            return cands
        return [c for c in cands if is_in_bounds(c["lat"], c["lon"], bounds)]

    def _try_exact_geo() -> Optional[Any]:
        geo_entity = get_geographic_entity(key, fuzzy=False)
        if geo_entity is not None:
            if is_in_bounds(geo_entity["lat"], geo_entity["lon"], bounds):
                return _format_geo_result(geo_entity, key)
            return _BLOCKED_OUT_OF_BOUNDS
        return None

    def _try_exact_city() -> Optional[Dict[str, Any]]:
        candidates = filter_by_bounds(list(_city_map.get(key, [])))
        if candidates:
            best = max(candidates, key=lambda c: c.get("population", 0))
            return {
                "found": True,
                "query": text,
                "geonameid": best.get("geonameid"),
                "name": capitalize_first(best.get("name") or text),
                "lat": best.get("lat"),
                "lon": best.get("lon"),
                "country": best.get("country"),
                "population": best.get("population"),
                "matched_text": key,
            }
        return None

    def _try_fuzzy_geo(cutoff: float) -> Optional[Any]:
        fuzzy_geo = get_geographic_entity(key, fuzzy=True, cutoff=cutoff)
        if fuzzy_geo is not None:
            if is_in_bounds(fuzzy_geo["lat"], fuzzy_geo["lon"], bounds):
                return _format_geo_result(fuzzy_geo, key)
            return _BLOCKED_OUT_OF_BOUNDS
        return None

    def _try_fuzzy_city(cutoff: float) -> Optional[Dict[str, Any]]:
        if bounds is not None:
            valid_keys = [k for k, v in _city_map.items() if filter_by_bounds(v)]
        else:
            valid_keys = list(_city_map.keys())
        close_matches = difflib.get_close_matches(key, valid_keys, n=1, cutoff=cutoff)
        if close_matches:
            matched_k = close_matches[0]
            candidates = filter_by_bounds(list(_city_map.get(matched_k, [])))
            if candidates:
                best = max(candidates, key=lambda c: c.get("population", 0))
                return {
                    "found": True,
                    "query": text,
                    "geonameid": best.get("geonameid"),
                    "name": capitalize_first(best.get("name") or text),
                    "lat": best.get("lat"),
                    "lon": best.get("lon"),
                    "country": best.get("country"),
                    "population": best.get("population"),
                    "matched_text": matched_k,
                }
        return None

    # Priority rule based on casing:
    # If the text is ALL-CAPS (e.g. "QUÉBEC", "NEW YORK"), prioritize geographic entities from JSON (states, countries, lakes, rivers).
    # If the text has lowercase letters (Title Case or lowercase, e.g. "Québec", "New York"), prioritize cities from geonamescache.
    is_all_caps = text.isupper()

    if is_all_caps:
        # 1. Exact match against JSON geographic entities
        geo_res = _try_exact_geo()
        if geo_res is not None:
            if geo_res is _BLOCKED_OUT_OF_BOUNDS:
                return result
            return geo_res

        city_res = _try_exact_city()
        if city_res is not None:
            return city_res
    else:

        city_res = _try_exact_city()
        if city_res is not None:
            return city_res

        geo_res = _try_exact_geo()
        if geo_res is not None:
            if geo_res is _BLOCKED_OUT_OF_BOUNDS:
                return result
            return geo_res

    # Fuzzy matches (when neither was an exact match):
    # Check geographic entities first to recover typos on countries/states/lakes without
    # falsely matching obscure cities, then check cities in bounds.
    if confidence_threshold < 1.0:
        fuzzy_geo = _try_fuzzy_geo(confidence_threshold)
        if fuzzy_geo is not None:
            if fuzzy_geo is _BLOCKED_OUT_OF_BOUNDS:
                return result
            return fuzzy_geo

        fuzzy_city = _try_fuzzy_city(confidence_threshold)
        if fuzzy_city is not None:
            return fuzzy_city

    return result


def match_ocr_label(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Match an OCR text label against the city and geographic entities gazetteer within frame_bounds.

    Tries the whole text first, then falls back to matching line by line.
    Returns the matched city/entity dict (with 'geonameid', 'name', 'lat', 'lon', etc.)
    or None if no match was found. Pure function: does not persist anything.
    """
    clean = str(text or "").strip()
    if not clean:
        return None

    def _try_match(query: str, threshold: float = 0.60) -> Optional[Dict[str, Any]]:
        try:
            cand = get_city_with_max_population(query, frame_bounds=frame_bounds, confidence_threshold=threshold)
            if cand.get("found"):
                return cand
        except Exception:
            pass
        return None

    # Try exact match on whole text (e.g. multi-word place: "New York" or "New\nYork")
    whole_clean = clean.replace("\n", " ")
    matched = _try_match(whole_clean, threshold=1.0)
    if matched is not None:
        return matched

    lines = [line.strip() for line in clean.split("\n") if line.strip()]

    # If multi-line, try exact match line by line
    if len(lines) > 1:
        for line in lines:
            matched_line = _try_match(line, threshold=1.0)
            if matched_line is not None:
                return matched_line

    # Fall back to fuzzy match (line-by-line for multi-line text, or whole query if single line)
    if len(lines) > 1:
        for line in lines:
            matched_line = _try_match(line, threshold=0.60)
            if matched_line is not None:
                return matched_line
    else:
        matched = _try_match(whole_clean, threshold=0.60)
        if matched is not None:
            return matched

    return None
