"""Georeferencing: fit a pixel -> Earth transform and apply it to features.

Package layout (plan section 3), filled in as the steps land:

    config.py       frozen hyperparameters as one versioned dataclass
    requirements.py what inputs the current algorithm needs, and which of them
                    a re-run can recover versus which need a human
    models.py       fit / apply / inverse / serialize -- one interface per model
    projection.py   EPSG:3857 maths and honest distance units
    frame.py        the user's framing box, parsed and persisted
    inputs.py       what a map was georeferenced from, stored on the map row
    snapping.py     post-hoc coastline vertex snap (due for replacement)
    piecewise.py    affine + Delaunay local correction, same model interface
    pipeline.py     fit -> snap -> clip -> EPSG:4326
    records.py      structured per-run record
    reference.py    framing box -> reference rasters + distance transform, cached
    align.py        chamfer + normal-search ICP, the distance field, Tukey
    gates.py        the named checks that decide whether alignment may ship
    recovery.py     the attempt, and the ladder it climbs down on failure
    evidence.py     user-side edge map, straight-line suppression, water mask
    runner.py       image -> gated alignment, the shared entry point
                    evidence.py and runner.py are NOT re-exported here: they are
                    the only modules needing cv2, and importing them from the
                    package would drag the image stack into every consumer.
                    Import them directly.
"""

from .config import CONFIG_VERSION, DEFAULT_GEOREF_CONFIG, GeorefConfig
from .frame import (
    FrameBounds,
    frame_bounds_from_geo_points,
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
from .piecewise import (
    PiecewiseAffineModel,
    deserialize_model,
    fit_piecewise_from_control_points,
)
from .align import (
    CurveSamples,
    PhaseResult,
    UserField,
    build_curve_samples,
    build_user_field,
    fit_chamfer,
    icp_refine,
    tukey_loss,
)
from .gates import evaluate_gates, failed_names, gates_passed, gcp_rms_px, water_mask_iou
from .pipeline import GeorefResult, georeference_features
from .recovery import AlignmentResult, align
from .reference import (
    COASTLINE_FILE,
    LAKES_FILE,
    RIVERS_FILE,
    ReferenceGrid,
    ReferenceLayers,
    build_reference_layers,
    dump_reference_debug_pngs,
    rasterize_lake_interiors,
)
from .projection import (
    mercator_scale_factor,
    reference_latitude,
    webmercator_meters_to_km,
)
from .records import GateCheck, RunRecord

__all__ = [
    "AffineModel",
    "align",
    "AlignmentResult",
    "build_curve_samples",
    "build_georef_inputs",
    "build_reference_layers",
    "build_user_field",
    "COASTLINE_FILE",
    "CONFIG_VERSION",
    "control_point_weights",
    "ControlPoint",
    "CurveSamples",
    "DEFAULT_GEOREF_CONFIG",
    "DEFAULT_SIGMA_PX_BY_SOURCE",
    "deserialize_model",
    "dump_reference_debug_pngs",
    "evaluate_gates",
    "failed_names",
    "fit_affine_from_control_points",
    "fit_chamfer",
    "fit_piecewise_from_control_points",
    "frame_bounds_from_geo_points",
    "frame_bounds_to_config_entry",
    "FrameBounds",
    "GateCheck",
    "gates_passed",
    "gcp_rms_px",
    "GEOREF_INPUTS_VERSION",
    "GeorefConfig",
    "georeference_features",
    "GeorefResult",
    "icp_refine",
    "LAKES_FILE",
    "mercator_scale_factor",
    "parse_frame_bounds",
    "parse_frame_bounds_entry",
    "parse_georef_inputs",
    "PhaseResult",
    "PiecewiseAffineModel",
    "rasterize_lake_interiors",
    "reference_latitude",
    "ReferenceGrid",
    "ReferenceLayers",
    "RIVERS_FILE",
    "RunRecord",
    "sigma_px_for_source",
    "tukey_loss",
    "UserField",
    "water_mask_iou",
    "webmercator_meters_to_km",
]
