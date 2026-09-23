"""The city gazetteer behind city control points.

The user names the cities their map shows; this finds them. Only cities inside
the framing box are ever returned -- a city outside the world area the user
framed is not on their map, and offering it would invite a wrong pairing.

**Why a SQLite file rather than geonamescache directly.** geonamescache loads
its whole JSON (15 MB for ``cities15000``, 56 MB for ``cities1000``) into Python
objects, for the world, in every process that imports it. Here only the frame
is wanted. So the gazetteer is built once from the pinned geonamescache into a
small SQLite file with a (lat, lon) index, and each search reads just the
frame's rows from disk: ~150 cities for a Quebec-sized box, in a few ms, with
nothing held in memory between requests.

**Which cities.** ``cities15000``: every place of 15,000+ inhabitants, ~32k
worldwide. The cities a map is georeferenced from are the big, stable ones.
Alternate names are indexed too (Latin script only, which keeps the file ~8 MB
instead of ~13 MB), so historical and foreign spellings match: "Kebek" finds
Quebec.

**The file is derived, never committed.** Built on first use into ``app/.cache``
(gitignored, bind-mounted into every backend container), keyed on the
geonamescache version and ``BUILDER_VERSION`` so a library upgrade or a change
here rebuilds it rather than serving a stale one.

**No fallback.** A name the gazetteer does not know returns no candidates, and
that city simply is not used.
"""

import difflib
import logging
import os
import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from importlib.metadata import version as package_version
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: geonamescache's population threshold: 500, 1000, 5000 or 15000.
MIN_POPULATION = 15000
#: Bump when the schema or what gets indexed changes, to force a rebuild.
BUILDER_VERSION = "1"

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")

#: Below this similarity a name is not offered as a near match. 0.8 lets
#: "Trois Riviere" find "Trois-Rivieres" and "Montral" find "Montreal", while
#: keeping unrelated names out.
FUZZY_MIN_RATIO = 0.8
#: A prefix shorter than this matches too much to mean anything.
PREFIX_MIN_LENGTH = 3

_MATCH_RANK = {"exact": 3, "prefix": 2, "fuzzy": 1}

_build_lock = threading.Lock()


def normalize_name(name: str) -> str:
    """Accent-, case- and punctuation-insensitive form of a place name.

    "Trois-Rivières", "trois rivieres" and "TROIS RIVIERES" all become
    "trois rivieres".
    """
    decomposed = unicodedata.normalize("NFKD", name or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    spaced = re.sub(r"[-'’.,]+", " ", stripped.casefold())
    return " ".join(spaced.split())


def _is_latin(name: str) -> bool:
    """Latin script only: what a user reading a Western map will type."""
    return all(ord(c) < 0x250 for c in name)


@dataclass(frozen=True)
class CityCandidate:
    """One gazetteer city offered for a typed name."""

    geonameid: int
    name: str
    lat: float
    lon: float
    country: str
    population: int
    #: The name that matched, which may be an alternate one ("Kebek").
    matched_name: str
    match: str  # "exact" | "prefix" | "fuzzy"
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.geonameid,
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "country": self.country,
            "population": self.population,
            "matchedName": self.matched_name,
            "match": self.match,
        }


# --------------------------------------------------------------------------
# Building the file
# --------------------------------------------------------------------------


def gazetteer_path() -> str:
    """Where the gazetteer for the installed geonamescache lives."""
    gnc = package_version("geonamescache")
    return os.path.join(
        CACHE_DIR,
        f"cities{MIN_POPULATION}-gnc{gnc}-b{BUILDER_VERSION}.sqlite",
    )


def build_gazetteer(path: str) -> str:
    """Write the SQLite gazetteer to *path*. Atomic: readers never see half a file."""
    import geonamescache

    cities = geonamescache.GeonamesCache(
        min_city_population=MIN_POPULATION
    ).get_cities()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    if os.path.exists(tmp):
        os.remove(tmp)

    db = sqlite3.connect(tmp)
    try:
        db.executescript(
            """
            CREATE TABLE city (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                country TEXT NOT NULL,
                population INTEGER NOT NULL
            );
            CREATE TABLE city_name (
                city_id INTEGER NOT NULL REFERENCES city(id),
                name_norm TEXT NOT NULL,
                name TEXT NOT NULL
            );
            """
        )
        for info in cities.values():
            try:
                city_id = int(info["geonameid"])
                name = str(info["name"])
                lat = float(info["latitude"])
                lon = float(info["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            db.execute(
                "INSERT INTO city VALUES (?, ?, ?, ?, ?, ?)",
                (
                    city_id,
                    name,
                    lat,
                    lon,
                    str(info.get("countrycode") or ""),
                    int(info.get("population") or 0),
                ),
            )
            # One row per distinct normalised name; the main name first so it
            # is the one shown when it and an alternate normalise alike.
            names: Dict[str, str] = {}
            for candidate in [name, *(info.get("alternatenames") or [])]:
                if not isinstance(candidate, str) or not _is_latin(candidate):
                    continue
                key = normalize_name(candidate)
                if key and key not in names:
                    names[key] = candidate
            db.executemany(
                "INSERT INTO city_name VALUES (?, ?, ?)",
                [(city_id, key, shown) for key, shown in names.items()],
            )
        db.executescript(
            """
            CREATE INDEX city_lat_lon ON city(lat, lon);
            CREATE INDEX city_name_city ON city_name(city_id);
            """
        )
        db.commit()
        db.execute("VACUUM")
    finally:
        db.close()

    os.replace(tmp, path)
    logger.info(f"[GAZETTEER] built {path} from {len(cities)} cities")
    return path


def ensure_gazetteer() -> str:
    """The gazetteer path, building the file first if it is not there yet."""
    path = gazetteer_path()
    if os.path.exists(path):
        return path
    with _build_lock:
        if not os.path.exists(path):
            build_gazetteer(path)
    return path


# --------------------------------------------------------------------------
# Searching
# --------------------------------------------------------------------------


def _cities_in_frame(bounds: Dict[str, float]) -> Dict[int, Dict[str, Any]]:
    """Every city inside *bounds* with all of its names, read from disk."""
    west, south, east, north = (
        float(bounds["west"]),
        float(bounds["south"]),
        float(bounds["east"]),
        float(bounds["north"]),
    )
    # A box crossing the antimeridian has west > east (frame.py accepts it).
    if west <= east:
        lon_clause, lon_args = "c.lon BETWEEN ? AND ?", (west, east)
    else:
        lon_clause, lon_args = "(c.lon >= ? OR c.lon <= ?)", (west, east)

    uri = f"file:{ensure_gazetteer()}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    try:
        rows = db.execute(
            f"""
            SELECT c.id, c.name, c.lat, c.lon, c.country, c.population,
                   n.name_norm, n.name
            FROM city c JOIN city_name n ON n.city_id = c.id
            WHERE c.lat BETWEEN ? AND ? AND {lon_clause}
            """,
            (south, north, *lon_args),
        ).fetchall()
    finally:
        db.close()

    cities: Dict[int, Dict[str, Any]] = {}
    for city_id, name, lat, lon, country, population, name_norm, shown in rows:
        city = cities.setdefault(
            city_id,
            {
                "name": name,
                "lat": lat,
                "lon": lon,
                "country": country,
                "population": population,
                "names": [],
            },
        )
        city["names"].append((name_norm, shown))
    return cities


def _best_match(query: str, names: List[tuple]) -> Optional[tuple]:
    """(kind, score, shown name) of the best-matching name, or None."""
    best: Optional[tuple] = None
    for norm, shown in names:
        if norm == query:
            candidate = ("exact", 1.0, shown)
        elif len(query) >= PREFIX_MIN_LENGTH and norm.startswith(query):
            candidate = ("prefix", len(query) / len(norm), shown)
        else:
            ratio = difflib.SequenceMatcher(None, query, norm).ratio()
            if ratio < FUZZY_MIN_RATIO:
                continue
            candidate = ("fuzzy", ratio, shown)
        if best is None or (_MATCH_RANK[candidate[0]], candidate[1]) > (
            _MATCH_RANK[best[0]],
            best[1],
        ):
            best = candidate
    return best


def search_cities(
    query: str, bounds: Dict[str, float], limit: int = 10
) -> List[CityCandidate]:
    """Cities inside *bounds* whose name, or an alternate name, matches *query*.

    Ranked exact before prefix before near match, then by how close the match
    is, then by population, so "Kingston" offers the big one first. Never
    raises on an unknown name: no match is an empty list.
    """
    normalized = normalize_name(query)
    if not normalized:
        return []

    found: List[CityCandidate] = []
    for city_id, city in _cities_in_frame(bounds).items():
        match = _best_match(normalized, city["names"])
        if match is None:
            continue
        kind, score, shown = match
        found.append(
            CityCandidate(
                geonameid=int(city_id),
                name=city["name"],
                lat=float(city["lat"]),
                lon=float(city["lon"]),
                country=city["country"],
                population=int(city["population"]),
                matched_name=shown,
                match=kind,
                score=float(score),
            )
        )

    found.sort(key=lambda c: (-_MATCH_RANK[c.match], -c.score, -c.population, c.name))
    return found[:limit]
