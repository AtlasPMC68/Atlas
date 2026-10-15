"""The city gazetteer behind city control points. SQLite. 
Returns most populated city by the same name that is in the frame box selected """
# region Imports
import difflib
import logging
import os
import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version as package_version
from typing import Any, Dict, List, Optional, Tuple
# endregion
logger = logging.getLogger(__name__)

BUILDER_VERSION = "1"
MIN_POPULATION = 5000

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")

#: Below this similarity a name is not offered as a near match. 0.8 lets
#: "Trois Riviere" find "Trois-Rivieres" and "Montral" find "Montreal", while
#: keeping unrelated names out.
FUZZY_MIN_RATIO = 0.8
#: A prefix shorter than this matches too much to mean anything.
PREFIX_MIN_LENGTH = 3

_MATCH_RANK = {"exact": 3, "prefix": 2, "fuzzy": 1}

#: How many frames' cities stay in memory. One import uses one frame.
FRAME_CACHE_SIZE = 8

_build_lock = threading.Lock()


def normalize_name(name: str) -> str:
    """Accent-, case- and punctuation-insensitive form of a place name."""
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
    import geonamescache # import only in this function to not load geonamescache every time a function of this file is called

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


@dataclass(frozen=True)
class _FrameCity:
    geonameid: int
    name: str
    lat: float
    lon: float
    country: str
    population: int
    #: (normalised, shown) for the main name and every alternate one.
    names: Tuple[Tuple[str, str], ...]


def _frame_key(bounds: Dict[str, float]) -> Tuple[float, float, float, float]:
    return (
        float(bounds["west"]),
        float(bounds["south"]),
        float(bounds["east"]),
        float(bounds["north"]),
    )


def _cities_in_frame(bounds: Dict[str, float]) -> Tuple[_FrameCity, ...]:
    """Every city inside *bounds* with all of its names."""
    return _read_frame(ensure_gazetteer(), _frame_key(bounds))


@lru_cache(maxsize=FRAME_CACHE_SIZE)
def _read_frame(
    path: str, frame: Tuple[float, float, float, float]
) -> Tuple[_FrameCity, ...]:
    west, south, east, north = frame
    # A box crossing the antimeridian has west > east (frame.py accepts it).
    if west <= east:
        lon_clause, lon_args = "c.lon BETWEEN ? AND ?", (west, east)
    else:
        lon_clause, lon_args = "(c.lon >= ? OR c.lon <= ?)", (west, east)

    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
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
                "geonameid": int(city_id),
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "country": country,
                "population": int(population),
                "names": [],
            },
        )
        city["names"].append((name_norm, shown))
    return tuple(
        _FrameCity(**{**city, "names": tuple(city["names"])}) for city in cities.values()
    )


def _best_match(
    query: str, names: Tuple[Tuple[str, str], ...], matcher: difflib.SequenceMatcher
) -> Optional[tuple]:
    """(kind, score, shown name) of the best-matching name, or None."""
    best: Optional[tuple] = None
    query_len = len(query)
    for norm, shown in names:
        if norm == query:
            candidate = ("exact", 1.0, shown)
        elif query_len >= PREFIX_MIN_LENGTH and norm.startswith(query):
            candidate = ("prefix", query_len / len(norm), shown)
        else:
            # The ratio is at most 2*min/sum of the lengths: most names are
            # ruled out on length alone, the rest by the cheap upper bounds,
            # before the real (quadratic) ratio is computed.
            if 2.0 * min(query_len, len(norm)) / (query_len + len(norm)) < FUZZY_MIN_RATIO:
                continue
            matcher.set_seq1(norm)
            if (
                matcher.real_quick_ratio() < FUZZY_MIN_RATIO
                or matcher.quick_ratio() < FUZZY_MIN_RATIO
            ):
                continue
            ratio = matcher.ratio()
            if ratio < FUZZY_MIN_RATIO:
                continue
            candidate = ("fuzzy", ratio, shown)
        if best is None or (_MATCH_RANK[candidate[0]], candidate[1]) > (
            _MATCH_RANK[best[0]],
            best[1],
        ):
            best = candidate
    return best


def warm_frame(bounds: Dict[str, float]) -> None:
    """Load a frame's cities into the cache ahead of the first search."""
    try:
        _cities_in_frame(bounds)
    except Exception as e:
        logger.warning(f"[GAZETTEER] could not warm frame {bounds}: {e}")


def search_cities(
    query: str, bounds: Dict[str, float], limit: int = 10
) -> List[CityCandidate]:
    """Cities inside *bounds* whose name, or an alternate name, matches *query*."""
    normalized = normalize_name(query)
    if not normalized:
        return []

    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(normalized)

    found: List[CityCandidate] = []
    for city in _cities_in_frame(bounds):
        match = _best_match(normalized, city.names, matcher)
        if match is None:
            continue
        kind, score, shown = match
        found.append(
            CityCandidate(
                geonameid=city.geonameid,
                name=city.name,
                lat=city.lat,
                lon=city.lon,
                country=city.country,
                population=city.population,
                matched_name=shown,
                match=kind,
                score=float(score),
            )
        )

    found.sort(key=lambda c: (-_MATCH_RANK[c.match], -c.score, -c.population, c.name))
    return found[:limit]


# --------------------------------------------------------------------------
# Place names read off the map
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FrameCityIndex:
    """Exact-name lookup of the cities inside one frame, for OCR text."""

    by_name: Dict[str, _FrameCity]
    #: Longest name in words, so a phrase scan knows when to stop growing.
    max_words: int

    def lookup(self, phrase: str) -> Optional[_FrameCity]:
        return self.by_name.get(normalize_name(phrase))


def frame_city_index(bounds: Dict[str, float]) -> FrameCityIndex:
    return _frame_city_index(ensure_gazetteer(), _frame_key(bounds))


@lru_cache(maxsize=FRAME_CACHE_SIZE)
def _frame_city_index(
    path: str, frame: Tuple[float, float, float, float]
) -> FrameCityIndex:
    by_name: Dict[str, _FrameCity] = {}
    for city in _read_frame(path, frame):
        for norm, _shown in city.names:
            current = by_name.get(norm)
            if current is None or city.population > current.population:
                by_name[norm] = city
    max_words = max((len(norm.split()) for norm in by_name), default=1)
    return FrameCityIndex(by_name=by_name, max_words=max_words)


_WORD_RE = re.compile(r"[\w\-']+")


def find_cities_in_text(
    text: str, index: FrameCityIndex, max_words: int = 4
) -> List[Tuple[str, Optional[_FrameCity]]]:
    """Split one OCR label into phrases, each matched to a city or not."""
    words = _WORD_RE.findall(text or "")
    limit = max(1, min(max_words, index.max_words))
    found: List[Tuple[str, Optional[_FrameCity]]] = []
    i = 0
    while i < len(words):
        for n in range(min(limit, len(words) - i), 0, -1):
            phrase = " ".join(words[i : i + n])
            city = index.lookup(phrase)
            if city is not None:
                found.append((phrase, city))
                i += n
                break
        else:
            found.append((words[i], None))
            i += 1
    return found
