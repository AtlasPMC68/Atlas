"""Place nomenclature, capitalization, geographic prefixes, and typography styling.

Derives casing, nomenclature formatting, and typography taxonomy from the shared
``shared/word-taxonomy.json`` configuration.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

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

        lower = part.lower()
        if word_idx > 0 and lower in _LOWERCASE_PARTICLES:
            result.append(lower)
        else:
            result.append(lower[:1].upper() + lower[1:])
        word_idx += 1

    return "".join(result)


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

GEOGRAPHIC_PREFIX_TYPES: Dict[str, Set[str]] = {
    "ocean": {"ocean"},
    "mer": {"sea"},
    "lac": {"lake"},
    "fleuve": {"river", "fleuve"},
    "riviere": {"river", "fleuve"},
    "baie": {"sea", "lake", "ocean"},
    "golfe": {"sea", "ocean"},
    "detroit": {"sea", "ocean"},
    "ile": {"province", "state", "territory", "country", "city"},
    "iles": {"province", "state", "territory", "country", "city"},
    "province": {"province", "state"},
    "territoire": {"territory", "state", "province"},
    "district": {"territory", "province", "state"},
    "etat": {"state", "province", "country"},
}


def _find_geographic_prefix(norm_text: str) -> Optional[Tuple[str, str]]:
    """Return (normalized_prefix, display_prefix) if norm_text begins with a known geographic prefix."""
    for p_norm, p_disp in _GEOGRAPHIC_PREFIXES:
        if norm_text.startswith(p_norm):
            return p_norm, p_disp
    return None


def is_geographic_prefix_only(text: str) -> bool:
    """Whether *text* is only a geographic prefix with no place name."""
    normalized = _normalize(text)
    if not normalized:
        return False
    prefix_fragments = {
        " ".join(prefix.strip().split()[:count])
        for prefix, _display in _GEOGRAPHIC_PREFIXES
        for count in range(1, len(prefix.strip().split()) + 1)
    }
    return normalized in prefix_fragments


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
    return {
        "found": False,
        "query": text,
        "name": text,
        "lat": 0.0,
        "lon": 0.0,
        "geonameid": None,
        "matched_text": None,
    }


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


__all__ = [
    "_normalize",
    "capitalize_first",
    "capitalize_words",
    "format_geographic_nomenclature",
    "is_geographic_prefix_only",
    "is_exploitable_text",
    "_find_geographic_prefix",
    "format_place_result",
    "_not_found",
    "WORD_TAXONOMY",
    "STYLES_MAP",
    "DEFAULT_STYLE",
    "StyleTuple",
    "GEOGRAPHIC_PREFIX_TYPES",
    "_WORD_STYLE_CONFIG",
]
