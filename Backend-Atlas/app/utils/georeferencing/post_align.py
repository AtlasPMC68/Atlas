"""Curve alignment run again after the piecewise correction.

Alignment fits six affine parameters, so it cannot move the piecewise model
itself. It fits an affine ``M`` in *pixel* space in front of it instead: the
placement becomes ``P(M(pixel))``. ``P`` is fixed during the fit, so the
reference curves and the control-point targets go through ``P``'s inverse
once, into the pixel frame ``P`` reads from, and the unchanged optimiser fits
``M`` from there, starting at the identity. An affine in front of a
piecewise-affine model is still piecewise affine on the same triangles, so
``M`` is folded back in and the result is an ordinary ``PiecewiseAffineModel``.

When there is no piecewise model (the correction was refused, or ``auto``
kept the affine), the same runs in front of the GCP affine, so a run without
an alignment before the correction is still aligned.

Not gated like the first alignment (no gates): ``M`` is kept only
when it keeps the map's orientation and does not make the coastline chamfer
worse than ``P`` alone. Everything here is cv2-free; the evidence was built
before (``runner.build_alignment_inputs``).
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence, Union

import numpy as np

from .align import (
    CurveSamples,
    UserField,
    build_curve_samples,
    build_user_field,
    chamfer_residual_px,
    sample_displacement_px,
)
from .config import GeorefConfig
from .affine import AffineModel
from .control_points import ControlPoint
from .piecewise import PiecewiseAffineModel
from .projection import lonlat_to_webmercator
from .records import RunRecord
from .gates import fit_stages

logger = logging.getLogger(__name__)

#: What can be aligned again: the piecewise model, or the GCP affine when the
#: correction was refused (or ``auto`` kept the affine).
Model = Union[AffineModel, PiecewiseAffineModel]


@dataclass(frozen=True)
class AlignmentContext:
    """The alignment evidence of one map, kept for a second alignment."""

    coast_samples: CurveSamples
    fine_samples: CurveSamples
    user_field: UserField


def build_alignment_context(
    layers: Any, evidence: Any, config: GeorefConfig
) -> AlignmentContext:
    """The same samples and field ``gates.align`` builds."""
    return AlignmentContext(
        coast_samples=build_curve_samples(
            layers, config, use_coastline=True, use_lakes=False
        ),
        fine_samples=build_curve_samples(layers, config),
        user_field=build_user_field(evidence, config),
    )


def _through(inverse: "Model", samples: CurveSamples) -> CurveSamples:
    """*samples* pushed through *inverse*, EPSG:3857 -> the pixel frame."""
    if len(samples) == 0:
        return samples
    x, y = inverse(samples.xy[:, 0], samples.xy[:, 1])
    nx, ny = inverse(samples.xy_normal[:, 0], samples.xy_normal[:, 1])
    return CurveSamples(xy=np.column_stack([x, y]), xy_normal=np.column_stack([nx, ny]))


def compose(model: Model, front: AffineModel) -> Model:
    """``model(front(pixel))`` as one model of the same kind.

    For a piecewise model, ``front`` maps each triangle onto a triangle,
    keeping barycentric coordinates, so the composite is the same
    triangulation with its input vertices pulled back through ``front`` and
    the base composed with it.
    """
    if isinstance(model, AffineModel):
        return AffineModel(matrix=model.matrix @ front.matrix, n_points=model.n_points)
    back = front.inverse()
    vx, vy = back(model.verts_in[:, 0], model.verts_in[:, 1])
    return PiecewiseAffineModel(
        base=AffineModel(matrix=model.base.matrix @ front.matrix, n_points=model.n_points),
        verts_in=np.column_stack([vx, vy]),
        verts_out=model.verts_out,
        simplices=model.simplices,
        n_points=model.n_points,
    )


def align_after_piecewise(
    model: Model,
    control_points: Sequence[ControlPoint],
    context: AlignmentContext,
    config: GeorefConfig,
    record: Optional[RunRecord] = None,
) -> Model:
    """Run the alignment stages in front of *model*; *model* if it does not help.

    *model* is the piecewise model, or the GCP affine when there is none; for
    an affine this is a plain alignment from it, without the gates. The
    returned model's GCP residuals are in-sample: a leave-one-out
    would need one alignment per fold.
    """
    record = record or RunRecord()
    stats: dict = {"applied": False, "onModel": model.name}

    if len(context.coast_samples) == 0 or not context.user_field.edge.any():
        stats["skippedBecause"] = "no coastline samples or no user edges"
        record.set_errors(postAlignment=stats)
        return model

    inverse = model.inverse()
    coast = _through(inverse, context.coast_samples)
    fine = _through(inverse, context.fine_samples)
    merc = np.array([lonlat_to_webmercator(*cp.geo) for cp in control_points], float)
    tx, ty = inverse(merc[:, 0], merc[:, 1])
    targets = np.column_stack([tx, ty])

    identity = AffineModel(matrix=np.eye(3), n_points=len(control_points))
    before = chamfer_residual_px(identity, coast, context.user_field)
    try:
        front, phase, _coarse = fit_stages(
            identity,
            control_points,
            coast,
            fine,
            context.user_field,
            config,
            gcp_targets=targets,
        )
    except Exception as e:  # the optimiser on a degenerate input; keep P
        logger.warning(f"Alignment after the piecewise correction failed: {e}")
        stats["skippedBecause"] = f"alignment raised: {e}"
        record.set_errors(postAlignment=stats)
        return model
    after = chamfer_residual_px(front, coast, context.user_field)

    stats.update(
        chamferBeforePx=before,
        chamferAfterPx=after,
        coastDisplacementPx=sample_displacement_px(identity, front, coast),
        correspondences=phase.detail.get("correspondences"),
        frontMatrix=front.matrix.tolist(),
    )
    if front.determinant <= 0:
        stats["skippedBecause"] = "the fit mirrored the map"
    elif not np.isfinite(after) or (np.isfinite(before) and after > before):
        stats["skippedBecause"] = "the coastline chamfer got worse"
    else:
        model = compose(model, front)
        model.measure_against(control_points)
        # How far the second fit pulled the map off the clicks, in pixels.
        px, py = model.inverse()(merc[:, 0], merc[:, 1])
        pixel = np.array([cp.pixel for cp in control_points], float)
        stats["applied"] = True
        stats["gcpRmsPx"] = float(
            np.sqrt(np.mean((px - pixel[:, 0]) ** 2 + (py - pixel[:, 1]) ** 2))
        )
    record.set_errors(postAlignment=stats)
    return model
