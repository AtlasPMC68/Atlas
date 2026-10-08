"""Administrative borders, for drawing expected zones in the dev-test editor.

Drop border files into ``app/geojson/borders/`` (see
``scripts/fetch_natural_earth_borders.py``) and they are picked up: each file is
recognised from its properties, so Natural Earth admin-0 (countries) and
admin-1 (states, provinces) and geoBoundaries ADM0 / ADM1 files all work, side
by side. Everything is indexed as countries, each with an optional whole-country
outline and a list of regions. """

import glob
import json
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import shapely
from shapely.geometry import mapping, shape

logger = logging.getLogger(__name__)

BORDERS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "geojson", "borders")

#: Default simplification, in degrees (~500 m). Natural Earth 10m is drawn for
#: 1:10M, about a kilometre, and a country at full resolution is hundreds of
#: thousands of vertices -- slow to send and slow to cut in the browser.
DEFAULT_SIMPLIFY_DEG = 0.005


@dataclass
class Region:
    id: str
    name: str
    wkb: bytes
    #: The larger unit it belongs to, when the file says (Natural Earth's
    #: ``region``: Lombardia for Milano, Bretagne for Finistere). Admin-1 is
    #: provinces for Italy and departements for France, so a regional map's
    #: zone is a whole group of them.
    group: Optional[str] = None


@dataclass
class Country:
    code: str
    name: str
    #: The whole-country outline, when an admin-0 file has it.
    wkb: Optional[bytes] = None
    regions: Dict[str, Region] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)


def _props(feature: Dict[str, Any]) -> Dict[str, Any]:
    """Properties with lower-cased keys: Natural Earth mixes ADM0_A3 and adm0_a3."""
    return {str(k).lower(): v for k, v in (feature.get("properties") or {}).items()}


def _text(props: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = props.get(key)
        if isinstance(value, str) and value.strip() and value.strip() != "-99":
            return value.strip()
    return None


def _classify(props: Dict[str, Any]) -> Optional[Tuple[int, str, Optional[str], str, str]]:
    """``(level, country code, country name, unit id, unit name)``, or None.

    Natural Earth admin-1 carries ``adm1_code``; admin-0 carries ``adm0_a3``
    without it; geoBoundaries carries ``shapeGroup`` and ``shapeType``. French
    names are preferred where the file has them: the editor is in French, and
    the zone name is what the pipette names have to match.
    """
    if "adm1_code" in props:
        code = _text(props, "adm0_a3", "iso_a2")
        name = _text(props, "name_fr", "name", "name_en")
        unit = _text(props, "adm1_code", "iso_3166_2")
        if code and name and unit:
            return 1, code, _text(props, "admin", "geonunit"), unit, name
        return None
    if "shapegroup" in props and "shapetype" in props:
        level = {"ADM0": 0, "ADM1": 1}.get(str(props.get("shapetype")).upper())
        code = _text(props, "shapegroup")
        name = _text(props, "shapename")
        unit = _text(props, "shapeid", "shapeiso") or name
        if level is not None and code and name and unit:
            return level, code, name if level == 0 else None, unit, name
        return None
    if "adm0_a3" in props:
        code = _text(props, "adm0_a3")
        name = _text(props, "name_fr", "name", "admin", "name_long")
        if code and name:
            return 0, code, name, code, name
    return None


@lru_cache(maxsize=1)
def _index_cached(files: Tuple[Tuple[str, float], ...]) -> Dict[str, Country]:
    countries: Dict[str, Country] = {}
    for path, _mtime in files:
        filename = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning(f"[BORDERS] Could not read {filename}: {e}")
            continue

        kept = 0
        for feature in data.get("features") or []:
            if not isinstance(feature, dict) or not feature.get("geometry"):
                continue
            classified = _classify(_props(feature))
            if classified is None:
                continue
            level, code, country_name, unit_id, unit_name = classified
            try:
                wkb = shape(feature["geometry"]).wkb
            except Exception:
                continue

            country = countries.setdefault(code, Country(code=code, name=country_name or code))
            if country_name and country.name == code:
                country.name = country_name
            if filename not in country.sources:
                country.sources.append(filename)
            if level == 0:
                # Natural Earth can split a country into several features;
                # the outline is all of them.
                country.wkb = (
                    wkb
                    if country.wkb is None
                    else shapely.union(shapely.from_wkb(country.wkb), shapely.from_wkb(wkb)).wkb
                )
                if country_name:
                    country.name = country_name
            else:
                group = _text(_props(feature), "region") if level == 1 else None
                country.regions[unit_id] = Region(
                    id=unit_id, name=unit_name, wkb=wkb, group=group
                )
            kept += 1
        logger.info(f"[BORDERS] {filename}: {kept} unit(s) indexed")
    return countries


def border_files(borders_dir: str = BORDERS_DIR) -> Tuple[Tuple[str, float], ...]:
    paths = sorted(
        glob.glob(os.path.join(borders_dir, "*.geojson"))
        + glob.glob(os.path.join(borders_dir, "*.json"))
    )
    return tuple((p, os.path.getmtime(p)) for p in paths)


def index(borders_dir: str = BORDERS_DIR) -> Dict[str, Country]:
    """Every country in the border files. Rebuilt when a file is added or changes."""
    return _index_cached(border_files(borders_dir))


def list_countries(borders_dir: str = BORDERS_DIR) -> Dict[str, Any]:
    countries = index(borders_dir)
    return {
        "files": [os.path.basename(p) for p, _ in border_files(borders_dir)],
        "countries": sorted(
            (
                {
                    "code": c.code,
                    "name": c.name,
                    "hasOutline": c.wkb is not None,
                    "regionCount": len(c.regions),
                }
                for c in countries.values()
            ),
            key=lambda c: c["name"].lower(),
        ),
    }


def list_regions(code: str, borders_dir: str = BORDERS_DIR) -> List[Dict[str, Any]]:
    """A country's regions, sorted by group then name. ``group`` may be None."""
    country = index(borders_dir).get(code)
    if country is None:
        raise KeyError(code)
    return sorted(
        (
            {"id": r.id, "name": r.name, "group": r.group}
            for r in country.regions.values()
        ),
        key=lambda r: ((r["group"] or "").lower(), r["name"].lower()),
    )


def border_zone(
    code: str,
    region_ids: Optional[Sequence[str]] = None,
    simplify_deg: float = DEFAULT_SIMPLIFY_DEG,
    borders_dir: str = BORDERS_DIR,
) -> Dict[str, Any]:
    """One zone: the whole country, or the union of the given regions.

    Returns ``{"name", "geometry"}`` with the geometry simplified by
    *simplify_deg* (topology preserved). Several regions make one zone (the
    Maritimes, say), named after all of them.

    Raises:
        KeyError: unknown country or region.
        ValueError: the country has no whole-country outline.
    """
    country = index(borders_dir).get(code)
    if country is None:
        raise KeyError(code)

    if region_ids:
        missing = [r for r in region_ids if r not in country.regions]
        if missing:
            raise KeyError(", ".join(missing))
        regions = [country.regions[r] for r in region_ids]
        geom = shapely.union_all([shapely.from_wkb(r.wkb) for r in regions])
        name = " + ".join(r.name for r in regions)
    else:
        if country.wkb is None:
            raise ValueError(f"No whole-country outline for {code}: pick its regions")
        geom = shapely.from_wkb(country.wkb)
        name = country.name

    if simplify_deg > 0:
        geom = geom.simplify(simplify_deg, preserve_topology=True)
    geom = shapely.make_valid(geom)
    # make_valid can nest a MultiPolygon inside a GeometryCollection: flatten twice.
    polygons = [
        g for g in shapely.get_parts(shapely.get_parts(geom)) if g.geom_type == "Polygon"
    ]
    geom = shapely.union_all(polygons) if polygons else geom
    return {"name": name, "geometry": mapping(geom)}
