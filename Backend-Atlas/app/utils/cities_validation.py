"""Place-name resolution for OCR labels.

Matches text detected by Florence (OCR) against two gazetteers:

1. **Geographic entities** (countries, provinces, lakes, rivers, …)
    loaded from ``data/geographic_entities.json``.
2. **Cities** from the *geonamescache* library (~24 000 cities worldwide).

When several candidates share the same name the winner is picked by
proximity to ``target_pos`` — the georeferenced position of the OCR
text on the world map — so no hard-coded bias is introduced.

Public API (used by tasks.py and tests):
    resolve_place, match_ocr_label, find_geo_entity, is_in_bounds, capitalize_first
"""

from __future__ import annotations

import difflib
import json
import math
import re
import unicodedata
from pathlib import Path
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


# Geographic-entities gazetteer  (JSON file)
_GEO_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "geographic_entities.json"

# normalized alias → [entity, …]
_GEO_INDEX: Dict[str, List[Dict[str, Any]]] = {}

if _GEO_DATA_PATH.exists():
    with open(_GEO_DATA_PATH, "r", encoding="utf-8") as _f:
        for _entry in json.load(_f):
            for _alias in _entry.get("aliases", []):
                _key = _normalize(_alias)
                if _key:
                    _GEO_INDEX.setdefault(_key, []).append(_entry)


# Political types take priority when multiple entity types share the same name
# (e.g. "Ontario" = province AND lake → province wins).
_POLITICAL_TYPES = frozenset({"country", "continent", "state", "province", "territory"})


def _nearest_candidate(
    candidates: List[Dict[str, Any]],
    target_pos: Optional[Tuple[float, float]] = None,
    bounds: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Pick the candidate closest to *target_pos* (georeferenced OCR position).

    When candidates mix political and physical types (e.g. "Ontario" is both
    a province and a lake), political entities are preferred.
    Fallback order: bounds center → first candidate (no geographic bias).
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    in_bounds = [
        c
        for c in candidates
        if c.get("lat") is not None
        and c.get("lon") is not None
        and (bounds is None or is_in_bounds(c["lat"], c["lon"], bounds))
    ]
    pool = in_bounds or candidates

    # If there's a mix of political vs physical types, keep only political
    political = [c for c in pool if c.get("type") in _POLITICAL_TYPES]
    if political and len(political) < len(pool):
        pool = political

    if target_pos is not None:
        ref_lat, ref_lon = target_pos
    elif bounds is not None:
        ref_lat = (bounds["north"] + bounds["south"]) / 2.0
        ref_lon = (bounds["east"] + bounds["west"]) / 2.0
    else:
        return pool[0]

    def _dist(c: Dict[str, Any]) -> float:
        lat, lon = c.get("lat"), c.get("lon")
        return (
            math.hypot(float(lat) - ref_lat, float(lon) - ref_lon) if lat is not None and lon is not None else float("inf")
        )

    return min(pool, key=_dist)


def find_geo_entity(
    text: str,
    *,
    fuzzy: bool = False,
    cutoff: float = 0.80,
    target_pos: Optional[Tuple[float, float]] = None,
    bounds: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Look up *text* in the geographic-entities JSON.

    Returns the best-matching entity dict or ``None``.
    When *fuzzy=True*, tolerates OCR typos up to *cutoff*.
    """
    norm = _normalize(text)
    if not norm:
        return None

    hits = _GEO_INDEX.get(norm)
    if hits:
        return _nearest_candidate(hits, target_pos, bounds)

    if fuzzy and cutoff < 1.0:
        close = difflib.get_close_matches(norm, _GEO_INDEX.keys(), n=1, cutoff=cutoff)
        if close:
            return _nearest_candidate(_GEO_INDEX[close[0]], target_pos, bounds)

    return None


# Backward-compat aliases used by older call-sites and tests
get_geographic_entity = find_geo_entity


def is_country_or_continent(
    text: str,
    fuzzy: bool = False,
    cutoff: float = 0.80,
    target_pos: Optional[Tuple[float, float]] = None,
    bounds: Optional[Dict[str, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Alias kept for backward compatibility."""
    return find_geo_entity(text, fuzzy=fuzzy, cutoff=cutoff, target_pos=target_pos, bounds=bounds)


# City gazetteer  (geonamescache)
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


# Style definitions for map display: (mapElementType, sizePx, fontStyle, textTransform)
StyleTuple = Tuple[str, int, str, Any]

STYLES_MAP: Dict[str, StyleTuple] = {
    "continent": ("label", 18, "uppercase", str.upper),
    "country": ("label", 16, "uppercase", str.upper),
    "state": ("label", 14, "uppercase", str.upper),
    "province": ("label", 14, "uppercase", str.upper),
    "territory": ("label", 14, "uppercase", str.upper),
    "ocean": ("label", 18, "italic", str.upper),
    "sea": ("label", 16, "italic", capitalize_first),
    "fleuve": ("label", 14, "italic", capitalize_first),
    "lake": ("label", 12, "italic", capitalize_first),
    "river": ("label", 10, "italic", capitalize_first),
}
DEFAULT_STYLE: StyleTuple = ("point", 12, "normal", capitalize_first)


# Common geographic prefixes preserved for display nomenclature only if detected in extraction query
_GEOGRAPHIC_PREFIXES = (
    ("province de l ", "Province de l'"),
    ("province d ", "Province d'"),
    ("province de ", "Province de "),
    ("province du ", "Province du "),
    ("province des ", "Province des "),
    ("territoire du ", "Territoire du "),
    ("territoire de ", "Territoire de "),
    ("territoire des ", "Territoire des "),
    ("territoire d ", "Territoire d'"),
    ("district de ", "District de "),
    ("district du ", "District du "),
    ("district d ", "District d'"),
    ("etat de ", "État de "),
    ("ocean ", "Océan "),
    ("mer ", "Mer "),
    ("lac ", "Lac "),
    ("fleuve ", "Fleuve "),
    ("riviere ", "Rivière "),
    ("baie d ", "Baie d'"),
    ("baie de ", "Baie de "),
    ("golfe du ", "Golfe du "),
    ("detroit de ", "Détroit de "),
    ("detroit d ", "Détroit d'"),
    ("ile du ", "Île-du-"),
    ("ile de ", "Île de "),
    ("ile d ", "Île d'"),
    ("iles de l ", "Îles de l'"),
    ("iles ", "Îles "),
)


def _preserve_prefix_nomenclature(raw_name: str, query: str) -> str:
    """Preserve terms like 'Province de ...', 'Océan ...', 'Territoire de ...' only if present in extraction query."""
    norm_query = _normalize(query)
    norm_raw = _normalize(raw_name)

    for prefix_norm, prefix_display in _GEOGRAPHIC_PREFIXES:
        if norm_query.startswith(prefix_norm):
            # Only attach if raw_name does not already have a geographic prefix
            for p_norm, _ in _GEOGRAPHIC_PREFIXES:
                if norm_raw.startswith(p_norm):
                    return raw_name
            return f"{prefix_display}{capitalize_first(raw_name)}"
    return raw_name


def _not_found(text: str) -> Dict[str, Any]:
    """Canonical 'not found' result."""
    return {"found": False, "query": text, "name": text, "lat": 0.0, "lon": 0.0, "geonameid": None, "matched_text": None}


def _geo_result(geo: Dict[str, Any], query: str, base: Dict[str, Any]) -> Dict[str, Any]:
    """Format a geographic-entity match as a result dict using STYLES_MAP."""
    raw_name = geo.get("name_fr") or geo.get("name", query)
    raw_name = _preserve_prefix_nomenclature(raw_name, query)
    geo_type = geo.get("type") or "country"

    map_element_type, size_px, font_style, transform_func = STYLES_MAP.get(geo_type, DEFAULT_STYLE)
    display = transform_func(raw_name)

    return {
        **base,
        "found": True,
        "name": display,
        "lat": geo["lat"],
        "lon": geo["lon"],
        "geonameid": geo.get("geonameid") or f"{geo_type}:{geo.get('name')}",
        "type": geo_type,
        "mapElementType": map_element_type,
        "sizePx": size_px,
        "fontStyle": font_style,
        "matched_text": _normalize(query),
    }


def _city_result(city: Dict[str, Any], query: str) -> Dict[str, Any]:
    """Format a city match as a result dict using DEFAULT_STYLE."""
    map_element_type, size_px, font_style, transform_func = DEFAULT_STYLE
    raw_name = city.get("name") or query
    display = transform_func(raw_name)
    return {
        "found": True,
        "query": query,
        "geonameid": city.get("geonameid"),
        "name": display,
        "lat": city.get("lat"),
        "lon": city.get("lon"),
        "population": city.get("population"),
        "mapElementType": map_element_type,
        "sizePx": size_px,
        "fontStyle": font_style,
        "matched_text": _normalize(query),
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


# Sentinel for "matched but out of bounds → reject immediately"
_BLOCKED = object()


def resolve_place(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
    confidence_threshold: float = 0.80,
    geo_bounds: Optional[Dict[str, float]] = None,
    target_pos: Optional[Tuple[float, float]] = None,
) -> Dict[str, Any]:
    """Resolve an OCR text string to a geographic place (entity or city).

    Resolution order depends on casing:
    - **ALL-CAPS** → geographic entities first (provinces, countries, …), then cities.
    - **Title / lower** → cities first, then geographic entities.

    Returns a dict that always contains ``found`` (bool).
    """
    key = _normalize(text)
    if not key:
        return _not_found(text)

    bounds = frame_bounds if frame_bounds is not None else geo_bounds
    base = _not_found(text)

    def _match_geo(fuzzy: bool = False, cutoff: float = 0.80) -> Any:
        ent = find_geo_entity(key, fuzzy=fuzzy, cutoff=cutoff, target_pos=target_pos, bounds=bounds)
        if ent is None:
            return None
        return _geo_result(ent, text, base) if is_in_bounds(ent["lat"], ent["lon"], bounds) else _BLOCKED

    def _match_city_exact() -> Optional[Dict[str, Any]]:
        cands = _city_map_in_bounds(key, bounds)
        if not cands:
            return None
        return _city_result(max(cands, key=lambda c: c.get("population", 0)), text)

    def _match_city_fuzzy(cutoff: float) -> Optional[Dict[str, Any]]:
        valid_keys = [k for k, v in _CITY_INDEX.items() if _any_in_bounds(v, bounds)] if bounds else list(_CITY_INDEX.keys())
        close = difflib.get_close_matches(key, valid_keys, n=1, cutoff=cutoff)
        if not close:
            return None
        cands = _city_map_in_bounds(close[0], bounds)
        if not cands:
            return None
        return _city_result(max(cands, key=lambda c: c.get("population", 0)), text)

    if text.isupper():
        # ALL-CAPS → prefer geographic entity
        geo = _match_geo()
        if geo is _BLOCKED:
            return base
        if geo:
            return geo
        city = _match_city_exact()
        if city:
            return city
    else:
        # Title / lowercase → prefer city
        city = _match_city_exact()
        if city:
            return city
        geo = _match_geo()
        if geo is _BLOCKED:
            return base
        if geo:
            return geo

    if confidence_threshold < 1.0:
        geo_f = _match_geo(fuzzy=True, cutoff=confidence_threshold)
        if geo_f is _BLOCKED:
            return base
        if geo_f:
            return geo_f

        city_f = _match_city_fuzzy(confidence_threshold)
        if city_f:
            return city_f

    return base


# Backward-compat alias
get_city_with_max_population = resolve_place


def _city_map_in_bounds(norm_key: str, bounds: Optional[Dict[str, float]]) -> List[Dict[str, Any]]:
    cands = _CITY_INDEX.get(norm_key, [])
    return [c for c in cands if is_in_bounds(c["lat"], c["lon"], bounds)] if bounds else list(cands)


def _any_in_bounds(cands: List[Dict[str, Any]], bounds: Optional[Dict[str, float]]) -> bool:
    return any(is_in_bounds(c["lat"], c["lon"], bounds) for c in cands)


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
    # If no letters at all (only digits, symbols, punctuation) -> reject
    if not any(c.isalpha() for c in s):
        return False
    # Less than 2 letters -> word too short / OCR noise -> reject
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 2:
        return False
    # Block legend / scale / annotation keywords
    s_lower = s.lower()
    for kw in ("echelle", "échelle", "scale", "legende", "légende", "annotation"):
        if kw in s_lower and len(s_lower.split()) <= 4:
            return False
    return True


# OCR label matcher  (called from tasks.py)
def match_ocr_label(
    text: str,
    frame_bounds: Optional[Dict[str, float]] = None,
    target_pos: Optional[Tuple[float, float]] = None,
) -> Optional[Dict[str, Any]]:
    """Match an OCR text label against both gazetteers.

    Tries the whole text first (exact then fuzzy),
    then falls back to matching line-by-line for multi-line blocks.
    Returns the matched place dict or ``None``.
    """
    clean = str(text or "").strip()
    if not clean:
        return None

    def _try(query: str, threshold: float) -> Optional[Dict[str, Any]]:
        if not is_exploitable_text(query):
            return None
        try:
            res = resolve_place(query, frame_bounds=frame_bounds, confidence_threshold=threshold, target_pos=target_pos)
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
            hit = _try(ln, 0.60)
            if hit:
                return hit
    else:
        hit = _try(whole, 0.60)
        if hit:
            return hit

    return None


__all__ = [
    "resolve_place",
    "get_city_with_max_population",
    "match_ocr_label",
    "find_geo_entity",
    "get_geographic_entity",
    "is_country_or_continent",
    "is_in_bounds",
    "capitalize_first",
    "haversine_distance_km",
    "find_nearby_candidate_city",
    "is_exploitable_text",
    "_normalize",
    "_city_map",
    "STYLES_MAP",
    "DEFAULT_STYLE",
    "StyleTuple",
]

_city_map = _CITY_INDEX
