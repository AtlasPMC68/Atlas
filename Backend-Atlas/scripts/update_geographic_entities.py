#!/usr/bin/env python
"""Generate an offline, lightweight JSON dataset of geographic entities with GPS coordinates.

Derives geographic entities dynamically from geonamescache, local cache, and Natural Earth,
without requiring external non-standard dependencies.

Output:
    Backend-Atlas/app/data/geographic_entities.json

Command: 
    Get-Content Backend-Atlas\scripts\update_geographic_entities.py | docker exec -i atlas-backend python -

"""

import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import geonamescache

# Safe dynamic resolution for static linters (Pylance/Pyright) when stubs are absent
GeonamesCache = getattr(geonamescache, "GeonamesCache", None)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "app" / "data"
GEOJSON_CACHE_DIR = DATA_DIR / "geojson_cache"
OUTPUT_FILE = DATA_DIR / "geographic_entities.json"

# Natural Earth Vector GeoJSON repository base URL
NE_BASE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"

# Standard French continent translations
FRENCH_CONTINENT_NAMES: Dict[str, str] = {
    "AF": "Afrique",
    "AN": "Antarctique",
    "AS": "Asie",
    "EU": "Europe",
    "NA": "Amérique du Nord",
    "OC": "Océanie",
    "SA": "Amérique du Sud",
}


def normalize_key(s: str) -> str:
    """Strip accents, punctuation, and extra whitespace to generate matching keys."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


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


def ring_centroid(ring: list) -> Tuple[float, float]:
    """Calculate the geometric centroid (lat, lon) of a 2D polygon ring."""
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


def compute_polygon_centroid(geom: dict) -> Tuple[Optional[float], Optional[float]]:
    """Calculate the geometric centroid of Polygon or MultiPolygon coordinates."""
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


def load_or_fetch_geojson(filename: str) -> Optional[dict]:
    """Load GeoJSON from local cache or fetch from Natural Earth repository if available."""
    GEOJSON_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local_path = GEOJSON_CACHE_DIR / filename
    if local_path.exists():
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = NE_BASE_URL + filename
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            try:
                temp_cache = local_path.with_suffix(".tmp")
                with open(temp_cache, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                temp_cache.replace(local_path)
            except Exception:
                pass
            return data
    except Exception as e:
        print(f"Info: GeoJSON {filename} not downloaded ({e}). Continuing with local data.")
        return None


def resolve_country_coordinates(
    iso: str,
    capital: str,
    country_cities: List[dict],
    existing: Optional[dict] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Dynamically resolve country GPS coordinates from cities or existing data."""
    # 1. Use existing validated coordinates if available
    if existing and existing.get("lat") is not None and existing.get("lon") is not None:
        return existing["lat"], existing["lon"]

    # 2. Look up capital city in pre-indexed cities for this country
    if capital and country_cities:
        norm_cap = normalize_key(capital)
        for city in country_cities:
            if normalize_key(city.get("name") or "") == norm_cap:
                return round(float(city["latitude"]), 4), round(float(city["longitude"]), 4)

    # 3. Fallback: pick the largest city in the country
    if country_cities:
        largest = max(country_cities, key=lambda c: int(c.get("population") or 0))
        return round(float(largest["latitude"]), 4), round(float(largest["longitude"]), 4)

    return None, None


def deduplicate_by_name_and_location(entities: List[dict]) -> List[dict]:
    """Deduplicate elements having the same normalized name and location."""
    dedup_map: Dict[tuple, dict] = {}
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


def merge_with_existing(new_entities: List[dict], output_file: Path) -> List[dict]:
    """Merge newly generated entities into the existing JSON dataset."""
    if not output_file.exists():
        return deduplicate_by_name_and_location(new_entities)

    try:
        with open(output_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
    except Exception as e:
        print(f"Warning: could not read existing {output_file.name} for merge: {e}")
        existing_data = []

    def _entity_key(e: dict) -> tuple:
        etype = e.get("type", "")
        raw_name = e.get("name_fr") or e.get("name") or ""
        norm_name = normalize_key(raw_name)

        # 1. Unique standard codes
        if etype == "continent":
            return ("continent", (e.get("code") or norm_name).upper())
        if etype == "country":
            return ("country", (e.get("iso") or norm_name).upper())

        # 2. Historical entities with explicit year range
        start_year = e.get("start_year")
        end_year = e.get("end_year")
        if start_year is not None or end_year is not None:
            return (norm_name, etype, start_year, end_year)

        # 3. Administrative divisions
        if etype in ("state", "province", "territory"):
            return ("admin", e.get("country_code", ""), norm_name)

        # 4. Natural / physical features (lakes, rivers, seas, oceans)
        lat = e.get("lat")
        lon = e.get("lon")
        lat_rounded = round(float(lat), 1) if lat is not None else None
        lon_rounded = round(float(lon), 1) if lon is not None else None
        return (norm_name, etype, lat_rounded, lon_rounded)

    merged: Dict[tuple, dict] = {}

    # 1. Load existing data first
    for entity in existing_data:
        key = _entity_key(entity)
        merged[key] = dict(entity)

    # 2. Merge newly generated entities
    for entity in new_entities:
        key = _entity_key(entity)
        if key in merged:
            target = merged[key]
            # Preserve existing coordinates if new entity has None
            for k, v in entity.items():
                if k in ("lat", "lon") and v is None and target.get(k) is not None:
                    continue
                if k == "aliases":
                    combined = set(target.get("aliases", [])) | set(v or [])
                    target["aliases"] = sorted(combined)
                elif v is not None:
                    target[k] = v
        else:
            merged[key] = dict(entity)

    return deduplicate_by_name_and_location(list(merged.values()))


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    gc_cls = GeonamesCache if GeonamesCache is not None else getattr(geonamescache, "GeonamesCache")
    gc = gc_cls()
    gc_countries = gc.get_countries()
    dataset: List[dict] = []

    # Pre-index cities by country for O(1) coordinate lookups (avoids 12M loop iterations)
    cities_by_country: Dict[str, List[dict]] = {}
    for city in gc.get_cities().values():
        cc = city.get("countrycode")
        if cc:
            cities_by_country.setdefault(cc, []).append(city)

    # Cache existing entries to preserve French names, aliases, and calibrated coordinates
    existing_countries_by_iso: Dict[str, dict] = {}
    existing_continents_by_code: Dict[str, dict] = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                for entry in json.load(f):
                    etype = entry.get("type")
                    if etype == "country" and entry.get("iso"):
                        existing_countries_by_iso[entry["iso"]] = entry
                    elif etype == "continent" and entry.get("code"):
                        existing_continents_by_code[entry["code"]] = entry
        except Exception:
            pass

    # 1. SOVEREIGN COUNTRIES & TERRITORIES (Dynamic)
    print(f"Processing {len(gc_countries)} countries from geonamescache...")
    country_coords_by_continent: Dict[str, List[Tuple[float, float]]] = {}

    for iso, info in gc_countries.items():
        name_en = info.get("name") or ""
        iso3 = info.get("iso3") or ""
        capital = info.get("capital") or ""
        population = int(info.get("population") or 0)
        cont_code = info.get("continentcode") or ""

        existing = existing_countries_by_iso.get(iso)
        name_fr = (existing.get("name_fr") if existing else None) or name_en

        country_cities = cities_by_country.get(iso, [])
        lat, lon = resolve_country_coordinates(iso, capital, country_cities, existing)
        if lat is not None and lon is not None and cont_code:
            country_coords_by_continent.setdefault(cont_code, []).append((lat, lon))

        aliases = set()
        for candidate in [name_en, name_fr, iso, iso3, capital]:
            if candidate:
                norm = normalize_key(candidate)
                if norm:
                    aliases.add(norm)
        if existing and existing.get("aliases"):
            aliases.update(existing["aliases"])

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

    # 2. CONTINENTS (Dynamic centroids from country distributions)
    print("Deriving continents dynamically from geonamescache...")
    for code, cont_info in gc.get_continents().items():
        name_en = cont_info.get("name") or code
        name_fr = FRENCH_CONTINENT_NAMES.get(code, name_en)
        coords_list = country_coords_by_continent.get(code, [])

        existing_cont = existing_continents_by_code.get(code)
        if existing_cont and existing_cont.get("lat") is not None and existing_cont.get("lon") is not None:
            lat, lon = existing_cont["lat"], existing_cont["lon"]
        elif coords_list:
            lat = round(sum(p[0] for p in coords_list) / len(coords_list), 4)
            lon = round(sum(p[1] for p in coords_list) / len(coords_list), 4)
        elif code == "AN":
            lat, lon = -82.86, 135.00
        else:
            lat, lon = None, None

        aliases = {normalize_key(name_en), normalize_key(name_fr), normalize_key(code)}
        if existing_cont and existing_cont.get("aliases"):
            aliases.update(existing_cont["aliases"])

        dataset.append(
            {
                "type": "continent",
                "code": code,
                "name": name_en,
                "name_fr": name_fr,
                "lat": lat,
                "lon": lon,
                "aliases": sorted(aliases),
            }
        )

    # 3. STATES & PROVINCES (Natural Earth Admin-1 or geonamescache US States)
    admin1_data = load_or_fetch_geojson("ne_50m_admin_1_states_provinces.geojson")
    if admin1_data:
        print(f"Processing {len(admin1_data.get('features', []))} states and provinces from Natural Earth...")
        for feat in admin1_data.get("features", []):
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
    else:
        # Fallback to geonamescache US States if GeoJSON is offline
        for st_code, st_info in gc.get_us_states().items():
            st_name = st_info.get("name") or ""
            aliases = {normalize_key(st_name), normalize_key(st_code), f"etat de {normalize_key(st_name)}"}
            dataset.append(
                {
                    "type": "state",
                    "country_code": "USA",
                    "name": st_name,
                    "name_fr": st_name,
                    "lat": None,
                    "lon": None,
                    "aliases": sorted(aliases),
                }
            )

    # 4. OCEANS & SEAS (Natural Earth Marine)
    marine_data = load_or_fetch_geojson("ne_50m_geography_marine_polys.geojson")
    if marine_data:
        print(f"Processing {len(marine_data.get('features', []))} oceans and seas...")
        for feat in marine_data.get("features", []):
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

            aliases = {normalize_key(str(cand)) for cand in [name_en, name_fr, p.get("namealt"), p.get("label")] if cand}
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

    # 5. LAKES
    lakes_data = load_or_fetch_geojson("ne_50m_lakes.geojson")
    if lakes_data:
        print(f"Processing {len(lakes_data.get('features', []))} lakes...")
        for feat in lakes_data.get("features", []):
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
            formatted_lake_fr = name_fr if name_fr.lower().startswith("mer ") else f"Lac {clean_lake_fr}"

            aliases = set()
            for cand in [name_en, name_fr, clean_lake_fr, p.get("name_alt"), p.get("label")]:
                if cand:
                    norm = normalize_key(str(cand))
                    if norm:
                        base = re.sub(r"^(lac|lake)\s+", "", norm).strip()
                        if base:
                            aliases.add(base)
                            aliases.add(f"lac {base}")
                            aliases.add(f"lake {base}")
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

    # 6. RIVERS & FLEUVES
    rivers_data = load_or_fetch_geojson("ne_50m_rivers_lake_centerlines_scale_rank.geojson")
    if rivers_data:
        print(f"Processing {len(rivers_data.get('features', []))} river segments...")
        grouped_rivers: Dict[str, dict] = {}
        for feat in rivers_data.get("features", []):
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
            pts = raw_coords if gtype == "LineString" else [pt for line in raw_coords for pt in line] if gtype == "MultiLineString" else []

            if key not in grouped_rivers:
                grouped_rivers[key] = {
                    "name_en": name_en,
                    "name_fr": name_fr,
                    "scalerank": p.get("scalerank"),
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
            scalerank = r_data.get("scalerank")
            clean_fr = re.sub(r"^(fleuve|riviere|river)\s+", "", name_fr, flags=re.IGNORECASE).strip()
            clean_en = re.sub(r"\s+river$", "", name_en, flags=re.IGNORECASE).strip()

            is_fleuve = (scalerank is not None and scalerank <= 2) or name_fr.lower().startswith("fleuve ")
            entity_type = "fleuve" if is_fleuve else "river"
            prefix = "Fleuve " if is_fleuve else "Rivière "
            formatted_name_fr = f"{prefix}{clean_fr}"

            aliases = set()
            for cand in [name_en, name_fr, clean_en, clean_fr, r_data.get("name_alt"), r_data.get("label")]:
                if cand:
                    norm = normalize_key(str(cand))
                    if norm:
                        base = re.sub(r"^(fleuve|riviere|river)\s+", "", norm).strip()
                        if base:
                            aliases.add(base)
                            aliases.add(f"riviere {base}")
                            aliases.add(f"fleuve {base}")
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

    # 7. STANDARDIZE CAPITALIZATION
    for entity in dataset:
        if "name_fr" in entity and entity["name_fr"]:
            entity["name_fr"] = capitalize_first(entity["name_fr"])
        if "name" in entity and entity["name"]:
            entity["name"] = capitalize_first(entity["name"])

    # 8. MERGE WITH EXISTING DATASET
    dataset = merge_with_existing(dataset, OUTPUT_FILE)

    # 9. SERIALIZE TO JSON (Atomic write via .tmp to prevent corruption)
    temp_file = OUTPUT_FILE.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    temp_file.replace(OUTPUT_FILE)

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"\nSuccessfully generated: {OUTPUT_FILE}")
    print(f"Total entities: {len(dataset)}")
    print(f"File size: {size_kb:.1f} KB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
