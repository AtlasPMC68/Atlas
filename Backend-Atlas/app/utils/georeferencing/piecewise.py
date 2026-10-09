from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial import Delaunay

from .config import DEFAULT_GEOREF_CONFIG, GeorefConfig
from .affine import AffineModel
from .control_points import ControlPoint, control_point_weights
from .projection import lonlat_to_webmercator

#: Triangle x point pairs located per pass. Locating is (triangles x points),
#: so the points per pass shrink as the triangulation grows: the local anchors
#: can multiply the triangle count, and peak memory has to stay bounded.
_LOCATE_BUDGET = 1_500_000

#: Most local anchors per axis. Each one adds triangles every located point is
#: tested against, so a tiny radius must not turn into a dense grid.
_MAX_LOCAL_ANCHORS_PER_AXIS = 12

#: Barycentric coordinates of a point exactly on a shared edge come out at
#: -1e-16 on one side, which would leave the point in no triangle at all.
_BARY_EPS = 1e-7

#: What a model's residuals are. Only ``leave_one_out`` is an honest error for
#: an interpolating model: in-sample residuals are 0 by construction, and with
#: a fixed base the point being measured still shaped the affine underneath.
RESIDUAL_LOO = "leave_one_out"
RESIDUAL_LOO_FIXED_BASE = "leave_one_out_fixed_base"
RESIDUAL_IN_SAMPLE = "in_sample"
RESIDUAL_KINDS = (RESIDUAL_LOO, RESIDUAL_LOO_FIXED_BASE, RESIDUAL_IN_SAMPLE)

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


def _padded_frame(
    src_xy: np.ndarray, extent: Optional[Extent], margin: float
) -> Extent:
    """The box the correction lives in: *extent* padded by *margin*."""

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
    return (x0 - px, y0 - py, x1 + px, y1 + py)


def _frame_anchors(
    src_xy: np.ndarray, extent: Optional[Extent], margin: float
) -> np.ndarray:
    """Corners and edge midpoints of a padded frame around the map."""

    x0, y0, x1, y1 = _padded_frame(src_xy, extent, margin)
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    return np.array(
        [[x0, y0], [xm, y0], [x1, y0], [x1, ym], [x1, y1], [xm, y1], [x0, y1], [x0, ym]]
    )


def _local_anchors(
    src_xy: np.ndarray,
    extent: Optional[Extent],
    margin: float,
    radius_px: Optional[float],
) -> np.ndarray:
    """Extra zero-correction anchors wherever no control point is near."""

    if radius_px is None or radius_px <= 0:
        return np.zeros((0, 2))
    x0, y0, x1, y1 = _padded_frame(src_xy, extent, margin)
    nx = min(max(int(np.ceil((x1 - x0) / radius_px)), 1), _MAX_LOCAL_ANCHORS_PER_AXIS)
    ny = min(max(int(np.ceil((y1 - y0) / radius_px)), 1), _MAX_LOCAL_ANCHORS_PER_AXIS)
    xs = x0 + (np.arange(nx) + 0.5) * (x1 - x0) / nx
    ys = y0 + (np.arange(ny) + 0.5) * (y1 - y0) / ny
    grid = np.array([(x, y) for y in ys for x in xs])
    nearest = np.min(
        np.hypot(grid[:, None, 0] - src_xy[None, :, 0], grid[:, None, 1] - src_xy[None, :, 1]),
        axis=1,
    )
    return grid[nearest >= radius_px]


@dataclass
class PiecewiseAffineModel:
    """Pixel -> EPSG:3857 (or its inverse): affine plus per-triangle correction."""

    name = "piecewise_affine"

    base: AffineModel
    verts_in: np.ndarray
    verts_out: np.ndarray
    simplices: np.ndarray
    n_points: int = 0
    #: Leave-one-out residuals (see ``fit``), NaN where a refit was impossible.
    residuals_3857: np.ndarray = field(default_factory=lambda: np.zeros(0))
    #: What ``residuals_3857`` are; one of ``RESIDUAL_KINDS``.
    residuals_kind: str = RESIDUAL_IN_SAMPLE

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
        *,
        extent: Optional[Extent] = None,
        anchor_margin: float = 0.25,
        base: Optional[AffineModel] = None,
        leave_one_out: bool = True,
        influence_radius_px: Optional[float] = None,
    ) -> "PiecewiseAffineModel":
        """Fit the global affine, then pin a local correction at each point."""

        src_xy = np.asarray(src_xy, dtype=float)
        dst_xy = np.asarray(dst_xy, dtype=float)
        if src_xy.shape != dst_xy.shape or src_xy.ndim != 2 or src_xy.shape[1] != 2:
            raise ValueError("src_xy and dst_xy must be matching (n, 2) arrays")

        n = src_xy.shape[0]
        w = None if weights is None else np.asarray(weights, dtype=float).ravel()
        base_fixed = base is not None

        if base is None:
            base = AffineModel.fit(src_xy, dst_xy, weights=w)

        model = cls._build(
            base, src_xy, dst_xy, extent, anchor_margin, influence_radius_px
        )
        model.n_points = n

        if leave_one_out:
            model.residuals_3857 = cls._leave_one_out(
                src_xy,
                dst_xy,
                w,
                extent,
                anchor_margin,
                base if base_fixed else None,
                influence_radius_px,
            )
            model.residuals_kind = (
                RESIDUAL_LOO_FIXED_BASE if base_fixed else RESIDUAL_LOO
            )
        else:
            model.residuals_3857 = model._residual_distances(src_xy, dst_xy)
            model.residuals_kind = RESIDUAL_IN_SAMPLE
        return model

    @classmethod
    def _build(
        cls,
        base: AffineModel,
        src_xy: np.ndarray,
        dst_xy: np.ndarray,
        extent: Optional[Extent],
        anchor_margin: float,
        influence_radius_px: Optional[float] = None,
    ) -> "PiecewiseAffineModel":
        # Every control point pins the correction, whatever its source: SIFT
        # points and cities are trusted alike (see config.gcp_sigma_px_*).
        anchors = np.vstack(
            [
                _frame_anchors(src_xy, extent, anchor_margin),
                _local_anchors(src_xy, extent, anchor_margin, influence_radius_px),
            ]
        )
        anchor_dst = np.column_stack(base(anchors[:, 0], anchors[:, 1]))

        verts_in = np.vstack([src_xy, anchors])
        verts_out = np.vstack([dst_xy, anchor_dst])

        tri = Delaunay(verts_in)
        if len(tri.coplanar):
            dup = sorted({int(i) for i in tri.coplanar[:, 0] if i < len(src_xy)})
            raise ValueError(f"Duplicate control point positions (indices {dup})")
        simplices = tri.simplices

        # A triangle whose orientation flips has folded the map over itself, so
        # the mapping is no longer one-to-one: zones would overlap, and the
        # inverse would be ambiguous. In practice it means two control points
        # swapped their relative order, which is a mis-click or a mis-match.
        area_in = _signed_areas(verts_in, simplices)
        area_out = _signed_areas(verts_out, simplices)
        folded = np.sign(area_out) != np.sign(area_in) * np.sign(base.determinant)
        if np.any(folded):
            bad = sorted({int(i) for i in simplices[folded].ravel() if i < len(src_xy)})
            raise ValueError(
                "Control points fold the map (triangles flipped). Suspect "
                f"points {bad}; check them or remove one."
            )

        return cls(
            base=base,
            verts_in=verts_in,
            verts_out=verts_out,
            simplices=simplices,
        )

    @classmethod
    def _leave_one_out(
        cls,
        src_xy,
        dst_xy,
        w,
        extent,
        anchor_margin,
        fixed_base,
        influence_radius_px=None,
    ) -> np.ndarray:
        """Per-point error with that point excluded from the fit."""

        n = src_xy.shape[0]
        out = np.full(n, np.nan)
        for i in range(n):
            keep = np.arange(n) != i
            try:
                b = fixed_base or AffineModel.fit(
                    src_xy[keep],
                    dst_xy[keep],
                    weights=None if w is None else w[keep],
                )
                m = cls._build(
                    b,
                    src_xy[keep],
                    dst_xy[keep],
                    extent,
                    anchor_margin,
                    influence_radius_px,
                )
            except (ValueError, np.linalg.LinAlgError):
                continue
            X, Y = m(src_xy[i, 0], src_xy[i, 1])
            out[i] = float(np.hypot(X - dst_xy[i, 0], Y - dst_xy[i, 1]))
        return out

    def measure_against(self, control_points: Sequence[ControlPoint]) -> None:
        """In-sample residuals, for a model that was not fitted here."""

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
        self.residuals_kind = RESIDUAL_IN_SAMPLE

    def _residual_distances(self, src_xy: np.ndarray, dst_xy: np.ndarray) -> np.ndarray:
        X, Y = self(src_xy[:, 0], src_xy[:, 1])
        return np.hypot(X - dst_xy[:, 0], Y - dst_xy[:, 1])

    # --- error reporting ----------------------------------------------------

    @property
    def redundancy(self) -> int:
        """Kept for interface parity with ``AffineModel``."""
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
        """Per-vertex size of the local correction on top of the affine."""
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
        step = max(_LOCATE_BUDGET // max(len(self.simplices), 1), 1)
        for start in range(0, pts.shape[0], step):
            chunk = pts[start : start + step]
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
        """Callback for ``shapely.ops.transform``."""

        def _transform(x, y, z=None):
            X, Y = self(x, y)
            return (X, Y) if z is None else (X, Y, z)

        return _transform

    def inverse(self) -> "PiecewiseAffineModel":
        """Exact inverse: same triangles, input and output swapped."""
        return PiecewiseAffineModel(
            base=self.base.inverse(),
            verts_in=self.verts_out,
            verts_out=self.verts_in,
            simplices=self.simplices,
            n_points=self.n_points,
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
            "rmse3857": self.rmse_3857,
            # Which number `rmse3857` is: an in-sample residual from an
            # interpolating model is 0 by construction, and a fixed-base
            # leave-one-out is optimistic, so a reader has to tell them apart.
            "rmse3857Kind": self.residuals_kind,
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
        )
        residuals = payload.get("residuals3857")
        if residuals is not None:
            model.residuals_3857 = np.array(
                [np.nan if r is None else r for r in residuals], dtype=float
            )
            kind = payload.get("rmse3857Kind")
            if kind not in RESIDUAL_KINDS:
                raise ValueError(f"Unknown rmse3857Kind: {kind!r}")
            model.residuals_kind = kind
        return model


def fit_piecewise_from_control_points(
    control_points: Sequence[ControlPoint],
    extent: Optional[Extent] = None,
    use_sigma_weights: bool = False,
    base: Optional[AffineModel] = None,
    anchor_margin: float = 0.25,
    config: GeorefConfig = DEFAULT_GEOREF_CONFIG,
    influence_radius_px: Optional[float] = None,
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
    weights = (
        control_point_weights(control_points, config) if use_sigma_weights else None
    )
    return PiecewiseAffineModel.fit(
        src,
        dst,
        weights=weights,
        extent=extent,
        anchor_margin=anchor_margin,
        base=base,
        influence_radius_px=influence_radius_px,
    )


def deserialize_model(payload: Dict[str, Any]):
    """Pick the right class from a stored payload's ``name``."""
    if payload.get("name") == PiecewiseAffineModel.name:
        return PiecewiseAffineModel.deserialize(payload)
    return AffineModel.deserialize(payload)
