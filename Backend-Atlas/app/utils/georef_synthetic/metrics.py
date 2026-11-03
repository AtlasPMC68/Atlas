"""The true placement error of a run (georeferencing-synthetic.md §3.5), and the real corpus's zone metrics."""

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np
import shapely
from shapely.geometry import mapping

from app.utils.dev_test_evaluator import evaluate_case_zones
from app.utils.georeferencing.cleaning import clean_expected_zones
from app.utils.georeferencing.projection import lonlat_arrays_to_webmercator
from app.utils.georeferencing.reference import COASTLINE_FILE, load_reference_linework

from .case import SyntheticMap

DENSE_SAMPLES = 20_000
#: Samples within this distance of the coastline are coastal, the split of
#: georeferencing-testing.md §8.2.
COASTAL_KM = 50.0
#: Margin around the visible region when clipping the coastline for distances:
#: beyond COASTAL_KM, so a sample's nearest coast is never cut off.
COAST_CLIP_MARGIN_DEG = 1.0


@dataclass(frozen=True)
class DenseSamples:
    """Points uniform on the ground inside a map's true zones. Drawn once per
    map, so every layout and variant of it is measured on the same points."""

    lon: np.ndarray
    lat: np.ndarray
    x_3857: np.ndarray
    y_3857: np.ndarray
    #: Where the map draws each point.
    px: np.ndarray
    py: np.ndarray
    coastal: np.ndarray  # bool

    def subset(self, count: int) -> "DenseSamples":
        """The first *count* samples: uniform too, since they were drawn in
        random order, and the same ones for every layout and variant."""
        return DenseSamples(*(getattr(self, f)[:count] for f in self.__dataclass_fields__))


def dense_samples(synthetic: SyntheticMap, count: int = DENSE_SAMPLES) -> DenseSamples:
    """Uniform on the sphere (longitude uniform, sin(latitude) uniform), kept
    inside the zones, from the map's own seed."""
    rng = np.random.default_rng(np.random.SeedSequence([synthetic.seed], spawn_key=(1,)))
    zones = shapely.union_all([z.geometry for z in synthetic.zones])
    shapely.prepare(zones)
    west, south, east, north = zones.bounds
    s0, s1 = math.sin(math.radians(south)), math.sin(math.radians(north))

    lons, lats = [], []
    kept = 0
    while kept < count:
        n = max(4 * (count - kept), 1000)
        lon = rng.uniform(west, east, n)
        lat = np.degrees(np.arcsin(rng.uniform(s0, s1, n)))
        inside = shapely.contains_xy(zones, lon, lat)
        lons.append(lon[inside])
        lats.append(lat[inside])
        kept += int(inside.sum())
    lon = np.concatenate(lons)[:count]
    lat = np.concatenate(lats)[:count]

    x, y = lonlat_arrays_to_webmercator(lon, lat)
    px, py = synthetic.warp.forward(lon, lat)

    vw, vs, ve, vn = synthetic.visible.bounds
    m = COAST_CLIP_MARGIN_DEG
    coast = shapely.clip_by_rect(load_reference_linework(COASTLINE_FILE), vw - m, vs - m, ve + m, vn + m)
    if coast.is_empty:
        coastal = np.zeros(lon.shape, dtype=bool)
    else:
        coast_3857 = shapely.transform(coast, lambda xy: np.column_stack(lonlat_arrays_to_webmercator(xy[:, 0], xy[:, 1])))
        distance_km = shapely.distance(coast_3857, shapely.points(x, y)) * np.cos(np.radians(lat)) / 1000.0
        coastal = distance_km <= COASTAL_KM
    return DenseSamples(lon, lat, x, y, px, py, coastal)


def ground_km(model: Any, samples: DenseSamples) -> np.ndarray:
    """How far *model* puts each sample's pixel from the sample, in ground km
    (the Mercator scale taken at the sample's own latitude)."""
    x, y = model(samples.px, samples.py)
    return np.hypot(np.asarray(x) - samples.x_3857, np.asarray(y) - samples.y_3857) * np.cos(
        np.radians(samples.lat)
    ) / 1000.0


def _mean(values: np.ndarray) -> Optional[float]:
    return round(float(values.mean()), 4) if values.size else None


def dense_error(model: Any, baseline: Any, samples: DenseSamples) -> Dict[str, Any]:
    error = ground_km(model, samples)
    return {
        "denseMeanKm": _mean(error),
        "denseMedianKm": round(float(np.median(error)), 4),
        "denseP90Km": round(float(np.percentile(error, 90)), 4),
        "denseMaxKm": round(float(error.max()), 4),
        "denseCoastalMeanKm": _mean(error[samples.coastal]),
        "denseInlandMeanKm": _mean(error[~samples.coastal]),
        "denseCoastalShare": round(float(samples.coastal.mean()), 4),
        "denseMeanKmGcpAffine": _mean(ground_km(baseline, samples)),
    }


def zone_metrics(
    synthetic: SyntheticMap,
    case_id: str,
    raw_zones: Dict[str, Any],
    zones: Dict[str, Any],
    unsnapped_zones: Optional[Dict[str, Any]] = None,
    snapped_zones: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """IoU and boundary distance, as the real corpus scores them: ``raw`` the
    zones as the transform placed them against the true zones; without a
    prefix the shipped zones as the variant's config cleans them; ``unsnapped``
    and ``snapped`` the same transform's zones cleaned without and with
    snapping, whatever the config, against the true zones put through the same
    cleaning (§10.6)."""
    expected = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"name": z.name}, "geometry": mapping(z.geometry)}
            for z in synthetic.zones
        ],
    }
    report, _errors, _raw_errors = evaluate_case_zones(
        test_id=synthetic.map_id,
        test_case_id=case_id,
        drawn_expected=expected,
        cleaned_expected=clean_expected_zones(expected),
        zones=zones,
        raw_zones=raw_zones,
        unsnapped_zones=unsnapped_zones,
        snapped_zones=snapped_zones,
    )
    raw, shipped = report["raw"]["metrics"]["mean"], report["metrics"]["mean"]
    both = {}
    for key in ("unsnapped", "snapped"):
        mean = ((report.get(key) or {}).get("metrics") or {}).get("mean") or {}
        both.update({
            f"{key}MeanIou": round(mean["meanIou"], 5) if mean else None,
            f"{key}MeanBoundaryKm": mean.get("meanBoundaryKm"),
            f"{key}MeanBoundaryP90Km": mean.get("meanBoundaryP90Km"),
        })
    return {
        **both,
        "rawMeanIou": round(raw["meanIou"], 5),
        "rawMeanBoundaryKm": raw["meanBoundaryKm"],
        "rawMeanBoundaryP90Km": raw["meanBoundaryP90Km"],
        "rawMaxBoundaryKm": raw["maxBoundaryKm"],
        "meanIou": round(shipped["meanIou"], 5),
        "meanBoundaryKm": shipped["meanBoundaryKm"],
        "meanBoundaryP90Km": shipped["meanBoundaryP90Km"],
        "maxBoundaryKm": shipped["maxBoundaryKm"],
    }
