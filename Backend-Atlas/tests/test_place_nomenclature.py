"""Unit tests for app.utils.place_nomenclature.

Tests:
- String normalization and cleaning.
- Capitalization (single word and multi-word with French particles/apostrophes).
- Geographic prefixes detection and nomenclature formatting.
- Style taxonomy derivation and format_place_result.
- Usable/exploitable text filtering.
"""

import json
from pathlib import Path

from app.utils.place_nomenclature import (
    DEFAULT_STYLE,
    STYLES_MAP,
    WORD_TAXONOMY,
    _WORD_STYLE_CONFIG,
    _normalize,
    capitalize_first,
    capitalize_words,
    format_geographic_nomenclature,
    format_place_result,
    is_exploitable_text,
)


def test_normalize():
    assert _normalize("Montréal") == "montreal"
    assert _normalize("  États-Unis  ") == "etats unis"
    assert _normalize("Océan Atlantique!!!") == "ocean atlantique"
    assert _normalize("") == ""


def test_capitalize_first():
    assert capitalize_first("québec") == "Québec"
    assert capitalize_first("france") == "France"
    assert capitalize_first("") == ""


def test_capitalize_words_with_particles_and_hyphens():
    assert capitalize_words("new york city") == "New York City"
    assert capitalize_words("saint-pierre") == "Saint-Pierre"
    assert capitalize_words("golfe du mexique") == "Golfe du Mexique"
    assert capitalize_words("mer du labrador") == "Mer du Labrador"
    assert capitalize_words("baie d'hudson") == "Baie d'Hudson"
    assert capitalize_words("lac de la haute-marne") == "Lac de la Haute-Marne"


def test_format_geographic_nomenclature():
    assert format_geographic_nomenclature("QUEBEC") == "QUEBEC"
    assert format_geographic_nomenclature("québec") == "Québec"
    assert format_geographic_nomenclature("hudson", query="baie d'hudson") == "Baie d'Hudson"
    assert format_geographic_nomenclature("mer du nord", query="mer du nord") == "Mer du Nord"


def test_is_exploitable_text():
    assert is_exploitable_text("Paris") is True
    assert is_exploitable_text("Saint-Malo") is True
    assert is_exploitable_text("") is False
    assert is_exploitable_text("12345") is False
    assert is_exploitable_text("!!! ?") is False
    assert is_exploitable_text("a") is False  # 1 letter noise
    assert is_exploitable_text("Échelle 1:50000") is False  # legend keyword
    assert is_exploitable_text("Légende de la carte") is False


def test_format_place_result_derives_taxonomy_styles():
    city_place = {
        "geonameid": "12345",
        "name": "Trois-Rivières",
        "lat": 46.34,
        "lon": -72.54,
        "population": 130000,
    }
    result = format_place_result(city_place, "trois-rivieres")
    assert result["found"] is True
    assert result["name"] == "Trois-Rivières"
    assert result["mapElementType"] == "point"
    assert result["sizePx"] == 12
    assert result["fontStyle"] == "normal"
    assert result["lat"] == 46.34
    assert result["lon"] == -72.54

    country_place = {
        "geonameid": "country:Canada",
        "name": "Canada",
        "name_fr": "Canada",
        "type": "country",
        "lat": 60.0,
        "lon": -95.0,
    }
    country_res = format_place_result(country_place, "CANADA", default_type="country")
    assert country_res["found"] is True
    assert country_res["name"] == "CANADA"
    assert country_res["mapElementType"] == "label"
    assert country_res["sizePx"] == 16
    assert country_res["fontStyle"] == "uppercase"
