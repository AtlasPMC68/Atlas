"""Georeferencing: fit a pixel -> Earth transform and apply it to features.

Package layout (plan section 3), filled in as the steps land:

    config.py       frozen hyperparameters as one versioned dataclass
    models.py       fit / apply / inverse / serialize -- one interface per model
    projection.py   EPSG:3857 maths and honest distance units
    frame.py        the user's framing box, parsed and persisted
    inputs.py       what a map was georeferenced from, stored on the map row
    snapping.py     post-hoc coastline vertex snap (due for replacement)
    pipeline.py     fit -> snap -> clip -> EPSG:4326
    records.py      structured per-run record
    reference.py    (Step 2) framing box -> reference rasters + distance transform
    evidence.py     (Step 3) user-side edge map, water mask
    align.py        (Step 4) coarse alignment, gates
"""

from .config import CONFIG_VERSION, DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import (
    FrameBounds,
    frame_bounds_to_config_entry,
    parse_frame_bounds,
    parse_frame_bounds_entry,
)
from .inputs import (
    GEOREF_INPUTS_VERSION,
    build_georef_inputs,
    parse_georef_inputs,
)
from .models import (
    DEFAULT_SIGMA_PX_BY_SOURCE,
    AffineModel,
    ControlPoint,
    control_point_weights,
    fit_affine_from_control_points,
    sigma_px_for_source,
)
from .pipeline import GeorefResult, georeference_features
from .projection import (
    mercator_scale_factor,
    reference_latitude,
    webmercator_meters_to_km,
)
from .records import GateCheck, RunRecord

__all__ = [
    "AffineModel",
    "build_georef_inputs",
    "CONFIG_VERSION",
    "control_point_weights",
    "ControlPoint",
    "DEFAULT_GEOREF_CONFIG",
    "DEFAULT_SIGMA_PX_BY_SOURCE",
    "fit_affine_from_control_points",
    "frame_bounds_to_config_entry",
    "FrameBounds",
    "GateCheck",
    "GEOREF_INPUTS_VERSION",
    "GeorefConfig",
    "georeference_features",
    "GeorefResult",
    "mercator_scale_factor",
    "parse_frame_bounds",
    "parse_frame_bounds_entry",
    "parse_georef_inputs",
    "reference_latitude",
    "RunRecord",
    "sigma_px_for_source",
    "webmercator_meters_to_km",
]
