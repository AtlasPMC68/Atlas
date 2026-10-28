#!/usr/bin/env python
"""Generate an offline, lightweight JSON dataset of geographic entities with GPS coordinates.

Output:
    Backend-Atlas/app/data/geographic_entities.json
"""

import gettext
import json
import math
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

import geonamescache
import pycountry
from countryinfo import CountryInfo

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
OUTPUT_FILE = DATA_DIR / "geographic_entities.json"

# Natural Earth Vector GeoJSON repository base URL
NE_BASE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"

# aourednik/historical-basemaps GeoJSON repository base URL
HISTORICAL_BASEMAPS_BASE_URL = "https://raw.githubusercontent.com/aourednik/historical-basemaps/master/geojson/"

# Canadian Territorial Evolution GeoJSON (https://app.geo.ca/fr-ca/map-browser/record/e88ce995-b69a-4595-a752-bb06b061b5a3)
CANADIAN_EVOLUTION_FILE = (
    BASE_DIR / "tests" / "assets" / "georef" / "georef_zones" / "table-Évolution-territoriale-du-Canada,-1867-à-2003.json"
)


# DATA SOURCE: FALLBACK_COORDINATES (Curated reference table)
# Provides: GPS coordinates [lat, lon] for micro-states, disputed territories, and island
# entities not indexed by the countryinfo library.

FALLBACK_COORDINATES = {
    "AQ": [-82.86, 135.00],  # Antarctica
    "AX": [60.18, 19.92],  # Aland Islands
    "BL": [17.90, -62.83],  # Saint Barthelemy
    "BQ": [12.18, -68.24],  # Bonaire, Sint Eustatius and Saba
    "BV": [-54.42, 3.36],  # Bouvet Island
    "CW": [12.17, -68.99],  # Curacao
    "XK": [42.60, 20.90],  # Kosovo
    "MF": [18.07, -63.05],  # Saint Martin
    "SX": [18.04, -63.06],  # Sint Maarten
    "TC": [21.75, -71.58],  # Turks and Caicos Islands
    "UM": [19.28, 166.65],  # United States Minor Outlying Islands
    "VG": [18.42, -64.64],  # British Virgin Islands
    "VI": [18.34, -64.93],  # U.S. Virgin Islands
}


# DATA SOURCE: CONTINENTS (Curated reference table)
# Provides: ISO 2-letter codes, English names, French names, and central [lat, lon]
# coordinates for the 7 standard continents.
CONTINENTS = {
    "AF": {"name": "Africa", "name_fr": "Afrique", "lat": 1.65, "lon": 17.30},
    "AN": {"name": "Antarctica", "name_fr": "Antarctique", "lat": -82.86, "lon": 135.00},
    "AS": {"name": "Asia", "name_fr": "Asie", "lat": 34.05, "lon": 100.62},
    "EU": {"name": "Europe", "name_fr": "Europe", "lat": 54.53, "lon": 15.26},
    "NA": {"name": "North America", "name_fr": "Amérique du Nord", "lat": 54.53, "lon": -105.26},
    "OC": {"name": "Oceania", "name_fr": "Océanie", "lat": -22.74, "lon": 140.02},
    "SA": {"name": "South America", "name_fr": "Amérique du Sud", "lat": -8.78, "lon": -55.49},
}

# ftm: off
# DATA SOURCE: MAJOR_FLEUVES (Curated hydrological reference set)
# Provides: Names of major world rivers that reach oceans/seas directly ("fleuve" in French),
# distinguishing them from inland tributary streams ("rivière").
MAJOR_FLEUVES = {
    "saint-laurent",
    "saint laurent",
    "saint lawrence",
    "st. lawrence",
    "st lawrence",
    "mississippi",
    "amazon",
    "amazone",
    "amazonas",
    "nile",
    "nil",
    "congo",
    "yangtze",
    "yangzi",
    "chang jiang",
    "fleuve bleu",
    "yellow river",
    "fleuve jaune",
    "huang he",
    "rhine",
    "rhin",
    "danube",
    "seine",
    "loire",
    "rhone",
    "garonne",
    "volga",
    "don",
    "dnieper",
    "dniepr",
    "elbe",
    "oder",
    "vistula",
    "vistule",
    "thames",
    "tamise",
    "tagus",
    "tage",
    "ebro",
    "ebre",
    "douro",
    "colorado",
    "columbia",
    "yukon",
    "mackenzie",
    "rio grande",
    "rio bravo",
    "parana",
    "orinoco",
    "orenoque",
    "ganges",
    "gange",
    "indus",
    "brahmaputra",
    "brahmapoutre",
    "mekong",
    "amur",
    "amour",
    "lena",
    "ob",
    "yenisey",
    "ienissei",
    "murray",
    "niger",
    "zambezi",
    "zambeze",
    "senegal",
    "orange",
}


# ========================================================================================
# DATA SOURCE: aourednik/historical-basemaps (GeoJSON World Historical Snapshots)
# Source: https://github.com/aourednik/historical-basemaps
# Provides dynamic polygon geometries to compute centroids [lat, lon] for:
# - New France (world_1700.geojson)
# - Louisiana (world_1715.geojson)
# - British American colonies / Thirteen Colonies (world_1715.geojson)
# - Province of Quebec 1763–1791 (world_1783.geojson)
# - Colonial empires: New Spain, Peru, Brazil, Holy Roman Empire, Ottoman, Mughal
# ========================================================================================
HISTORICAL_BASEMAP_TARGETS = [
    {
        "file": "world_1700.geojson",
        "match_name": "New France",
        "type": "territory",
        "name": "New France",
        "name_fr": "Nouvelle-France",
        "start_year": 1534,
        "end_year": 1763,
        "aliases": ["new france", "nouvelle france"],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "Louisiana",
        "type": "territory",
        "name": "Louisiana",
        "name_fr": "Louisiane",
        "start_year": 1682,
        "end_year": 1803,
        "aliases": [
            "louisiane",
            "louisiana",
            "la louisiane",
            "louisiane francaise",
            "territoire de la louisiane",
            "territoire de louisiane",
            "louisiana territory",
        ],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "British American colonies",
        "type": "territory",
        "name": "Thirteen Colonies",
        "name_fr": "Treize Colonies",
        "start_year": 1607,
        "end_year": 1776,
        "aliases": [
            "thirteen colonies",
            "treize colonies",
            "treize colonies britanniques",
            "british american colonies",
        ],
    },
    {
        "file": "world_1783.geojson",
        "match_name": "Quebec",
        "type": "province",
        "name": "Québec",
        "name_fr": "Québec",
        "start_year": 1763,
        "end_year": 1791,
        "aliases": [
            "province of quebec",
            "province de quebec",
            "quebec",
        ],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "Viceroyalty of New Spain",
        "type": "territory",
        "name": "Viceroyalty of New Spain",
        "name_fr": "Nouvelle-Espagne",
        "start_year": 1521,
        "end_year": 1821,
        "aliases": [
            "nouvelle espagne",
            "vice royaute de nouvelle espagne",
            "new spain",
            "viceroyalty of new spain",
        ],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "Viceroyalty of Peru",
        "type": "territory",
        "name": "Viceroyalty of Peru",
        "name_fr": "Vice-royauté du Pérou",
        "start_year": 1542,
        "end_year": 1824,
        "aliases": [
            "vice royaute du perou",
            "perou colonial",
            "viceroyalty of peru",
        ],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "Viceroyalty of Brazil",
        "type": "territory",
        "name": "Viceroyalty of Brazil",
        "name_fr": "Vice-royauté du Brésil",
        "start_year": 1500,
        "end_year": 1815,
        "aliases": [
            "bresil colonial",
            "vice royaute du bresil",
            "viceroyalty of brazil",
        ],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "Holy Roman Empire",
        "type": "territory",
        "name": "Holy Roman Empire",
        "name_fr": "Saint-Empire romain germanique",
        "start_year": 962,
        "end_year": 1806,
        "aliases": [
            "saint empire romain germanique",
            "saint empire",
            "holy roman empire",
        ],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "Ottoman Empire",
        "type": "territory",
        "name": "Ottoman Empire",
        "name_fr": "Empire ottoman",
        "start_year": 1299,
        "end_year": 1922,
        "aliases": [
            "empire ottoman",
            "ottoman empire",
        ],
    },
    {
        "file": "world_1715.geojson",
        "match_name": "Mughal Empire",
        "type": "territory",
        "name": "Mughal Empire",
        "name_fr": "Empire moghol",
        "start_year": 1526,
        "end_year": 1857,
        "aliases": [
            "empire moghol",
            "mughal empire",
        ],
    },
]

# ========================================================================================
# DATA SOURCE: CANADIAN TERRITORIAL EVOLUTION (1867–2003) PROVINCE & TERRITORY METADATA
# Source / Reference: Ressources naturelles Canada (RNCan)
# Mapping of all 28 distinct NOM_PROV entities with standard English and French names,
# administrative types, and OCR search aliases.
# Centroids [lat, lon] and time validity intervals [start_year, end_year] are computed
# dynamically from each historical milestone feature in table-Évolution-territoriale-du-Canada,-1867-à-2003.json.
# ========================================================================================
CANADIAN_PROVINCE_METADATA = {
    "Alberta": {
        "name_en": "Alberta",
        "name_fr": "Alberta",
        "type": "province",
        "ref_lat": 53.9333,
        "ref_lon": -116.5765,
        "aliases": ["alberta", "province de l alberta", "province d alberta", "ab"],
    },
    "Colombie-Britannique": {
        "name_en": "British Columbia",
        "name_fr": "Colombie-Britannique",
        "type": "province",
        "ref_lat": 53.7267,
        "ref_lon": -127.6476,
        "aliases": ["colombie britannique", "british columbia", "province de la colombie britannique", "bc", "c b"],
    },
    "District d'Alberta": {
        "name_en": "Alberta District",
        "name_fr": "Territoire d'Alberta",
        "type": "territory",
        "ref_lat": 52.6640,
        "ref_lon": -114.7347,
        "aliases": [
            "territoire d alberta",
            "territoire dalberta",
            "territoire alberta",
            "alberta territory",
            "district d alberta",
            "district dalberta",
            "alberta district",
        ],
    },
    "District d'Assiniboine": {
        "name_en": "Assiniboine District",
        "name_fr": "Territoire d'Assiniboine",
        "type": "territory",
        "ref_lat": 50.4757,
        "ref_lon": -106.4049,
        "aliases": [
            "territoire d assiniboine",
            "territoire d assiniboia",
            "territoire assiniboine",
            "territoire assiniboia",
            "district d assiniboine",
            "district d assiniboia",
            "assiniboia",
            "assiniboine",
            "assiniboine district",
            "assiniboia district",
        ],
    },
    "District d'Athabaska": {
        "name_en": "Athabaska District",
        "name_fr": "Territoire d'Athabaska",
        "type": "territory",
        "ref_lat": 57.5539,
        "ref_lon": -115.7275,
        "aliases": [
            "territoire d athabaska",
            "territoire d athabasca",
            "territoire athabaska",
            "territoire athabasca",
            "district d athabaska",
            "district d athabasca",
            "athabaska",
            "athabasca",
            "athabaska district",
        ],
    },
    "District d'Ungava": {
        "name_en": "Ungava District",
        "name_fr": "Territoire d'Ungava",
        "type": "territory",
        "ref_lat": 56.5,
        "ref_lon": -71.5,
        "aliases": [
            "territoire d ungava",
            "territoire dungava",
            "territoire ungava",
            "district d ungava",
            "district dungava",
            "ungava",
            "ungava district",
        ],
    },
    "District de Franklin": {
        "name_en": "Franklin District",
        "name_fr": "Territoire de Franklin",
        "type": "territory",
        "ref_lat": 73.0,
        "ref_lon": -90.0,
        "aliases": [
            "territoire de franklin",
            "territoire franklin",
            "district de franklin",
            "franklin",
            "franklin district",
        ],
    },
    "District de Keewatin": {
        "name_en": "Keewatin District",
        "name_fr": "Territoire de Keewatin",
        "type": "territory",
        "ref_lat": 61.5,
        "ref_lon": -96.0,
        "aliases": [
            "territoire de keewatin",
            "territoire keewatin",
            "district de keewatin",
            "keewatin",
            "keewatin district",
        ],
    },
    "District de Mackenzie": {
        "name_en": "Mackenzie District",
        "name_fr": "Territoire de Mackenzie",
        "type": "territory",
        "ref_lat": 64.0,
        "ref_lon": -120.0,
        "aliases": [
            "territoire de mackenzie",
            "territoire mackenzie",
            "district de mackenzie",
            "mackenzie",
            "mackenzie district",
        ],
    },
    "District de Saskatchewan": {
        "name_en": "Saskatchewan District",
        "name_fr": "Territoire de Saskatchewan",
        "type": "territory",
        "ref_lat": 53.0,
        "ref_lon": -106.0,
        "aliases": [
            "territoire de saskatchewan",
            "territoire saskatchewan",
            "district de saskatchewan",
            "saskatchewan district",
        ],
    },
    "District du Yukon": {
        "name_en": "Yukon District",
        "name_fr": "Territoire du Yukon",
        "type": "territory",
        "ref_lat": 64.0,
        "ref_lon": -135.0,
        "aliases": [
            "territoire du yukon",
            "territoire yukon",
            "district du yukon",
            "yukon district",
        ],
    },
    "Manitoba": {
        "name_en": "Manitoba",
        "name_fr": "Manitoba",
        "type": "province",
        "ref_lat": 53.7609,
        "ref_lon": -98.8139,
        "aliases": ["manitoba", "province du manitoba", "mb"],
    },
    "North-Western Territory": {
        "name_en": "North-Western Territory",
        "name_fr": "Territoire du Nord-Ouest",
        "type": "territory",
        "ref_lat": 60.0,
        "ref_lon": -115.0,
        "aliases": ["north western territory", "northwestern territory", "territoire du nord ouest"],
    },
    "Nouveau-Brunswick": {
        "name_en": "New Brunswick",
        "name_fr": "Nouveau-Brunswick",
        "type": "province",
        "ref_lat": 46.5653,
        "ref_lon": -66.4619,
        "aliases": ["nouveau brunswick", "new brunswick", "province du nouveau brunswick", "nb"],
    },
    "Nouvelle-Écosse": {
        "name_en": "Nova Scotia",
        "name_fr": "Nouvelle-Écosse",
        "type": "province",
        "ref_lat": 45.2707,
        "ref_lon": -62.7196,
        "aliases": ["nouvelle ecosse", "nova scotia", "province de la nouvelle ecosse", "ns"],
    },
    "Nunavut": {
        "name_en": "Nunavut",
        "name_fr": "Nunavut",
        "type": "territory",
        "ref_lat": 70.2998,
        "ref_lon": -83.1076,
        "aliases": ["nunavut", "territoire du nunavut", "nu"],
    },
    "Ontario": {
        "name_en": "Ontario",
        "name_fr": "Ontario",
        "type": "province",
        "ref_lat": 51.2538,
        "ref_lon": -85.3232,
        "aliases": ["ontario", "province de l ontario", "province d ontario", "on"],
    },
    "Québec": {
        "name_en": "Québec",
        "name_fr": "Québec",
        "type": "province",
        "ref_lat": 52.9399,
        "ref_lon": -73.5491,
        "aliases": ["quebec", "province de quebec", "province du quebec", "qc"],
    },
    "Saskatchewan": {
        "name_en": "Saskatchewan",
        "name_fr": "Saskatchewan",
        "type": "province",
        "ref_lat": 52.9399,
        "ref_lon": -106.4509,
        "aliases": ["saskatchewan", "province de la saskatchewan", "sk"],
    },
    "Terre de Rupert": {
        "name_en": "Rupert's Land",
        "name_fr": "Terre de Rupert",
        "type": "territory",
        "ref_lat": 55.0,
        "ref_lon": -85.0,
        "aliases": ["terre de rupert", "rupert s land", "ruperts land"],
    },
    "Terre-Neuve": {
        "name_en": "Newfoundland",
        "name_fr": "Terre-Neuve",
        "type": "province",
        "ref_lat": 48.9,
        "ref_lon": -55.8,
        "aliases": ["terre neuve", "newfoundland", "province de terre neuve", "nl"],
    },
    "Terre-Neuve-et-Labrador": {
        "name_en": "Newfoundland and Labrador",
        "name_fr": "Terre-Neuve-et-Labrador",
        "type": "province",
        "ref_lat": 53.1355,
        "ref_lon": -57.6604,
        "aliases": ["terre neuve et labrador", "newfoundland and labrador", "nl"],
    },
    "Territoire du Yukon": {
        "name_en": "Yukon Territory",
        "name_fr": "Territoire du Yukon",
        "type": "territory",
        "ref_lat": 64.2823,
        "ref_lon": -135.0,
        "aliases": ["territoire du yukon", "yukon territory", "yukon", "yt"],
    },
    "Territoires Nord-Ouest": {
        "name_en": "Northwest Territories",
        "name_fr": "Territoires du Nord-Ouest",
        "type": "territory",
        "ref_lat": 64.8255,
        "ref_lon": -124.8457,
        "aliases": ["territoires du nord ouest", "territoires nord ouest", "northwest territories", "nwt", "nt"],
    },
    "Zone disputée": {
        "name_en": "Disputed Zone",
        "name_fr": "Zone disputée",
        "type": "territory",
        "ref_lat": 49.5,
        "ref_lon": -94.5,
        "aliases": ["zone disputee", "zone disputee ontario manitoba", "disputed zone"],
    },
    "Île-du-Prince-Édouard": {
        "name_en": "Prince Edward Island",
        "name_fr": "Île-du-Prince-Édouard",
        "type": "province",
        "ref_lat": 46.5107,
        "ref_lon": -63.4168,
        "aliases": ["ile du prince edouard", "prince edward island", "pei", "ipe"],
    },
    "Îles de l'Arctique": {
        "name_en": "Arctic Islands",
        "name_fr": "Îles de l'Arctique",
        "type": "territory",
        "ref_lat": 75.0,
        "ref_lon": -95.0,
        "aliases": ["iles de l arctique", "arctic islands"],
    },
}


def normalize_key(s: str) -> str:
    """Strip accents, punctuation, and extra whitespace to generate matching keys."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def clean_french_name(name_fr: str) -> list[str]:
    """Given an inverted name from pycountry/gettext (e.g. 'Russie, Fédération de'),
    return direct natural variants: ['Russie', 'Fédération de Russie']."""
    variants = [name_fr]
    if "," in name_fr:
        parts = [p.strip() for p in name_fr.split(",", 1)]
        variants.append(parts[0])
        variants.append(f"{parts[1]} {parts[0]}")
    return variants


def capitalize_first(s: str) -> str:
    """Capitalize the first character of a string while preserving the rest."""
    if not s:
        return s
    return s[0].upper() + s[1:]


def ring_area(ring: list) -> float:
    """Calculate the absolute planar area of a 2D ring in square degrees (Shoelace formula)."""
    if len(ring) < 3:
        return 0.0
    a = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) * 0.5


def ring_centroid(ring: list) -> tuple[float, float]:
    """Calculate the true geometric centroid (lat, lon) of a 2D polygon ring."""
    n = len(ring)
    if n < 3:
        return (round(float(ring[0][1]), 4), round(float(ring[0][0]), 4)) if ring else (0.0, 0.0)
    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-7:
        avg_lon = sum(p[0] for p in ring) / n
        avg_lat = sum(p[1] for p in ring) / n
        return (round(float(avg_lat), 4), round(float(avg_lon), 4))
    cx /= 6.0 * a
    cy /= 6.0 * a
    return (round(float(cy), 4), round(float(cx), 4))


def sanitize_district_to_territoire(name: str) -> str:
    """Convert any mention of 'district' in French names to 'territoire'."""
    if not name:
        return name
    replacements = [
        (r"\bDistrict d'", "Territoire d'"),
        (r"\bDistrict du\b", "Territoire du"),
        (r"\bDistrict de la\b", "Territoire de la"),
        (r"\bDistrict des\b", "Territoire des"),
        (r"\bDistrict de\b", "Territoire de"),
        (r"\bDistrict\b", "Territoire"),
        (r"\bdistrict d'", "territoire d'"),
        (r"\bdistrict du\b", "territoire du"),
        (r"\bdistrict de la\b", "territoire de la"),
        (r"\bdistrict des\b", "territoire des"),
        (r"\bdistrict de\b", "territoire de"),
        (r"\bdistrict\b", "territoire"),
    ]
    res = name
    for pat, rep in replacements:
        res = re.sub(pat, rep, res)
    return res


def deduplicate_by_name_and_location(entities: list[dict]) -> list[dict]:
    """Deduplicate elements having the same normalized name and the same geographic location.

    Merges aliases into a unified set and consolidates validity years.
    """
    dedup_map: dict[tuple, dict] = {}
    for e in entities:
        name_key = normalize_key(e.get("name_fr") or e.get("name") or "")
        lat = e.get("lat")
        lon = e.get("lon")
        lat_r = round(float(lat), 4) if lat is not None else None
        lon_r = round(float(lon), 4) if lon is not None else None
        loc_key = (name_key, lat_r, lon_r)

        if loc_key not in dedup_map:
            dedup_map[loc_key] = dict(e)
            dedup_map[loc_key]["aliases"] = set(e.get("aliases", []))
        else:
            existing = dedup_map[loc_key]
            existing["aliases"].update(e.get("aliases", []))
            e_sy, e_ey = e.get("start_year"), e.get("end_year")
            ex_sy, ex_ey = existing.get("start_year"), existing.get("end_year")

            if ex_sy is None or e_sy is None:
                existing["start_year"] = None
                existing["end_year"] = None
            else:
                existing["start_year"] = min(ex_sy, e_sy)
                existing["end_year"] = max(ex_ey, e_ey)

    result = []
    for e in dedup_map.values():
        e["aliases"] = sorted(e["aliases"])
        result.append(e)
    return result


def merge_with_existing(new_entities: list[dict], output_file: Path) -> list[dict]:
    """Merge newly generated entities into the existing JSON dataset.

    Enforces:
    1. Deduplication: removes elements having the same name and the same location.
    2. Name standardization: ensures no name_fr contains 'district', but 'territoire'.
    3. Alias preservation: aliases from merged duplicates are unioned.
    """
    if not output_file.exists():
        cleaned = []
        for e in new_entities:
            if "name_fr" in e and e["name_fr"]:
                e["name_fr"] = sanitize_district_to_territoire(e["name_fr"])
            cleaned.append(e)
        return deduplicate_by_name_and_location(cleaned)

    try:
        with open(output_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    except Exception as e:
        print(f"Warning: could not read existing {output_file.name} for merge: {e}")
        existing_data = []

    def _entity_key(e: dict) -> tuple:
        raw_name = e.get("name_fr") or e.get("name") or ""
        norm_name = normalize_key(raw_name)
        etype = e.get("type", "")
        start_year = e.get("start_year")
        end_year = e.get("end_year")

        if start_year is not None or end_year is not None:
            return (norm_name, etype, start_year, end_year)

        lat = e.get("lat")
        lon = e.get("lon")
        lat_rounded = round(float(lat), 3) if lat is not None else None
        lon_rounded = round(float(lon), 3) if lon is not None else None
        return (norm_name, etype, lat_rounded, lon_rounded)

    merged: dict[tuple, dict] = {}

    # 1. Load existing data first
    for entity in existing_data:
        key = _entity_key(entity)
        merged[key] = entity

    # 2. Merge newly generated entities
    for entity in new_entities:
        key = _entity_key(entity)
        if key in merged:
            merged[key].update(entity)
        else:
            merged[key] = entity

    # 3. Sanitize all name_fr: no 'district' allowed, must be 'territoire'
    for entity in merged.values():
        if "name_fr" in entity and entity["name_fr"]:
            orig = entity["name_fr"]
            clean = sanitize_district_to_territoire(orig)
            if clean != orig:
                entity["name_fr"] = clean
                aliases = set(entity.get("aliases", []))
                norm_orig = normalize_key(orig)
                norm_clean = normalize_key(clean)
                if norm_orig:
                    aliases.add(norm_orig)
                if norm_clean:
                    aliases.add(norm_clean)
                entity["aliases"] = sorted(aliases)
                if entity.get("type") in ("province", "territory", "district"):
                    entity["type"] = "territory"

    # 4. Remove elements having the same name and the same location
    return deduplicate_by_name_and_location(list(merged.values()))


def compute_polygon_centroid(geom: dict) -> tuple[float | None, float | None]:
    """Calculate the geometric centroid of Polygon or MultiPolygon coordinates
    extracted from GeoJSON features, prioritizing the largest polygon ring by area."""
    rings = []
    gtype = geom.get("type")
    raw_coords = geom.get("coordinates", [])

    if gtype == "Polygon" and raw_coords:
        rings.append(raw_coords[0])
    elif gtype == "MultiPolygon" and raw_coords:
        for poly in raw_coords:
            if poly:
                rings.append(poly[0])

    if not rings:
        return None, None

    largest_ring = max(rings, key=ring_area)
    lat, lon = ring_centroid(largest_ring)
    return lat, lon


def fetch_geojson(filename: str) -> dict | None:
    """Fetch GeoJSON file from the Natural Earth Vector GitHub repository."""
    url = NE_BASE_URL + filename
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Warning: could not download {filename}: {e}")
        return None


def fetch_historical_basemap(filename: str) -> dict | None:
    """Fetch GeoJSON file from the aourednik/historical-basemaps GitHub repository."""
    url = HISTORICAL_BASEMAPS_BASE_URL + filename
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Warning: could not download {filename} from historical-basemaps: {e}")
        return None


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # STEP 1: INITIALIZE FRENCH LOCALIZATION
    # Library: `pycountry` + standard library `gettext`
    # Information: Loads the ISO 3166-1 French message catalog from pycountry's locale dir.
    try:
        trans_fr = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["fr"])
    except Exception as e:
        print(f"Warning: could not load French locale for pycountry: {e}")
        trans_fr = None

    # STEP 2: LOAD CONTINENTS
    # Source: Curated `CONTINENTS` table
    # Information: English & French continent names, 2-letter codes, and centroid [lat, lon].
    dataset = []

    print("Processing continents...")
    for code, cont in CONTINENTS.items():
        aliases = {
            normalize_key(cont["name"]),
            normalize_key(cont["name_fr"]),
        }
        dataset.append(
            {
                "type": "continent",
                "code": code,
                "name": cont["name"],
                "name_fr": cont["name_fr"],
                "lat": cont["lat"],
                "lon": cont["lon"],
                "aliases": sorted(aliases),
            }
        )

    # STEP 3: LOAD SOVEREIGN COUNTRIES & TERRITORIES
    # Libraries / Sources:
    # 1. `geonamescache`:
    #    - `gc.get_countries()` provides:
    #      * Country English Name (`name`)
    #      * ISO 3166-1 Alpha-2 code (`iso`)
    #      * ISO 3166-1 Alpha-3 code (`iso3`)
    #      * Capital City (`capital`)
    #      * Estimated Population (`population`)
    # 2. `pycountry` + `gettext`:
    #    - `pycountry.countries.get(alpha_2=iso)` translated via 'iso3166-1' catalog provides:
    #      * French Localized Country Name (`name_fr`)
    #      * French Common Name variants (`common_name`)
    # 3. `countryinfo`:
    #    - `CountryInfo(query)` provides:
    #      * Centroid GPS coordinates `[lat, lon]` via `.latlng()`
    #      * Alternate international names and spellings via `.alt_spellings()`
    # 4. `FALLBACK_COORDINATES`:
    #    - Provides manual GPS coordinates for micro-states and overseas territories
    #      missing from `countryinfo` (e.g. Antarctica, Kosovo, Turks and Caicos, etc.)
    gc = geonamescache.GeonamesCache()
    gc_countries = gc.get_countries()

    print(f"Processing {len(gc_countries)} countries...")
    for iso, info in gc_countries.items():
        name_en = info.get("name") or ""
        iso3 = info.get("iso3") or ""
        capital = info.get("capital") or ""
        population = int(info.get("population") or 0)

        # French translation from pycountry gettext catalog
        name_fr = name_en
        french_variants = []
        if trans_fr:
            py_country = pycountry.countries.get(alpha_2=iso)
            if py_country:
                raw_fr = trans_fr.gettext(py_country.name)
                french_variants = clean_french_name(raw_fr)
                name_fr = french_variants[0]
                if hasattr(py_country, "common_name"):
                    raw_common_fr = trans_fr.gettext(py_country.common_name)
                    french_variants.extend(clean_french_name(raw_common_fr))

        # Lat / Lon resolution from countryinfo (with fallback table)
        lat, lon = None, None
        alt_spellings = []
        for query in [name_en, iso, iso3]:
            if not query:
                continue
            try:
                ci = CountryInfo(query)
                coords = ci.latlng()
                if coords and len(coords) == 2:
                    lat, lon = round(float(coords[0]), 4), round(float(coords[1]), 4)
                    alt_spellings = ci.alt_spellings()
                    break
            except Exception:
                pass

        if lat is None and iso in FALLBACK_COORDINATES:
            fb = FALLBACK_COORDINATES[iso]
            lat, lon = fb[0], fb[1]

        aliases = set()
        for candidate in [name_en, name_fr, iso, iso3] + french_variants + alt_spellings:
            if candidate:
                norm = normalize_key(candidate)
                if norm:
                    aliases.add(norm)

        dataset.append(
            {
                "type": "country",
                "iso": iso,
                "iso3": iso3,
                "name": name_en,
                "name_fr": name_fr,
                "capital": capital,
                "population": population,
                "lat": lat,
                "lon": lon,
                "aliases": sorted(aliases),
            }
        )

    # STEP 4: LOAD OCEANS & MAJOR SEAS
    # Source: Natural Earth Vector GeoJSON (`ne_50m_geography_marine_polys.geojson`)
    # Information extracted:
    # - `name` (English marine name, e.g. "North Atlantic Ocean", "Mediterranean Sea")
    # - `name_fr` (French marine name, e.g. "Océan Atlantique Nord", "Mer Méditerranée")
    # - `featureclass` / `featurecla` (Categorizes entity into "ocean" vs "sea")
    # - `namealt`, `label` (Alternative names for alias search index)
    # - Polygon / MultiPolygon coordinates -> centroid `[lat, lon]` computed via
    #   `compute_polygon_centroid`
    print("Fetching oceans and major seas from Natural Earth...")
    marine_data = fetch_geojson("ne_50m_geography_marine_polys.geojson")
    if marine_data:
        marine_feats = marine_data.get("features", [])
        print(f"Processing {len(marine_feats)} oceans and seas...")
        for feat in marine_feats:
            p = feat.get("properties", {})
            geom = feat.get("geometry", {})
            name_en = p.get("name") or ""
            if not name_en:
                continue

            name_fr = p.get("name_fr") or name_en
            feature_class = (p.get("featureclass") or p.get("featurecla") or "sea").lower()
            entity_type = "ocean" if "ocean" in feature_class else "sea"

            lat, lon = compute_polygon_centroid(geom)
            if lat is None or lon is None:
                continue

            aliases = set()
            for cand in [name_en, name_fr, p.get("namealt"), p.get("label")]:
                if cand:
                    norm = normalize_key(str(cand))
                    if norm:
                        aliases.add(norm)

            dataset.append(
                {
                    "type": entity_type,
                    "name": name_en.title() if name_en.isupper() else name_en,
                    "name_fr": name_fr.title() if name_fr.isupper() else name_fr,
                    "lat": lat,
                    "lon": lon,
                    "aliases": sorted(aliases),
                }
            )

    # STEP 5: LOAD MAJOR LAKES
    # Source: Natural Earth Vector GeoJSON (`ne_50m_lakes.geojson`)
    # Information extracted:
    # - `name` (English lake name, e.g. "Lake Superior", "Lake Victoria")
    # - `name_fr` (French lake name, e.g. "Lac Supérieur", "Lac Victoria")
    # - `name_alt`, `label` (Alternative spellings and historical names)
    # - Polygon / MultiPolygon coordinates -> centroid `[lat, lon]` computed via
    #   `compute_polygon_centroid`
    # - Prefix normalization: generates search variants with and without "Lac" / "Lake"
    print("Fetching major lakes from Natural Earth...")
    lakes_data = fetch_geojson("ne_50m_lakes.geojson")
    if lakes_data:
        lake_feats = lakes_data.get("features", [])
        print(f"Processing {len(lake_feats)} lakes...")
        for feat in lake_feats:
            p = feat.get("properties", {})
            geom = feat.get("geometry", {})
            name_en = p.get("name") or ""
            if not name_en:
                continue

            name_fr = p.get("name_fr") or name_en
            lat, lon = compute_polygon_centroid(geom)
            if lat is None or lon is None:
                continue

            clean_lake_fr = re.sub(r"^(lac|lake)\s+", "", name_fr, flags=re.IGNORECASE).strip()
            clean_lake_en = re.sub(r"^(lake\s+|\s+lake$)", "", name_en, flags=re.IGNORECASE).strip()
            formatted_lake_fr = name_fr if name_fr.lower().startswith("mer ") else f"Lac {clean_lake_fr}"

            aliases = set()
            for cand in [name_en, name_fr, clean_lake_fr, clean_lake_en, p.get("name_alt"), p.get("label")]:
                if not cand:
                    continue
                norm = normalize_key(str(cand))
                if not norm:
                    continue
                base = re.sub(r"^(lac|lake)\s+", "", norm).strip()
                base = re.sub(r"\s+lake$", "", base).strip()
                if base:
                    aliases.add(base)
                    aliases.add(f"lac {base}")
                    aliases.add(f"lake {base}")
                    aliases.add(f"{base} lake")
                aliases.add(norm)

            dataset.append(
                {
                    "type": "lake",
                    "name": name_en,
                    "name_fr": formatted_lake_fr,
                    "lat": lat,
                    "lon": lon,
                    "aliases": sorted(aliases),
                }
            )

    # STEP 6: LOAD STATES & PROVINCES (Admin-1 Level)
    # Source: Natural Earth Vector GeoJSON (`ne_50m_admin_1_states_provinces.geojson`)
    # Information extracted:
    # - `name` (English name of state/province, e.g. "Quebec", "California")
    # - `name_fr` (French name of state/province, e.g. "Québec", "Californie")
    # - `adm0_a3` (Parent country ISO-3 code, e.g. "CAN", "USA", "MEX")
    # - `type_en` (Administrative division type: "State" -> type "state", else "province")
    # - `postal` (Official postal abbreviation code, e.g. "QC", "ON", "CA", "NY")
    # - Polygon coordinates -> centroid `[lat, lon]` computed via `compute_polygon_centroid`
    # - Synthetic aliases: auto-generates "province de <name>" and "etat de <name>"
    print("Fetching states and provinces from Natural Earth...")
    admin1_data = fetch_geojson("ne_50m_admin_1_states_provinces.geojson")
    if admin1_data:
        admin1_feats = admin1_data.get("features", [])
        print(f"Processing {len(admin1_feats)} states and provinces...")
        for feat in admin1_feats:
            p = feat.get("properties", {})
            geom = feat.get("geometry", {})
            name_en = p.get("name") or ""
            if not name_en:
                continue

            name_fr = p.get("name_fr") or name_en
            adm0 = p.get("adm0_a3") or ""
            type_en = (p.get("type_en") or "Province").lower()
            entity_type = "state" if "state" in type_en else "province"

            lat, lon = compute_polygon_centroid(geom)
            if lat is None or lon is None:
                continue

            aliases = set()
            for cand in [name_en, name_fr, p.get("name_alt"), p.get("label"), p.get("postal")]:
                if cand:
                    norm = normalize_key(str(cand))
                    if norm:
                        aliases.add(norm)
                        if not norm.startswith("province de "):
                            aliases.add(f"province de {norm}")
                        if not norm.startswith("etat de "):
                            aliases.add(f"etat de {norm}")

            dataset.append(
                {
                    "type": entity_type,
                    "country_code": adm0,
                    "name": name_en,
                    "name_fr": name_fr,
                    "lat": lat,
                    "lon": lon,
                    "aliases": sorted(aliases),
                }
            )

    # STEP 7: LOAD MAJOR RIVERS & FLEUVES
    # Sources:
    # 1. Natural Earth Vector GeoJSON (`ne_50m_rivers_lake_centerlines_scale_rank.geojson`):
    #    - `name` / `name_en` (English river name, e.g. "Saint Lawrence", "Mississippi")
    #    - `name_fr` (French river name, e.g. "Saint-Laurent", "Mississippi")
    #    - `name_alt`, `label` (Alternative river spellings)
    #    - LineString / MultiLineString coordinates -> aggregated flow midpoints `[lat, lon]`
    # 2. `MAJOR_FLEUVES` reference set:
    #    - Cross-references river names to distinguish sea/ocean-reaching rivers (`fleuve`)
    #      from inland tributary streams (`river`). Automatically prefixes French names
    #      with "Fleuve " or "Rivière ".
    print("Fetching major rivers from Natural Earth...")
    rivers_data = fetch_geojson("ne_50m_rivers_lake_centerlines_scale_rank.geojson")
    if rivers_data:
        river_feats = rivers_data.get("features", [])
        print(f"Processing {len(river_feats)} river segments...")
        grouped_rivers: dict[str, dict] = {}
        for feat in river_feats:
            p = feat.get("properties", {})
            geom = feat.get("geometry", {})
            name_en = p.get("name") or p.get("name_en") or ""
            if not name_en:
                continue

            name_fr = p.get("name_fr") or name_en
            key = normalize_key(name_en)
            if not key:
                continue

            gtype = geom.get("type")
            raw_coords = geom.get("coordinates", [])
            pts = []
            if gtype == "LineString":
                pts = raw_coords
            elif gtype == "MultiLineString":
                for line in raw_coords:
                    pts.extend(line)

            if key not in grouped_rivers:
                grouped_rivers[key] = {
                    "name_en": name_en,
                    "name_fr": name_fr,
                    "name_alt": p.get("name_alt"),
                    "label": p.get("label"),
                    "coords": list(pts),
                }
            else:
                grouped_rivers[key]["coords"].extend(pts)
                if not grouped_rivers[key]["name_fr"] and name_fr:
                    grouped_rivers[key]["name_fr"] = name_fr

        for r_data in grouped_rivers.values():
            pts = r_data["coords"]
            if not pts:
                continue
            avg_lon = sum(pt[0] for pt in pts) / len(pts)
            avg_lat = sum(pt[1] for pt in pts) / len(pts)
            lat, lon = round(float(avg_lat), 4), round(float(avg_lon), 4)

            name_en = r_data["name_en"]
            name_fr = r_data["name_fr"]

            clean_fr = re.sub(r"^(fleuve|riviere|river)\s+", "", name_fr, flags=re.IGNORECASE).strip()
            clean_en = re.sub(r"\s+river$", "", name_en, flags=re.IGNORECASE).strip()

            is_fleuve = (
                normalize_key(clean_fr) in MAJOR_FLEUVES
                or normalize_key(clean_en) in MAJOR_FLEUVES
                or name_fr.lower().startswith("fleuve ")
            )
            entity_type = "fleuve" if is_fleuve else "river"
            prefix = "Fleuve " if is_fleuve else "Rivière "
            formatted_name_fr = f"{prefix}{clean_fr}"

            aliases = set()
            for cand in [name_en, name_fr, clean_en, clean_fr, r_data.get("name_alt"), r_data.get("label")]:
                if not cand:
                    continue
                norm = normalize_key(str(cand))
                if not norm:
                    continue
                base = re.sub(r"^(fleuve|riviere|river)\s+", "", norm).strip()
                base = re.sub(r"\s+river$", "", base).strip()
                if base:
                    aliases.add(base)
                    aliases.add(f"riviere {base}")
                    aliases.add(f"fleuve {base}")
                    aliases.add(f"{base} river")
                    aliases.add(f"river {base}")
                aliases.add(norm)

            dataset.append(
                {
                    "type": entity_type,
                    "name": name_en,
                    "name_fr": formatted_name_fr,
                    "lat": lat,
                    "lon": lon,
                    "aliases": sorted(aliases),
                }
            )

    # ====================================================================================
    # STEP 8: LOAD HISTORICAL TERRITORIES
    # 8.1 Pre-Confederation & Global Historical Territories
    # Source: `aourednik/historical-basemaps` (world_1700.geojson, world_1715.geojson, world_1783.geojson)
    # Dynamically calculates polygon centroids [lat, lon] for New France, Louisiana, Thirteen Colonies,
    # Province of Quebec, and colonial empires.
    # ====================================================================================
    print("Fetching historical territories and colonial empires from aourednik/historical-basemaps...")
    basemap_cache: dict[str, dict | None] = {}
    for target in HISTORICAL_BASEMAP_TARGETS:
        fn = target["file"]
        if fn not in basemap_cache:
            basemap_cache[fn] = fetch_historical_basemap(fn)

        geo_data = basemap_cache[fn]
        lat, lon = None, None
        if geo_data:
            for feat in geo_data.get("features", []):
                p = feat.get("properties", {})
                p_name = p.get("NAME") or p.get("name")
                if p_name == target["match_name"]:
                    lat, lon = compute_polygon_centroid(feat.get("geometry", {}))
                    break

        if lat is None or lon is None:
            print(f"Warning: could not calculate centroid for {target['name']}, skipping (no fallback).")
            continue

        aliases = set()
        for cand in target.get("aliases", []) + [target["name_fr"], target["name"]]:
            norm = normalize_key(cand)
            if norm:
                aliases.add(norm)

        dataset.append(
            {
                "type": target["type"],
                "name": target["name"],
                "name_fr": target["name_fr"],
                "lat": lat,
                "lon": lon,
                "start_year": target["start_year"],
                "end_year": target["end_year"],
                "aliases": sorted(aliases),
            }
        )

    # 8.2 Canadian Historical Evolution (1867–2003) from Official RNCan Dataset
    # Source: `table-Évolution-territoriale-du-Canada,-1867-à-2003.json`
    # Information: Dynamically computes centroid [lat, lon] from polygon geometries,
    # extracts historical validity intervals (start_year, end_year) across each milestone period.
    canadian_added_count = 0
    if CANADIAN_EVOLUTION_FILE.exists():
        print(f"Loading Canadian territorial evolution from {CANADIAN_EVOLUTION_FILE.name}...")
        try:
            with open(CANADIAN_EVOLUTION_FILE, "r", encoding="utf-8") as f:
                c_data = json.load(f)

            c_features = c_data.get("features", [])
            # Collect all distinct milestone years sorted
            all_milestones = sorted(
                list(
                    set(
                        int(feat["properties"]["START_TIME"])
                        for feat in c_features
                        if feat.get("properties", {}).get("START_TIME") is not None
                    )
                )
            )
            milestone_to_next = {}
            for i, yr in enumerate(all_milestones):
                if i + 1 < len(all_milestones):
                    milestone_to_next[yr] = all_milestones[i + 1]
                else:
                    milestone_to_next[yr] = 2003

            # Group features by (NOM_PROV, START_TIME)
            grouped_canadian: dict[tuple[str, int], list[dict]] = {}
            for feat in c_features:
                p = feat.get("properties", {})
                nom_prov = p.get("NOM_PROV")
                start_time = p.get("START_TIME")
                if not nom_prov or start_time is None or nom_prov not in CANADIAN_PROVINCE_METADATA:
                    continue
                start_year = int(start_time)
                grouped_canadian.setdefault((nom_prov, start_year), []).append(feat)

            for (nom_prov, start_year), feats in grouped_canadian.items():
                meta = CANADIAN_PROVINCE_METADATA[nom_prov]
                end_year = milestone_to_next.get(start_year, 2003)

                rings = []
                for feat in feats:
                    geom = feat.get("geometry", {})
                    gtype = geom.get("type")
                    raw_coords = geom.get("coordinates", [])
                    if gtype == "Polygon" and raw_coords:
                        rings.append(raw_coords[0])
                    elif gtype == "MultiPolygon" and raw_coords:
                        for poly in raw_coords:
                            if poly:
                                rings.append(poly[0])

                if not rings:
                    continue

                largest_ring = max(rings, key=ring_area)
                area = ring_area(largest_ring)
                lat, lon = ring_centroid(largest_ring)

                # Safeguards 1 & 2:
                # 1. Largest polygon by area prevents small island fragments from skewing the centroid.
                # 2. Sanity-check vs curated reference coordinates: if the polygon area is tiny (< 0.2 sq deg)
                #    or the computed centroid deviates significantly (> 4.5 deg) from the reference,
                #    safely fall back to the curated mainland coordinates.
                ref_lat = meta.get("ref_lat")
                ref_lon = meta.get("ref_lon")
                if ref_lat is not None and ref_lon is not None:
                    dist = math.hypot(lat - ref_lat, lon - ref_lon)
                    if area < 0.2 or dist > 4.5:
                        lat, lon = ref_lat, ref_lon

                aliases = set()
                for cand in meta.get("aliases", []) + [meta["name_fr"], meta["name_en"]]:
                    norm = normalize_key(cand)
                    if norm:
                        aliases.add(norm)
                        if "district" in norm:
                            aliases.add(norm.replace("district", "territoire"))
                            meta["name_fr"] = meta["name_fr"].replace("district", "territoire")

                entity = {
                    "type": meta["type"],
                    "name": meta["name_en"],
                    "name_fr": meta["name_fr"],
                    "lat": lat,
                    "lon": lon,
                    "start_year": start_year,
                    "end_year": end_year,
                    "aliases": sorted(aliases),
                }

                dataset.append(entity)
                canadian_added_count += 1

            print(f"Loaded {canadian_added_count} Canadian historical milestone entities with dynamic centroids.")
        except Exception as e:
            print(f"Warning: could not load Canadian territorial evolution file: {e}")

    # STEP 9: STANDARDIZE CAPITALIZATION & SANITIZE DISTRICTS
    # Enforces that all entity names begin with an uppercase letter while preserving
    # interior casing, and replaces any mention of 'district' in French names with 'territoire'.
    for entity in dataset:
        if "name_fr" in entity and entity["name_fr"]:
            entity["name_fr"] = sanitize_district_to_territoire(entity["name_fr"])
            entity["name_fr"] = capitalize_first(entity["name_fr"])
        if "name" in entity and entity["name"]:
            entity["name"] = capitalize_first(entity["name"])

    # STEP 10: MERGE WITH EXISTING DATA (NEVER DELETE EXISTING LINES)
    # Merges newly generated entities with existing entries in `OUTPUT_FILE` (app/data/geographic_entities.json)
    # ensuring no existing line or manual entry is ever removed.
    dataset = merge_with_existing(dataset, OUTPUT_FILE)

    # STEP 11: SERIALIZE TO JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"\n Successfully generated: {OUTPUT_FILE}")
    print(f" Total entities: {len(dataset)}")
    print(f" File size: {size_kb:.1f} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
