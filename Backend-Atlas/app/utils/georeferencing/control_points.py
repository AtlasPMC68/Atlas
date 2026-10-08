"""Control points: one pixel <-> lon/lat pair each, and where it came from.

The records every stage passes around (``ControlPoint``, ``CityRef``), their
one wire format, and the per-source helpers: selecting a subset of sources,
counting them, and the ``1/sigma^2`` weights a weighted fit uses.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .config import (
    DEFAULT_GEOREF_CONFIG,
    GCP_SOURCES,
    SOURCE_CITY,
    SOURCE_SIFT,
    GeorefConfig,
)
from .projection import LonLat, XY


@dataclass(frozen=True)
class CityRef:
    """The gazetteer city a control point was matched to.

    ``geonameid`` is the GeoNames id, stable across GeoNames-derived datasets,
    which is what tells two spellings of one city ("Quebec", "Kebek") apart
    from two different cities. ``name`` is the gazetteer's name, so run records
    and overlays say which city a residual belongs to.
    """

    geonameid: int
    name: str

    def __post_init__(self) -> None:
        if isinstance(self.geonameid, bool) or not isinstance(self.geonameid, int):
            raise ValueError(f"city id must be an integer, got {self.geonameid!r}")
        if self.geonameid <= 0:
            raise ValueError(f"city id must be positive, got {self.geonameid}")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("city name must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.geonameid, "name": self.name}


@dataclass(frozen=True)
class ControlPoint:
    """One pixel <-> geo pair, and where it came from.

    A discriminated union on ``source``: a ``city`` point always carries its
    ``CityRef`` and a ``sift`` point never has one. Enforced at construction,
    so no consumer ever handles a city without a name or a keypoint with one.

    Positional uncertainty is deliberately *not* stored here. It is a model
    setting, looked up from ``GeorefConfig`` by source when fitting
    (``gcp_sigma_px``), so it can change without rewriting stored clicks.
    """

    pixel: XY
    geo: LonLat
    source: str
    city: Optional[CityRef] = None

    def __post_init__(self) -> None:
        if self.source not in GCP_SOURCES:
            raise ValueError(
                f"Unknown control point source {self.source!r};"
                f" expected one of {list(GCP_SOURCES)}"
            )
        if self.source == SOURCE_CITY and not isinstance(self.city, CityRef):
            raise ValueError("A city control point needs the city it was matched to")
        if self.source != SOURCE_CITY and self.city is not None:
            raise ValueError(f"A {self.source} control point cannot carry a city")

        pixel = _finite_pair(self.pixel, "pixel")
        lon, lat = _finite_pair(self.geo, "geo")
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise ValueError(f"geo out of range: lon={lon}, lat={lat}")
        # Frozen, so normalise to plain float tuples through object.__setattr__.
        object.__setattr__(self, "pixel", pixel)
        object.__setattr__(self, "geo", (lon, lat))

    @classmethod
    def sift(cls, pixel: Sequence[float], geo: Sequence[float]) -> "ControlPoint":
        """A coastline keypoint the user matched on their map. ``geo`` is (lon, lat)."""
        return cls(pixel=pixel, geo=geo, source=SOURCE_SIFT)

    @classmethod
    def from_city(
        cls,
        pixel: Sequence[float],
        geo: Sequence[float],
        geonameid: int,
        name: str,
    ) -> "ControlPoint":
        """A gazetteer city the user located on their map. ``geo`` is (lon, lat)."""
        return cls(
            pixel=pixel,
            geo=geo,
            source=SOURCE_CITY,
            city=CityRef(geonameid=geonameid, name=name),
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "source": self.source,
            "pixel": {"x": self.pixel[0], "y": self.pixel[1]},
            "geo": {"lon": self.geo[0], "lat": self.geo[1]},
        }
        if self.city is not None:
            payload["city"] = self.city.to_dict()
        return payload

    @classmethod
    def from_dict(cls, entry: Any) -> "ControlPoint":
        """Inverse of ``to_dict``. Strict: raises ValueError on anything else.

        The one wire format for control points: the upload routes, the Celery
        task arguments, dev-test ``config.json`` and ``maps.georef_inputs``.
        """
        if not isinstance(entry, dict):
            raise ValueError(f"control point must be an object, got {entry!r}")
        pixel = entry.get("pixel")
        geo = entry.get("geo")
        if not isinstance(pixel, dict) or not isinstance(geo, dict):
            raise ValueError("control point needs 'pixel' {x, y} and 'geo' {lon, lat}")
        try:
            xy = (pixel["x"], pixel["y"])
            lonlat = (geo["lon"], geo["lat"])
        except KeyError as e:
            raise ValueError(f"control point is missing {e}")

        city = entry.get("city")
        city_ref = None
        if city is not None:
            if not isinstance(city, dict) or "id" not in city or "name" not in city:
                raise ValueError("control point 'city' must be {id, name}")
            city_ref = CityRef(geonameid=city["id"], name=city["name"])

        return cls(pixel=xy, geo=lonlat, source=entry.get("source"), city=city_ref)


def _finite_pair(value: Any, label: str) -> Tuple[float, float]:
    try:
        a, b = value
        pair = (_as_float(a), _as_float(b))
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be two numbers, got {value!r}")
    if not all(math.isfinite(v) for v in pair):
        raise ValueError(f"{label} must be finite, got {value!r}")
    return pair


def _as_float(value: Any) -> float:
    # bool is an int subclass; a True coordinate is always a caller bug.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"not a number: {value!r}")
    return float(value)


def parse_control_points(entries: Any) -> List[ControlPoint]:
    """A JSON list of control points, as ``ControlPoint.to_dict`` writes them.

    Raises:
        ValueError: naming the offending index, on anything malformed.
    """
    if not isinstance(entries, list):
        raise ValueError("control points must be a JSON array")
    points: List[ControlPoint] = []
    for i, entry in enumerate(entries):
        try:
            points.append(ControlPoint.from_dict(entry))
        except ValueError as e:
            raise ValueError(f"control point {i}: {e}")
    return points


def select_control_points(
    control_points: Sequence[ControlPoint], sources: Sequence[str]
) -> List[ControlPoint]:
    """The points whose source is in *sources*, in their original order."""
    wanted = set(sources)
    return [cp for cp in control_points if cp.source in wanted]


def count_by_source(control_points: Sequence[ControlPoint]) -> Dict[str, int]:
    """Point count per known source, zeros included, for records and the UI."""
    counts = {source: 0 for source in GCP_SOURCES}
    for cp in control_points:
        counts[cp.source] += 1
    return counts


def gcp_sigma_px(source: str, config: GeorefConfig = DEFAULT_GEOREF_CONFIG) -> float:
    """Expected positional error, in image pixels, of a point from *source*."""
    if source == SOURCE_CITY:
        return float(config.gcp_sigma_px_city)
    return float(config.gcp_sigma_px_sift)


def control_point_weights(
    control_points: Sequence[ControlPoint],
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
) -> np.ndarray:
    """``1/sigma^2`` weights, sigma looked up per source from *config*."""
    sigmas = np.array(
        [max(gcp_sigma_px(cp.source, config), 1e-6) for cp in control_points],
        dtype=float,
    )
    return 1.0 / (sigmas**2)
