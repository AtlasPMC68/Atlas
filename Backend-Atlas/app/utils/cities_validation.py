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
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

try:
    import requests_cache
except Exception:
    requests_cache = None


_WORD_RE = re.compile(r"\b[\w\-']+\b", flags=re.UNICODE)


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


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
    key = _normalize(name)
    _city_map.setdefault(key, []).append({
        "name": name,
        "lat": lat,
        "lon": lon,
        "country": country,
        "population": info.get("population"),
    })


# Setup Nominatim geolocator with requests cache and rate limiter
if requests_cache is not None:
    try:
        requests_cache.install_cache("nominatim_cache", expire_after=60 * 60 * 24)
    except Exception:
        pass

_geolocator = Nominatim(user_agent="atlas_geocoder")
_geocode_rate_limited = RateLimiter(_geolocator.geocode, min_delay_seconds=1.0)


def detect_cities_from_text(
    text: str, max_ngram: int = 4, use_search: bool = False, search_limit: int = 10
) -> List[Dict[str, Any]]:
    """Scan text for city names using the local gazetteer.

    Returns a list of matches with the matched text span (as tokens), and local candidates.

    Each match: {
        'text': original_phrase,
        'start_token': int,
        'end_token': int,
        'candidates': [ { 'name','lat','lon','country',... } ]
    }
    """
    tokens = _WORD_RE.findall(text)
    norm_tokens = [_normalize(t) for t in tokens]
    matches: List[Dict[str, Any]] = []
    i = 0
    L = len(tokens)
    while i < L:
        found = False
        for n in range(min(max_ngram, L - i), 0, -1):
            phrase = " ".join(tokens[i : i + n])
            key = _normalize(phrase)
            candidates: List[Dict[str, Any]] = []

            # Exact lookup in prebuilt map (fast)
            if key in _city_map:
                candidates = _city_map.get(key, [])

            # Optionally use geonamescache.search_cities for contains/fuzzy matching
            elif use_search:
                try:
                    raw = _gc.search_cities(phrase, case_sensitive=False, contains_search=True)
                except Exception:
                    raw = None

                if raw:
                    items = raw.values() if isinstance(raw, dict) else raw
                    for info in items:
                        try:
                            name = info.get("name") or info.get("toponymName") or ""
                            lat = float(info.get("latitude") or info.get("lat") or 0)
                            lon = float(info.get("longitude") or info.get("lng") or 0)
                            country = info.get("countrycode") or info.get("countryCode") or ""
                        except Exception:
                            continue
                        candidates.append({
                            "name": name,
                            "lat": lat,
                            "lon": lon,
                            "country": country,
                            "population": info.get("population"),
                        })
                    # optionally trim to search_limit
                    if search_limit and len(candidates) > search_limit:
                        candidates = candidates[:search_limit]

            if candidates:
                matches.append(
                    {
                        "text": phrase,
                        "start_token": i,
                        "end_token": i + n - 1,
                        "candidates": candidates,
                    }
                )
                i += n
                found = True
                break
        if not found:
            i += 1
    return matches


def geocode_fallback(place_name: str, countrycodes: Optional[List[str]] = None, limit: int = 3) -> List[Dict[str, Any]]:
    """Use Nominatim to geocode place_name when local gazetteer fails.

    Returns a list of candidate dicts with keys: name, lat, lon, raw.
    """
    params = {"exactly_one": False, "limit": limit}
    if countrycodes:
        params["country_codes"] = ",".join(countrycodes)

    try:
        results = _geocode_rate_limited(place_name, **params)
    except Exception:
        return []

    if not results:
        return []

    out: List[Dict[str, Any]] = []
    for r in results:
        if r is None:
            continue
        try:
            lat = float(r.latitude)
            lon = float(r.longitude)
        except Exception:
            continue
        out.append({"name": getattr(r, "address", None) or r.address, "lat": lat, "lon": lon, "raw": getattr(r, "raw", None)})
    return out


_all_ = ["detect_cities_from_text", "geocode_fallback", "_city_map", "find_first_city"]


def find_first_city(text: str):
    """Return the best local city candidate found in `text` or False.

    The function calls `detect_cities_from_text(text)` and returns a dict with
    keys `name`, `lat`, `lon`, and `matched_text` for the best candidate (by
    population where available). If no local candidate is found, returns
    False.
    """
    matches = detect_cities_from_text(text)
    if not matches:
        return False

    for m in matches:
        candidates = m.get("candidates") or []
        if not candidates:
            continue
        # pick candidate with largest population when available
        def pop_key(c):
            try:
                return int(c.get("population") or 0)
            except Exception:
                return 0

        best = max(candidates, key=pop_key)
        return {
            "name": best.get("name"),
            "lat": best.get("lat"),
            "lon": best.get("lon"),
            "matched_text": m.get("text"),
        }

    return False