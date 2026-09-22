from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial import Delaunay

from .models import AffineModel, ControlPoint, Regularizer, control_point_weights
from .projection import lonlat_to_webmercator

#: Sources trusted enough to pin the local correction. A city control point
#: (sigma 40 px, see ``models.DEFAULT_SIGMA_PX_BY_SOURCE``) still shapes the
#: global affine, but interpolating exactly through a city that the map itself
#: places wrongly would import that error into its whole neighbourhood --
#: and old maps placing cities wrongly is the premise of the project.
DEFAULT_LOCAL_SOURCES: Tuple[str, ...] = ("sift", "manual")

#: Points located per pass. Locating is (triangles x points), so this bounds
#: peak memory on a dense geometry rather than the number of triangles.
_CHUNK = 20000

#: Barycentric coordinates of a point exactly on a shared edge come out at
#: -1e-16 on one side, which would leave the point in no triangle at all.
_BARY_EPS = 1e-7

Extent = Tuple[float, float, float, float]  # (x0, y0, x1, y1) in pixels


def _homogeneous_triangles(tri_pts: np.ndarray) -> np.ndarray:
    """(t, 3, 2) triangle corners -> (t, 3, 3) matrices with columns [x, y, 1]."""
    t = tri_pts.shape[0]
    mats = np.ones((t, 3, 3))
    mats[:, 0, :] = tri_pts[:, :, 0]
    mats[:, 1, :] = tri_pts[:, :, 1]
    return mats


def _signed_areas(verts: np.ndarray, simplices: np.ndarray) -> np.ndarray:
    p = verts[simplices]
    return 0.5 * (
        (p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1])
        - (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1])
    )


def _frame_anchors(
    src_xy: np.ndarray, extent: Optional[Extent], margin: float
) -> np.ndarray:
    """Corners and edge midpoints of a padded frame around the map.

    The anchors are where the local correction is pinned to zero, so the frame
    has to enclose everything that will be warped. Falling back to the control
    points' own bounding box is the weakest option -- that box is systematically
    too tight, because the points sit inside the mapped area -- so callers pass
    the image size, or at least the drawn features' extent.
    """
    if extent is not None:
        x0, y0, x1, y1 = (float(v) for v in extent)
    else:
        x0, y0 = src_xy.min(axis=0)
        x1, y1 = src_xy.max(axis=0)
    # A degenerate box (one point, or a single row of points) would put anchors
    # on top of each other and make the triangulation fail.
    width = max(x1 - x0, 1.0)
    height = max(y1 - y0, 1.0)
    px, py = margin * width, margin * height
    x0, x1, y0, y1 = x0 - px, x1 + px, y0 - py, y1 + py
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    return np.array(
        [[x0, y0], [xm, y0], [x1, y0], [x1, ym], [x1, y1], [xm, y1], [x0, y1], [x0, ym]]
    )


@dataclass
class PiecewiseAffineModel:
    """Pixel -> EPSG:3857 (or its inverse): affine plus per-triangle correction.

    ``verts_in`` / ``verts_out`` are the triangulation vertices in input and
    output space; ``simplices`` is shared by both, which is what makes
    ``inverse()`` exact. Outside the triangulated frame, ``base`` applies.
    """

    name = "piecewise_affine"

    base: AffineModel
    verts_in: np.ndarray
    verts_out: np.ndarray
    simplices: np.ndarray
    n_points: int = 0
    n_local_points: int = 0
    #: Leave-one-out residuals (see ``fit``), NaN where a refit was impossible.
    residuals_3857: np.ndarray = field(default_factory=lambda: np.zeros(0))
    #: Whether ``residuals_3857`` are honest (leave-one-out) or in-sample.
    residuals_are_loo: bool = False

    def __post_init__(self) -> None:
        self.verts_in = np.asarray(self.verts_in, dtype=float)
        self.verts_out = np.asarray(self.verts_out, dtype=float)
        self.simplices = np.asarray(self.simplices, dtype=int)
        s_in = _homogeneous_triangles(self.verts_in[self.simplices])
        s_out = _homogeneous_triangles(self.verts_out[self.simplices])
        # [x, y, 1] -> barycentric, then barycentric -> [X, Y, 1].
        self._bary = np.linalg.inv(s_in)
        self._tri_mats = s_out @ self._bary

    # --- fitting ------------------------------------------------------------

    @classmethod
    def fit(
        cls,
        src_xy: np.ndarray,
        dst_xy: np.ndarray,
        weights: Optional[np.ndarray] = None,
        regularizer: Optional[Regularizer] = None,
        *,
        local_mask: Optional[np.ndarray] = None,
        extent: Optional[Extent] = None,
        anchor_margin: float = 0.25,
        base: Optional[AffineModel] = None,
        leave_one_out: bool = True,
    ) -> "PiecewiseAffineModel":
        """Fit the global affine, then pin a local correction at each point.

        Args:
            src_xy: (n, 2) pixel coordinates.
            dst_xy: (n, 2) EPSG:3857 coordinates.
            weights: optional per-point weights for the global affine fit.
            regularizer: passed to the global affine fit.
            local_mask: (n,) bool; which points pin the local correction. All of
                them when omitted. Masked-out points only shape the affine.
            extent: (x0, y0, x1, y1) in pixels, where the frame anchors go.
            anchor_margin: frame padding, as a fraction of width and height.
            base: an existing affine (Step 4's aligned model, say) to correct
                instead of fitting one. It is then held fixed, including in the
                leave-one-out passes.
            leave_one_out: compute honest per-point error. Costs n refits, each
                one small least-squares solve plus a triangulation.

        Raises:
            ValueError: on mismatched inputs, duplicate control points, or a
                triangulation that folds.
        """
        src_xy = np.asarray(src_xy, dtype=float)
        dst_xy = np.asarray(dst_xy, dtype=float)
        if src_xy.shape != dst_xy.shape or src_xy.ndim != 2 or src_xy.shape[1] != 2:
            raise ValueError("src_xy and dst_xy must be matching (n, 2) arrays")

        n = src_xy.shape[0]
        mask = (
            np.ones(n, dtype=bool) if local_mask is None else np.asarray(local_mask, bool)
        )
        w = None if weights is None else np.asarray(weights, dtype=float).ravel()
        base_fixed = base is not None

        if base is None:
            base = AffineModel.fit(src_xy, dst_xy, weights=w, regularizer=regularizer)

        model = cls._build(base, src_xy, dst_xy, mask, extent, anchor_margin)
        model.n_points = n

        if leave_one_out:
            model.residuals_3857 = cls._leave_one_out(
                src_xy,
                dst_xy,
                w,
                regularizer,
                mask,
                extent,
                anchor_margin,
                base if base_fixed else None,
            )
            model.residuals_are_loo = True
        else:
            model.residuals_3857 = model._residual_distances(src_xy, dst_xy)
            model.residuals_are_loo = False
        return model

    @classmethod
    def _build(
        cls,
        base: AffineModel,
        src_xy: np.ndarray,
        dst_xy: np.ndarray,
        mask: np.ndarray,
        extent: Optional[Extent],
        anchor_margin: float,
    ) -> "PiecewiseAffineModel":
        local_src, local_dst = src_xy[mask], dst_xy[mask]
        anchors = _frame_anchors(src_xy, extent, anchor_margin)
        anchor_dst = np.column_stack(base(anchors[:, 0], anchors[:, 1]))

        verts_in = np.vstack([local_src, anchors])
        verts_out = np.vstack([local_dst, anchor_dst])

        tri = Delaunay(verts_in)
        if len(tri.coplanar):
            dup = sorted({int(i) for i in tri.coplanar[:, 0] if i < len(local_src)})
            raise ValueError(f"Duplicate control point positions (local indices {dup})")
        simplices = tri.simplices

        # A triangle whose orientation flips has folded the map over itself, so
        # the mapping is no longer one-to-one: zones would overlap, and the
        # inverse would be ambiguous. In practice it means two control points
        # swapped their relative order, which is a mis-click or a mis-match.
        area_in = _signed_areas(verts_in, simplices)
        area_out = _signed_areas(verts_out, simplices)
        folded = np.sign(area_out) != np.sign(area_in) * np.sign(base.determinant)
        if np.any(folded):
            bad = sorted({int(i) for i in simplices[folded].ravel() if i < len(local_src)})
            raise ValueError(
                "Control points fold the map (triangles flipped). Suspect local "
                f"points {bad}; check them or remove one."
            )

        return cls(
            base=base,
            verts_in=verts_in,
            verts_out=verts_out,
            simplices=simplices,
            n_local_points=int(local_src.shape[0]),
        )

    @classmethod
    def _leave_one_out(
        cls, src_xy, dst_xy, w, regularizer, mask, extent, anchor_margin, fixed_base
    ) -> np.ndarray:
        """Per-point error with that point excluded from the fit.

        NaN where the refit was impossible -- fewer than 3 points left, or
        removing the point produced a fold. Callers report those as unknown
        rather than as zero.
        """
        n = src_xy.shape[0]
        out = np.full(n, np.nan)
        for i in range(n):
            keep = np.arange(n) != i
            try:
                b = fixed_base or AffineModel.fit(
                    src_xy[keep],
                    dst_xy[keep],
                    weights=None if w is None else w[keep],
                    regularizer=regularizer,
                )
                m = cls._build(
                    b, src_xy[keep], dst_xy[keep], mask[keep], extent, anchor_margin
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            X, Y = m(src_xy[i, 0], src_xy[i, 1])
            out[i] = float(np.hypot(X - dst_xy[i, 0], Y - dst_xy[i, 1]))
        return out

    def measure_against(self, control_points: Sequence[ControlPoint]) -> None:
        """In-sample residuals, for a model that was not fitted here.

        Near zero at every point used as a vertex, so prefer the leave-one-out
        residuals ``fit`` produces when reporting error.
        """
        if not control_points:
            return
        src = np.array([cp.pixel for cp in control_points], dtype=float)
        dst = np.array(
            [
                lonlat_to_webmercator(lon, lat)
                for lon, lat in (cp.geo for cp in control_points)
            ],
            dtype=float,
        )
        self.n_points = len(control_points)
        self.residuals_3857 = self._residual_distances(src, dst)
        self.residuals_are_loo = False

    def _residual_distances(self, src_xy: np.ndarray, dst_xy: np.ndarray) -> np.ndarray:
        X, Y = self(src_xy[:, 0], src_xy[:, 1])
        return np.hypot(X - dst_xy[:, 0], Y - dst_xy[:, 1])

    # --- error reporting ----------------------------------------------------

    @property
    def redundancy(self) -> int:
        """Kept for interface parity with ``AffineModel``.

        Leave-one-out error is defined for an interpolating model, unlike an
        in-sample residual, so this does not gate ``rmse_3857`` the way the
        affine's does.
        """
        return 2 * self.n_points - self.base.dof

    @property
    def rmse_3857(self) -> Optional[float]:
        """RMS leave-one-out residual in EPSG:3857 metres, or None if unknown."""
        r = self.residuals_3857[np.isfinite(self.residuals_3857)]
        if r.size == 0:
            return None
        return float(np.sqrt(np.mean(r**2)))

    @property
    def corrections_3857(self) -> np.ndarray:
        """Per-vertex size of the local correction on top of the affine.

        Large values mark where the map is most locally distorted -- or where a
        control point is wrong. The two look identical from here.
        """
        bx, by = self.base(self.verts_in[:, 0], self.verts_in[:, 1])
        return np.hypot(self.verts_out[:, 0] - bx, self.verts_out[:, 1] - by)

    @property
    def meters_per_pixel(self) -> float:
        return self.base.meters_per_pixel

    @property
    def determinant(self) -> float:
        return self.base.determinant

    # --- applying -----------------------------------------------------------

    def _locate(self, pts: np.ndarray) -> np.ndarray:
        """Index of the triangle containing each point, or -1 outside the frame."""
        idx = np.full(pts.shape[0], -1, dtype=int)
        for start in range(0, pts.shape[0], _CHUNK):
            chunk = pts[start : start + _CHUNK]
            ph = np.vstack([chunk.T, np.ones(chunk.shape[0])])  # (3, m)
            bary = self._bary @ ph  # (t, 3, m)
            inside = np.all(bary >= -_BARY_EPS, axis=1)  # (t, m)
            idx[start : start + len(chunk)] = np.where(
                inside.any(axis=0), inside.argmax(axis=0), -1
            )
        return idx

    def __call__(self, x, y) -> Tuple[np.ndarray, np.ndarray]:
        shape = np.asarray(x).shape
        pts = np.column_stack(
            [np.asarray(x, dtype=float).ravel(), np.asarray(y, dtype=float).ravel()]
        )
        X, Y = self.base(pts[:, 0], pts[:, 1])  # what applies outside the frame
        X, Y = np.array(X, dtype=float), np.array(Y, dtype=float)

        tri = self._locate(pts)
        inside = tri >= 0
        if inside.any():
            ph = np.column_stack([pts[inside], np.ones(int(inside.sum()))])
            out = np.einsum("mij,mj->mi", self._tri_mats[tri[inside]], ph)
            X[inside], Y[inside] = out[:, 0], out[:, 1]
        return X.reshape(shape), Y.reshape(shape)

    def as_shapely_transform(self):
        """Callback for ``shapely.ops.transform``.

        Densify geometries first (``shapely.segmentize``, in pixels): only
        vertices are warped, so a long straight edge crossing several triangles
        would otherwise stay straight and cut across the correction.
        """

        def _transform(x, y, z=None):
            X, Y = self(x, y)
            return (X, Y) if z is None else (X, Y, z)

        return _transform

    def inverse(self) -> "PiecewiseAffineModel":
        """Exact inverse: same triangles, input and output swapped.

        Valid because ``_build`` rejects a folded triangulation, so the mapping
        is one-to-one.
        """
        return PiecewiseAffineModel(
            base=self.base.inverse(),
            verts_in=self.verts_out,
            verts_out=self.verts_in,
            simplices=self.simplices,
            n_points=self.n_points,
            n_local_points=self.n_local_points,
        )

    # --- serialization ------------------------------------------------------

    def serialize(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base": self.base.serialize(),
            "vertsIn": self.verts_in.tolist(),
            "vertsOut": self.verts_out.tolist(),
            "simplices": self.simplices.tolist(),
            "nPoints": int(self.n_points),
            "nLocalPoints": int(self.n_local_points),
            "rmse3857": self.rmse_3857,
            # Which number `rmse3857` is: an in-sample residual from an
            # interpolating model is 0 by construction, so a reader has to be
            # able to tell the two apart.
            "rmse3857Kind": "leave_one_out" if self.residuals_are_loo else "in_sample",
            "residuals3857": [
                None if not np.isfinite(r) else float(r) for r in self.residuals_3857
            ],
            "metersPerPixel": float(self.meters_per_pixel),
            "determinant": self.determinant,
        }

    @classmethod
    def deserialize(cls, payload: Dict[str, Any]) -> "PiecewiseAffineModel":
        if payload.get("name") != cls.name:
            raise ValueError(f"Not a piecewise-affine payload: {payload.get('name')}")
        model = cls(
            base=AffineModel.deserialize(payload["base"]),
            verts_in=np.array(payload["vertsIn"], dtype=float),
            verts_out=np.array(payload["vertsOut"], dtype=float),
            simplices=np.array(payload["simplices"], dtype=int),
            n_points=int(payload.get("nPoints", 0)),
            n_local_points=int(payload.get("nLocalPoints", 0)),
        )
        residuals = payload.get("residuals3857")
        if residuals is not None:
            model.residuals_3857 = np.array(
                [np.nan if r is None else r for r in residuals], dtype=float
            )
            model.residuals_are_loo = payload.get("rmse3857Kind") == "leave_one_out"
        return model


def fit_piecewise_from_control_points(
    control_points: Sequence[ControlPoint],
    extent: Optional[Extent] = None,
    local_sources: Sequence[str] = DEFAULT_LOCAL_SOURCES,
    use_sigma_weights: bool = False,
    regularizer: Optional[Regularizer] = None,
    base: Optional[AffineModel] = None,
    anchor_margin: float = 0.25,
) -> PiecewiseAffineModel:
    """Drop-in counterpart of ``models.fit_affine_from_control_points``."""
    if len(control_points) < 3:
        raise ValueError("At least 3 point pairs are required")
    src = np.array([cp.pixel for cp in control_points], dtype=float)
    dst = np.array(
        [
            lonlat_to_webmercator(lon, lat)
            for lon, lat in (cp.geo for cp in control_points)
        ],
        dtype=float,
    )
    weights = control_point_weights(control_points) if use_sigma_weights else None
    local_mask = np.array([cp.source in local_sources for cp in control_points])
    return PiecewiseAffineModel.fit(
        src,
        dst,
        weights=weights,
        regularizer=regularizer,
        local_mask=local_mask,
        extent=extent,
        anchor_margin=anchor_margin,
        base=base,
    )


def deserialize_model(payload: Dict[str, Any]):
    """Pick the right class from a stored payload's ``name``."""
    if payload.get("name") == PiecewiseAffineModel.name:
        return PiecewiseAffineModel.deserialize(payload)
    return AffineModel.deserialize(payload)
