#!/usr/bin/env python
"""Generate an offline, lightweight JSON dataset of geographic entities with GPS coordinates.

Contains:
- Continents (7)
- Countries (252) from geonamescache + pycountry + countryinfo
- Oceans & Major Seas (~118) from Natural Earth Marine Polys
- Major Lakes (~412) from Natural Earth Lakes
- States & Provinces (Admin-1) from Natural Earth
- Major Rivers & Fleuves (~348) from Natural Earth Rivers
- Historical Territories (Terre de Rupert, Nouvelle-France)

Output:
    Backend-Atlas/app/data/geographic_entities.json
"""

import gettext
import json
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

NE_BASE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"

# Fallback coordinates [lat, lon] for small territories not covered by countryinfo
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

# The 7 Continents
CONTINENTS = {
    "AF": {"name": "Africa", "name_fr": "Afrique", "lat": 1.65, "lon": 17.30},
    "AN": {"name": "Antarctica", "name_fr": "Antarctique", "lat": -82.86, "lon": 135.00},
    "AS": {"name": "Asia", "name_fr": "Asie", "lat": 34.05, "lon": 100.62},
    "EU": {"name": "Europe", "name_fr": "Europe", "lat": 54.53, "lon": 15.26},
    "NA": {"name": "North America", "name_fr": "Amérique du Nord", "lat": 54.53, "lon": -105.26},
    "OC": {"name": "Oceania", "name_fr": "Océanie", "lat": -22.74, "lon": 140.02},
    "SA": {"name": "South America", "name_fr": "Amérique du Sud", "lat": -8.78, "lon": -55.49},
}

HISTORICAL_TERRITORIES = [
    {
        "type": "territory",
        "name": "Rupert's Land",
        "name_fr": "Terre de Rupert",
        "lat": 55.0,
        "lon": -85.0,
        "aliases": ["rupert s land", "ruperts land", "terre de rupert"],
    },
    {
        "type": "territory",
        "name": "New France",
        "name_fr": "Nouvelle-France",
        "lat": 48.0,
        "lon": -72.0,
        "aliases": ["new france", "nouvelle france"],
    },
    {
        "type": "territory",
        "name": "Louisiana",
        "name_fr": "Louisiane",
        "lat": 39.5,
        "lon": -96.5,
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
]

# Major world fleuves (rivers flowing directly into seas/oceans)
MAJOR_FLEUVES = {
    "saint-laurent", "saint laurent", "saint lawrence", "st. lawrence", "st lawrence",
    "mississippi", "amazon", "amazone", "amazonas", "nile", "nil",
    "congo", "yangtze", "yangzi", "chang jiang", "fleuve bleu",
    "yellow river", "fleuve jaune", "huang he",
    "rhine", "rhin", "danube", "seine", "loire", "rhone", "garonne",
    "volga", "don", "dnieper", "dniepr", "elbe", "oder", "vistula", "vistule",
    "thames", "tamise", "tagus", "tage", "ebro", "ebre", "douro",
    "colorado", "columbia", "yukon", "mackenzie", "rio grande", "rio bravo",
    "parana", "orinoco", "orenoque",
    "ganges", "gange", "indus", "brahmaputra", "brahmapoutre", "mekong",
    "amur", "amour", "lena", "ob", "yenisey", "ienissei", "murray",
    "niger", "zambezi", "zambeze", "senegal", "orange",
}


def normalize_key(s: str) -> str:
    """Strip accents, punctuation, and extra whitespace to generate matching keys."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def clean_french_name(name_fr: str) -> list[str]:
    """Given an inverted name like 'Russie, Fédération de', return ['Russie', 'Fédération de Russie']."""
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


def compute_polygon_centroid(geom: dict) -> tuple[float | None, float | None]:
    """Calculate the average latitude/longitude centroid of Polygon or MultiPolygon coordinates."""
    coords = []
    gtype = geom.get("type")
    raw_coords = geom.get("coordinates", [])

    if gtype == "Polygon" and raw_coords:
        coords = raw_coords[0]
    elif gtype == "MultiPolygon" and raw_coords:
        for poly in raw_coords:
            if poly:
                coords.extend(poly[0])

    if coords:
        avg_lon = sum(pt[0] for pt in coords) / len(coords)
        avg_lat = sum(pt[1] for pt in coords) / len(coords)
        return round(float(avg_lat), 4), round(float(avg_lon), 4)
    return None, None


def fetch_geojson(filename: str) -> dict | None:
    """Fetch GeoJSON file from Natural Earth repo."""
    url = NE_BASE_URL + filename
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Warning: could not download {filename}: {e}")
        return None


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load French translator from pycountry
    try:
        trans_fr = gettext.translation("iso3166-1", pycountry.LOCALES_DIR, languages=["fr"])
    except Exception as e:
        print(f"Warning: could not load French locale for pycountry: {e}")
        trans_fr = None

    gc = geonamescache.GeonamesCache()
    gc_countries = gc.get_countries()

    dataset = []

    # 2. Continents
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

    # 3. Countries
    print(f"Processing {len(gc_countries)} countries...")
    for iso, info in gc_countries.items():
        name_en = info.get("name") or ""
        iso3 = info.get("iso3") or ""
        capital = info.get("capital") or ""
        population = int(info.get("population") or 0)

        # French translation
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

        # Lat / Lon resolution
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

    # 4. Oceans & Major Seas (from Natural Earth)
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

    # 5. Major Lakes (from Natural Earth)
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

    # 6. States & Provinces (Admin-1 from Natural Earth: US States, Canadian Provinces, etc.)
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

    # 7. Major Rivers (from Natural Earth)
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

    # 8. Historical Territories
    for terr in HISTORICAL_TERRITORIES:
        dataset.append(terr)

    # 9. Enforce that every name_fr and name begins with a capital letter
    for entity in dataset:
        if "name_fr" in entity and entity["name_fr"]:
            entity["name_fr"] = capitalize_first(entity["name_fr"])
        if "name" in entity and entity["name"]:
            entity["name"] = capitalize_first(entity["name"])

    # 10. Save combined dataset
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"\n Successfully generated: {OUTPUT_FILE}")
    print(f" Total entities: {len(dataset)}")
    print(f" File size: {size_kb:.1f} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
