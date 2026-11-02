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


_WORD_STYLE_CONFIG_PATH = Path(__file__).resolve().parents[3] / "shared" / "word-taxonomy.json"
with _WORD_STYLE_CONFIG_PATH.open(encoding="utf-8") as _config_file:
    _WORD_STYLE_CONFIG = json.load(_config_file)


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


_LOWERCASE_PARTICLES = set(_WORD_STYLE_CONFIG["capitalization"]["lowercaseParticles"])
_APOSTROPHE_PREFIXES = tuple(_WORD_STYLE_CONFIG["capitalization"]["apostrophePrefixes"])
_APOSTROPHE_PREFIX_PATTERN = re.compile(
    rf"^([{''.join(re.escape(prefix) for prefix in _APOSTROPHE_PREFIXES)}]['’])(.*)$",
    flags=re.IGNORECASE,
)


def capitalize_words(text: str) -> str:
    """Capitalize each word/term in a place name, preserving hyphens and French particles.
    E.g. 'new york city' -> 'New York City'
         'saint-pierre' -> 'Saint-Pierre'
         'golfe du mexique' -> 'Golfe du Mexique'
         'mer du labrador' -> 'Mer du Labrador'
         'baie d\'hudson' -> 'Baie d\'Hudson'
    """
    if not text:
        return text

    parts = re.split(r"([\s\-]+)", text)
    result = []
    word_idx = 0

    for part in parts:
        if not part:
            continue
        if re.match(r"^[\s\-]+$", part):
            result.append(part)
            continue

        apo_m = _APOSTROPHE_PREFIX_PATTERN.match(part)
        if apo_m:
            pfx = apo_m.group(1).lower()
            rest = apo_m.group(2)
            cased_rest = rest[:1].upper() + rest[1:].lower() if rest else ""
            result.append(f"{pfx}{cased_rest}")
            word_idx += 1
            continue

        lower = part.casefold()
        if word_idx > 0 and lower in _LOWERCASE_PARTICLES:
            result.append(lower)
        else:
            result.append(lower[:1].upper() + lower[1:])
        word_idx += 1

    return "".join(result)


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


# Configuration table for matching thresholds
MATCHING_CONFIG = {
    "exact_threshold": 1.0,
    "default_confidence_threshold": 0.80,
    "ocr_fuzzy_threshold": 0.60,
}


def resolve_best_candidate(
    candidates: List[Dict[str, Any]],
    target_pos: Optional[Tuple[float, float]] = None,
    bounds: Optional[Dict[str, float]] = None,
    *,
    prefer_political: bool = True,
    prefer_population: bool = False,
    strict_bounds: bool = False,
) -> Optional[Dict[str, Any]]:
    """Select the best candidate from a candidate list.

    Unifies candidate selection across cities and geographic entities:
    - Filters by spatial bounds (strict if requested, or prefers in-bounds candidates).
    - Prioritizes political entities over physical entities when mixed (e.g. province vs lake).
    - If target_pos is provided, picks the candidate closest to target_pos.
    - If prefer_population is True (or cities without target_pos), picks highest population.
    - If bounds center is available, picks closest to bounds center.
    - Otherwise returns the first candidate in the pool.
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

    if prefer_political:
        political = [c for c in pool if c.get("type") in _POLITICAL_TYPES]
        if political and len(political) < len(pool):
            pool = political

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
    norm = _normalize(text)
    if not norm:
        return None

    hits = _GEO_INDEX.get(norm)
    if hits:
        return resolve_best_candidate(hits, target_pos=target_pos, bounds=bounds, prefer_political=True)

    if fuzzy and cutoff < MATCHING_CONFIG["exact_threshold"]:
        close = difflib.get_close_matches(norm, _GEO_INDEX.keys(), n=1, cutoff=cutoff)
        if close:
            return resolve_best_candidate(_GEO_INDEX[close[0]], target_pos=target_pos, bounds=bounds, prefer_political=True)

    return None


# City gazetteer  (geonamescache)
def _parse_pop(val: Any) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


# City gazetteer (geonamescache)
_gc = getattr(geonamescache, "GeonamesCache")()
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


# Style definitions derive from the shared, language-neutral taxonomy.
StyleTuple = Tuple[str, int, str, Any]

WORD_TAXONOMY: Dict[str, Dict[str, Any]] = {
    word_type: {
        "element_type": entry["mapElementType"],
        "size_px": entry["sizePx"],
        "font_style": (
            f"{entry['fontStyle']} uppercase"
            if entry["fontStyle"] == "italic"
            and entry["textTransform"] == "uppercase"
            else "uppercase"
            if entry["textTransform"] == "uppercase"
            else entry["fontStyle"]
        ),
        "priority": entry["priority"],
        "min_zoom": entry["minZoom"],
        "category": entry["category"],
        "transform": (
            str.upper if entry["textTransform"] == "uppercase" else capitalize_words
        ),
    }
    for word_type, entry in _WORD_STYLE_CONFIG["types"].items()
}

STYLES_MAP: Dict[str, StyleTuple] = {
    k: (v["element_type"], v["size_px"], v["font_style"], v["transform"])
    for k, v in WORD_TAXONOMY.items()
}
DEFAULT_STYLE: StyleTuple = STYLES_MAP["city"]


_GEOGRAPHIC_PREFIXES = tuple(
    (str(normalized), str(display))
    for normalized, display in _WORD_STYLE_CONFIG["geographicPrefixes"]
)


def _find_geographic_prefix(norm_text: str) -> Optional[Tuple[str, str]]:
    """Return (normalized_prefix, display_prefix) if norm_text begins with a known geographic prefix."""
    for p_norm, p_disp in _GEOGRAPHIC_PREFIXES:
        if norm_text.startswith(p_norm):
            return p_norm, p_disp
    return None


def format_geographic_nomenclature(raw_name: str, query: str = "") -> str:
    """Format place name with unified nomenclature and preserve query prefix when present.

    Preserves terms like 'Province de ...', 'Océan ...', 'Territoire de ...' only if present
    in the extraction query, avoiding nested prefix loops or casing inconsistencies.
    """
    clean_name = raw_name.strip()
    if not clean_name:
        return raw_name

    norm_query = _normalize(query)
    norm_raw = _normalize(clean_name)

    query_prefix = _find_geographic_prefix(norm_query) if query else None
    raw_prefix = _find_geographic_prefix(norm_raw)

    formatted_base = clean_name if clean_name.isupper() else capitalize_words(clean_name)

    if query_prefix and not raw_prefix:
        _, display_prefix = query_prefix
        return f"{display_prefix}{capitalize_words(clean_name)}"

    return formatted_base


def _not_found(text: str) -> Dict[str, Any]:
    """Canonical 'not found' result."""
    return {"found": False, "query": text, "name": text, "lat": 0.0, "lon": 0.0, "geonameid": None, "matched_text": None}


def format_place_result(
    place: Dict[str, Any],
    query: str,
    base: Optional[Dict[str, Any]] = None,
    default_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Format a geographic-entity or city match as a result dict using STYLES_MAP."""
    raw_name = place.get("name_fr") or place.get("name", query)
    raw_name = format_geographic_nomenclature(raw_name, query)
    geo_type = place.get("type") or default_type

    style_key = geo_type or "city"
    map_element_type, size_px, font_style, transform_func = STYLES_MAP.get(style_key, DEFAULT_STYLE)
    display = transform_func(raw_name)

    result: Dict[str, Any] = {
        **(base or {}),
        "found": True,
        "query": query,
        "geonameid": place.get("geonameid")
        or (f"{geo_type}:{place.get('name')}" if geo_type and place.get("name") else None),
        "name": display,
        "lat": place.get("lat"),
        "lon": place.get("lon"),
        "mapElementType": map_element_type,
        "sizePx": size_px,
        "fontStyle": font_style,
        "matched_text": _normalize(query),
    }

    if "population" in place and place["population"] is not None:
        result["population"] = place["population"]

    if geo_type is not None:
        result["type"] = geo_type

    return result


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
    min_similarity: float = 0.80,
) -> Optional[Dict[str, Any]]:
    """Find a candidate city within radius_km of coordinates [lon, lat].

    Strictly discriminates: requires exploitable text, non-empty normalized key,
    and difflib similarity >= min_similarity (default 0.80).
    Does NOT fall back to picking the nearest city when the score is insufficient.
    """
    if not is_exploitable_text(text):
        return None
    if not coords or len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    key = _normalize(text)
    if not key:
        return None

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

    scored = [
        (difflib.SequenceMatcher(None, key, _normalize(c.get("name", ""))).ratio(), -dist, c) for dist, c in nearby_cities
    ]
    best_sim, _, best_city = max(scored, key=lambda x: (x[0], x[1]))
    if best_sim >= min_similarity:
        return best_city

    return None


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

    def _match_geo(fuzzy: bool = False, cutoff: float = MATCHING_CONFIG["default_confidence_threshold"]) -> Any:
        ent = find_geo_entity(key, fuzzy=fuzzy, cutoff=cutoff, target_pos=target_pos, bounds=bounds)
        if ent is None:
            return None
        return (
            format_place_result(ent, text, base=base, default_type="country")
            if is_in_bounds(ent["lat"], ent["lon"], bounds)
            else _BLOCKED
        )

    def _match_city(fuzzy: bool = False, cutoff: float = MATCHING_CONFIG["default_confidence_threshold"]) -> Optional[Dict[str, Any]]:
        if not fuzzy:
            cands = _CITY_INDEX.get(key, [])
        else:
            valid_keys = [k for k, v in _CITY_INDEX.items() if any(is_in_bounds(c["lat"], c["lon"], bounds) for c in v)] if bounds else list(_CITY_INDEX.keys())
            close = difflib.get_close_matches(key, valid_keys, n=1, cutoff=cutoff)
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
            return None
        return format_place_result(best, text)

    if text.isupper():
        # ALL-CAPS → prefer geographic entity
        geo = _match_geo(fuzzy=False)
        if geo is _BLOCKED:
            return base
        if geo:
            return geo
        city = _match_city(fuzzy=False)
        if city:
            return city
    else:
        # Title / lowercase → prefer city
        city = _match_city(fuzzy=False)
        if city:
            return city
        geo = _match_geo(fuzzy=False)
        if geo is _BLOCKED:
            return base
        if geo:
            return geo

    if confidence_threshold < MATCHING_CONFIG["exact_threshold"]:
        geo_f = _match_geo(fuzzy=True, cutoff=confidence_threshold)
        if geo_f is _BLOCKED:
            return base
        if geo_f:
            return geo_f

        city_f = _match_city(fuzzy=True, cutoff=confidence_threshold)
        if city_f:
            return city_f

    return base


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
    "is_in_bounds",
    "capitalize_first",
    "capitalize_words",
    "format_geographic_nomenclature",
    "haversine_distance_km",
    "find_nearby_candidate_city",
    "is_exploitable_text",
    "format_place_result",
    "_normalize",
    "_city_map",
    "WORD_TAXONOMY",
    "STYLES_MAP",
    "DEFAULT_STYLE",
    "StyleTuple",
    "MATCHING_CONFIG",
]

_city_map = _CITY_INDEX
