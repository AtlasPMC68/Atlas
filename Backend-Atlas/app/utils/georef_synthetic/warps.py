"""The known deformation of a synthetic map: where the cartographer drew each place.

A warp maps world -> pixel, in three parts::

    W(lon, lat) = D( A( P(lon, lat) ) )
        P  projection     lon/lat -> plane (metres, y north)
        A  affine         plane -> pixel (x right, y down; fits the region to the image)
        D  displacements  pixel -> pixel (a smooth field, one local error)

It is applied to vectors, never to a raster, so the truth is exact. Pixel
coordinates follow OpenCV: the centre of pixel (i, j) is at (i, j).
"""

import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.utils.georeferencing.projection import R_EARTH

MERCATOR = "mercator"
EQUIRECTANGULAR = "equirectangular"
LAMBERT_CONIC = "lcc"
PROJECTIONS = (MERCATOR, EQUIRECTANGULAR, LAMBERT_CONIC)

#: How often each projection is drawn (georeferencing-synthetic.md §3.2). Mercator is the one an affine fits
#: exactly, since the pipeline fits in EPSG:3857: with no field and no local
#: error it is the easy case, ~7% of maps at these weights.
PROJECTION_WEIGHTS = {MERCATOR: 0.3, EQUIRECTANGULAR: 0.35, LAMBERT_CONIC: 0.35}

#: A conic needs its two standard parallels on the same side of the equator,
#: or its cone opens flat. Closer to the equator than this, it is not drawn.
MIN_CONIC_ABS_LAT = 11.5

ROTATION_SIGMA_DEG = 5.0
MAX_ROTATION_DEG = 15.0
MAX_SCALE_RATIO_DEVIATION = 0.1
MAX_SHEAR = 0.05

FIELD_PROBABILITY = 0.6
FIELD_GRID = 4
#: RMS displacement over the image, as a share of its diagonal.
FIELD_RMS_RATIO = (0.005, 0.03)

BUMP_PROBABILITY = 0.4
BUMP_RADIUS_RATIO = (0.05, 0.15)
BUMP_SHIFT_RATIO = (0.01, 0.04)
BUMP_SCALE = (0.1, 0.3)

#: The stress twin (georeferencing-synthetic.md §3.2): well past the other
#: twins, whose strengths were guesses and look nearly undeformed. All three
#: at once: a strong field, several local errors, and a patchwork.
STRESS_FIELD_RMS_RATIO = (0.03, 0.10)
STRESS_BUMPS = (2, 4)
STRESS_BUMP_SHIFT_RATIO = (0.04, 0.10)
STRESS_BUMP_SCALE = (0.3, 0.5)
#: The map compiled from pieces: each patch placed by its own small affine,
#: blended into the next across a seam.
PATCHES = (2, 3)
PATCH_ROTATION_DEG = (1.0, 4.0)
PATCH_SCALE = (0.02, 0.06)
PATCH_SHIFT_RATIO = (0.02, 0.06)
#: The seam's width: at least this share of the diagonal, and at least
#: ``SEAM_PER_JUMP`` times the largest shift between two patches. Narrower, two
#: patches moving towards each other fold the map where they meet: across a
#: seam of width w the displacement changes by the jump over about 2w.
SEAM_RATIO = 0.01
SEAM_PER_JUMP = 0.6
#: A seam is narrower than the default fold grid's step.
STRESS_FOLD_CHECK_GRID = 160

FOLD_CHECK_GRID = 64
NEWTON_ITERATIONS = 30
NEWTON_TOLERANCE_PX = 1e-6

LAT_LIMIT = 89.0


@dataclass(frozen=True)
class WarpOptions:
    """What a warp is drawn from, and whether the coast is drawn generalised
    (generalise.py; not a warp, but a deformation of what is drawn). The
    defaults are the generator's; tests narrow them (an undeformed map, say)."""

    projection_weights: Dict[str, float] = field(default_factory=lambda: dict(PROJECTION_WEIGHTS))
    field_probability: float = FIELD_PROBABILITY
    bump_probability: float = BUMP_PROBABILITY
    coast_generalisation: bool = True


# --------------------------------------------------------------------------
# Projections
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Projection:
    """A spherical projection centred on (lon0, lat0), in metres."""

    name: str
    lon0: float
    lat0: float
    #: Standard parallels, for the conic only.
    lat1: Optional[float] = None
    lat2: Optional[float] = None

    def __post_init__(self) -> None:
        if self.name not in PROJECTIONS:
            raise ValueError(f"Unknown projection {self.name!r}")
        if self.name == LAMBERT_CONIC and (self.lat1 is None or self.lat2 is None):
            raise ValueError("A conic needs its two standard parallels")

    def _conic_constants(self) -> Tuple[float, float, float]:
        """(n, F, rho0) of the spherical Lambert conformal conic."""
        phi1, phi2, phi0 = (math.radians(v) for v in (self.lat1, self.lat2, self.lat0))

        def t(phi: float) -> float:
            return math.tan(math.pi / 4.0 + phi / 2.0)

        if abs(phi1 - phi2) < 1e-9:
            n = math.sin(phi1)
        else:
            n = math.log(math.cos(phi1) / math.cos(phi2)) / math.log(t(phi2) / t(phi1))
        F = math.cos(phi1) * t(phi1) ** n / n
        return n, F, R_EARTH * F / t(phi0) ** n

    def forward(self, lon, lat) -> Tuple[np.ndarray, np.ndarray]:
        lam = np.radians(np.asarray(lon, dtype=float) - self.lon0)
        phi = np.radians(np.clip(np.asarray(lat, dtype=float), -LAT_LIMIT, LAT_LIMIT))
        if self.name == MERCATOR:
            return R_EARTH * lam, R_EARTH * np.log(np.tan(np.pi / 4.0 + phi / 2.0))
        if self.name == EQUIRECTANGULAR:
            # Standard parallel at the centre, so the map is not stretched there.
            return R_EARTH * lam * math.cos(math.radians(self.lat0)), R_EARTH * phi
        n, F, rho0 = self._conic_constants()
        rho = R_EARTH * F / np.tan(np.pi / 4.0 + phi / 2.0) ** n
        theta = n * lam
        return rho * np.sin(theta), rho0 - rho * np.cos(theta)

    def inverse(self, x, y) -> Tuple[np.ndarray, np.ndarray]:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if self.name == MERCATOR:
            lam = x / R_EARTH
            phi = 2.0 * np.arctan(np.exp(y / R_EARTH)) - np.pi / 2.0
        elif self.name == EQUIRECTANGULAR:
            lam = x / (R_EARTH * math.cos(math.radians(self.lat0)))
            phi = y / R_EARTH
        else:
            n, F, rho0 = self._conic_constants()
            sign = math.copysign(1.0, n)
            rho = sign * np.hypot(x, rho0 - y)
            theta = np.arctan2(sign * x, sign * (rho0 - y))
            with np.errstate(divide="ignore"):
                phi = 2.0 * np.arctan((R_EARTH * F / rho) ** (1.0 / n)) - np.pi / 2.0
            lam = theta / n
        return self.lon0 + np.degrees(lam), np.degrees(phi)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"name": self.name, "lon0": self.lon0, "lat0": self.lat0}
        if self.name == LAMBERT_CONIC:
            out.update(lat1=self.lat1, lat2=self.lat2)
        return out


# --------------------------------------------------------------------------
# Displacements (pixel -> pixel)
# --------------------------------------------------------------------------


def _gaussian(q: np.ndarray, centre: np.ndarray, radius: float) -> Tuple[np.ndarray, np.ndarray]:
    """exp(-|q - c|^2 / 2 r^2) and q - c, for points q of shape (N, 2)."""
    offset = q - centre
    return np.exp(-np.sum(offset * offset, axis=1) / (2.0 * radius * radius)), offset


@dataclass(frozen=True)
class SmoothField:
    """A sum of Gaussian kernels on a grid over the image: a smooth, low-frequency
    displacement that fades out away from the image."""

    centres: np.ndarray  # (K, 2) px
    weights: np.ndarray  # (K, 2) px
    radius: float  # px
    rms_ratio: float  # the RMS displacement over the image it was scaled to

    def displacement(self, q: np.ndarray) -> np.ndarray:
        out = np.zeros_like(q)
        for centre, weight in zip(self.centres, self.weights):
            g, _ = _gaussian(q, centre, self.radius)
            out += g[:, None] * weight
        return out

    def jacobian(self, q: np.ndarray) -> np.ndarray:
        out = np.zeros((q.shape[0], 2, 2))
        for centre, weight in zip(self.centres, self.weights):
            g, offset = _gaussian(q, centre, self.radius)
            grad = -offset * (g / (self.radius * self.radius))[:, None]  # (N, 2)
            out += weight[None, :, None] * grad[:, None, :]
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "gaussian_grid",
            "centres": self.centres.round(3).tolist(),
            "weights": self.weights.round(4).tolist(),
            "radiusPx": round(self.radius, 3),
            "rmsRatio": self.rms_ratio,
        }


@dataclass(frozen=True)
class LocalBump:
    """One region drawn in the wrong place (``shift``) or at the wrong size
    (``scale``), fading out with a Gaussian of the given radius."""

    kind: str  # "shift" | "scale"
    centre: np.ndarray  # (2,) px
    radius: float  # px
    shift: Optional[np.ndarray] = None  # (2,) px
    scale: Optional[float] = None  # 0.2 enlarges the region by 20% at its centre

    def displacement(self, q: np.ndarray) -> np.ndarray:
        g, offset = _gaussian(q, self.centre, self.radius)
        if self.kind == "shift":
            return g[:, None] * self.shift
        return (self.scale * g)[:, None] * offset

    def jacobian(self, q: np.ndarray) -> np.ndarray:
        g, offset = _gaussian(q, self.centre, self.radius)
        grad = -offset * (g / (self.radius * self.radius))[:, None]
        if self.kind == "shift":
            return self.shift[None, :, None] * grad[:, None, :]
        eye = np.broadcast_to(np.eye(2), (q.shape[0], 2, 2))
        return self.scale * (
            g[:, None, None] * eye + offset[:, :, None] * grad[:, None, :]
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "kind": self.kind,
            "centre": self.centre.round(3).tolist(),
            "radiusPx": round(self.radius, 3),
        }
        if self.kind == "shift":
            out["shiftPx"] = self.shift.round(3).tolist()
        else:
            out["scale"] = self.scale
        return out


@dataclass(frozen=True)
class Patchwork:
    """A map compiled from pieces: patch i (the region nearest ``centres[i]``)
    is displaced by its own affine, ``linear[i] @ (q - c_i) + shift[i]``, and
    the patches blend across a seam about ``seam`` px wide (a softmax of
    the distances to the centres)."""

    centres: np.ndarray  # (K, 2) px
    linear: np.ndarray  # (K, 2, 2): the patch's affine less the identity
    shift: np.ndarray  # (K, 2) px
    seam: float  # px

    def _weights(self, q: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Softmax weights (N, K), the offsets q - c_i (N, K, 2) and the
        distances (N, K)."""
        offset = q[:, None, :] - self.centres[None, :, :]
        r = np.maximum(np.linalg.norm(offset, axis=2), 1e-9)
        s = -r / self.seam
        w = np.exp(s - s.max(axis=1, keepdims=True))
        return w / w.sum(axis=1, keepdims=True), offset, r

    def _patch_displacements(self, offset: np.ndarray) -> np.ndarray:
        return np.einsum("kij,nkj->nki", self.linear, offset) + self.shift[None, :, :]

    def displacement(self, q: np.ndarray) -> np.ndarray:
        w, offset, _ = self._weights(q)
        return np.sum(w[:, :, None] * self._patch_displacements(offset), axis=1)

    def jacobian(self, q: np.ndarray) -> np.ndarray:
        w, offset, r = self._weights(q)
        grad_s = -offset / (r * self.seam)[:, :, None]  # (N, K, 2)
        grad_w = w[:, :, None] * (grad_s - np.sum(w[:, :, None] * grad_s, axis=1, keepdims=True))
        f = self._patch_displacements(offset)
        return np.einsum("nk,kij->nij", w, self.linear) + np.einsum("nki,nkj->nij", f, grad_w)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "patchwork",
            "centres": self.centres.round(3).tolist(),
            "linear": self.linear.round(5).tolist(),
            "shiftPx": self.shift.round(3).tolist(),
            "seamPx": round(self.seam, 3),
        }


# --------------------------------------------------------------------------
# The warp
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Warp:
    projection: Projection
    #: Plane -> pixel, 2x3.
    affine: np.ndarray
    image_size: Tuple[int, int]  # (width, height)
    displacements: Tuple[Any, ...] = ()
    #: What the affine's random part was, for the record.
    affine_params: Dict[str, float] = field(default_factory=dict)

    # --- forward --------------------------------------------------------

    def _plane_to_pixel(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        a = self.affine
        return np.column_stack(
            (a[0, 0] * x + a[0, 1] * y + a[0, 2], a[1, 0] * x + a[1, 1] * y + a[1, 2])
        )

    def displace(self, q: np.ndarray) -> np.ndarray:
        out = q.copy()
        for d in self.displacements:
            out += d.displacement(q)
        return out

    def displacement_jacobian(self, q: np.ndarray) -> np.ndarray:
        """The Jacobian of D at pixel points q (N, 2): shape (N, 2, 2)."""
        out = np.broadcast_to(np.eye(2), (q.shape[0], 2, 2)).copy()
        for d in self.displacements:
            out += d.jacobian(q)
        return out

    def forward(self, lon, lat) -> Tuple[np.ndarray, np.ndarray]:
        """lon/lat -> pixel."""
        lon = np.asarray(lon, dtype=float)
        shape = lon.shape
        x, y = self.projection.forward(lon.ravel(), np.asarray(lat, dtype=float).ravel())
        q = self.displace(self._plane_to_pixel(x, y))
        return q[:, 0].reshape(shape), q[:, 1].reshape(shape)

    def forward_xy(self, xy: np.ndarray) -> np.ndarray:
        """(N, 2) lon/lat -> (N, 2) pixel, the callback ``shapely.transform`` wants."""
        px, py = self.forward(xy[:, 0], xy[:, 1])
        return np.column_stack((px, py))

    # --- inverse --------------------------------------------------------

    def undisplace(self, p: np.ndarray) -> np.ndarray:
        """Solve q + d(q) = p by Newton iteration; NaN where it did not converge."""
        if not self.displacements:
            return p.copy()
        q = p - (self.displace(p) - p)
        for _ in range(NEWTON_ITERATIONS):
            residual = self.displace(q) - p
            if np.all(np.abs(residual) < NEWTON_TOLERANCE_PX):
                break
            q = q - np.linalg.solve(self.displacement_jacobian(q), residual[:, :, None])[:, :, 0]
        bad = np.any(np.abs(self.displace(q) - p) > 1e-3, axis=1)
        q[bad] = np.nan
        return q

    def inverse(self, px, py) -> Tuple[np.ndarray, np.ndarray]:
        """pixel -> lon/lat. NaN where the inversion failed."""
        px = np.asarray(px, dtype=float)
        shape = px.shape
        p = np.column_stack((px.ravel(), np.asarray(py, dtype=float).ravel()))
        q = self.undisplace(p)
        a = np.vstack((self.affine, (0.0, 0.0, 1.0)))
        plane = np.linalg.solve(a, np.vstack((q.T, np.ones(q.shape[0]))))
        lon, lat = self.projection.inverse(plane[0], plane[1])
        return lon.reshape(shape), lat.reshape(shape)

    # --- checks ---------------------------------------------------------

    def min_jacobian_determinant(self, grid: int = FOLD_CHECK_GRID) -> float:
        """The smallest det of D's Jacobian over the image. <= 0 means a fold."""
        if not self.displacements:
            return 1.0
        w, h = self.image_size
        xs, ys = np.meshgrid(np.linspace(0, w, grid), np.linspace(0, h, grid))
        jac = self.displacement_jacobian(np.column_stack((xs.ravel(), ys.ravel())))
        return float(np.min(np.linalg.det(jac)))

    def displacement_affine_fit(self, grid: int = 32) -> np.ndarray:
        """The best affine fit of the displacement over the image, (3, 2):
        ``d(q) ~ [q, 1] @ coef``. The part any affine fit takes out."""
        w, h = self.image_size
        xs, ys = np.meshgrid(np.linspace(0, w, grid), np.linspace(0, h, grid))
        q = np.column_stack((xs.ravel(), ys.ravel()))
        design = np.column_stack((q, np.ones(len(q))))
        coef, *_ = np.linalg.lstsq(design, self.displace(q) - q, rcond=None)
        return coef

    def non_affine_rms_px(self, grid: int = 32) -> float:
        """The RMS over the image of the displacement less its best affine
        fit: what no affine can take out, so what the twins differ by."""
        if not self.displacements:
            return 0.0
        w, h = self.image_size
        xs, ys = np.meshgrid(np.linspace(0, w, grid), np.linspace(0, h, grid))
        q = np.column_stack((xs.ravel(), ys.ravel()))
        residual = self.displace(q) - q - np.column_stack((q, np.ones(len(q)))) @ self.displacement_affine_fit(grid)
        return float(np.sqrt(np.mean(np.sum(residual * residual, axis=1))))

    @property
    def families(self) -> List[str]:
        out = [self.projection.name, "affine"]
        for d in self.displacements:
            if isinstance(d, SmoothField):
                out.append("field")
            elif isinstance(d, Patchwork):
                out.append("patchwork")
            else:
                out.append(f"local_{d.kind}")
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "families": self.families,
            "projection": self.projection.to_dict(),
            "affine": np.asarray(self.affine).tolist(),
            "affineParams": self.affine_params,
            "displacements": [d.to_dict() for d in self.displacements],
        }


# --------------------------------------------------------------------------
# Drawing a warp
# --------------------------------------------------------------------------


def draw_projection(
    rng: np.random.Generator,
    lon0: float,
    lat0: float,
    lat_span: float,
    weights_by_name: Dict[str, float] = PROJECTION_WEIGHTS,
) -> Projection:
    """A projection centred on the region; the conic only away from the equator."""
    names = list(PROJECTIONS)
    weights = np.array([weights_by_name.get(n, 0.0) for n in names], dtype=float)
    if abs(lat0) < MIN_CONIC_ABS_LAT:
        weights[names.index(LAMBERT_CONIC)] = 0.0
    name = names[int(rng.choice(len(names), p=weights / weights.sum()))]
    if name != LAMBERT_CONIC:
        return Projection(name, lon0, lat0)
    # Standard parallels at 1/6 and 5/6 of the latitude span, kept on the
    # region's side of the equator.
    south, north = lat0 - lat_span / 2.0, lat0 + lat_span / 2.0
    lat1 = south + lat_span / 6.0
    lat2 = north - lat_span / 6.0
    if lat0 > 0:
        lat1 = max(lat1, 1.0)
    else:
        lat2 = min(lat2, -1.0)
    return Projection(name, lon0, lat0, lat1, lat2)


def fit_affine(
    projection: Projection,
    centre: Tuple[float, float],
    plane_width: float,
    image_size: Tuple[int, int],
    rng: np.random.Generator,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Plane -> pixel: the region of the given plane width, centred on *centre*,
    fills the image; then a random rotation, scale ratio and shear about the
    image centre."""
    w, h = image_size
    cx, cy = (float(v) for v in projection.forward(*centre))
    s = w / plane_width
    # Fit: pixel = (w/2 + s (x - cx), h/2 - s (y - cy)).
    base = np.array([[s, 0.0, w / 2.0 - s * cx], [0.0, -s, h / 2.0 + s * cy]])

    rotation = float(np.clip(rng.normal(0.0, ROTATION_SIGMA_DEG), -MAX_ROTATION_DEG, MAX_ROTATION_DEG))
    ratio = 1.0 + float(rng.uniform(-MAX_SCALE_RATIO_DEVIATION, MAX_SCALE_RATIO_DEVIATION))
    shear = float(rng.uniform(-MAX_SHEAR, MAX_SHEAR))
    t = math.radians(rotation)
    rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    linear = rot @ np.array([[1.0, shear], [0.0, 1.0]]) @ np.diag([math.sqrt(ratio), 1.0 / math.sqrt(ratio)])

    c = np.array([w / 2.0, h / 2.0])
    affine = np.empty((2, 3))
    affine[:, :2] = linear @ base[:, :2]
    affine[:, 2] = linear @ (base[:, 2] - c) + c
    return affine, {"rotationDeg": rotation, "scaleRatio": ratio, "shear": shear}


def draw_field(
    rng: np.random.Generator, image_size: Tuple[int, int], rms_range: Tuple[float, float] = FIELD_RMS_RATIO
) -> SmoothField:
    w, h = image_size
    xs, ys = np.meshgrid(np.linspace(0, w, FIELD_GRID), np.linspace(0, h, FIELD_GRID))
    centres = np.column_stack((xs.ravel(), ys.ravel()))
    radius = float(np.hypot(w, h)) / (FIELD_GRID - 1) / math.sqrt(2.0)
    weights = rng.normal(0.0, 1.0, size=centres.shape)
    rms_ratio = float(rng.uniform(*rms_range))

    unit = SmoothField(centres, weights, radius, rms_ratio)
    gx, gy = np.meshgrid(np.linspace(0, w, 32), np.linspace(0, h, 32))
    d = unit.displacement(np.column_stack((gx.ravel(), gy.ravel())))
    rms = float(np.sqrt(np.mean(np.sum(d * d, axis=1))))
    target = rms_ratio * float(np.hypot(w, h))
    return SmoothField(centres, weights * (target / rms), radius, rms_ratio)


def draw_bump(
    rng: np.random.Generator,
    image_size: Tuple[int, int],
    centre: np.ndarray,
    shift_range: Tuple[float, float] = BUMP_SHIFT_RATIO,
    scale_range: Tuple[float, float] = BUMP_SCALE,
) -> LocalBump:
    diagonal = float(np.hypot(*image_size))
    radius = float(rng.uniform(*BUMP_RADIUS_RATIO)) * diagonal
    if rng.random() < 0.5:
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        length = float(rng.uniform(*shift_range)) * diagonal
        shift = length * np.array([math.cos(angle), math.sin(angle)])
        return LocalBump("shift", np.asarray(centre, dtype=float), radius, shift=shift)
    scale = float(rng.uniform(*scale_range)) * (1.0 if rng.random() < 0.5 else -1.0)
    return LocalBump("scale", np.asarray(centre, dtype=float), radius, scale=scale)


def draw_patchwork(
    rng: np.random.Generator, image_size: Tuple[int, int], seam_ratio: float = SEAM_RATIO, strength: float = 1.0
) -> Patchwork:
    """2-3 patches, each displaced by its own affine times *strength*."""
    w, h = image_size
    diagonal = float(np.hypot(w, h))
    k = int(rng.integers(PATCHES[0], PATCHES[1] + 1))
    # Centres in the middle 60% of the image, so every patch shows.
    centres = np.column_stack((rng.uniform(0.2 * w, 0.8 * w, k), rng.uniform(0.2 * h, 0.8 * h, k)))
    linear, shift = np.empty((k, 2, 2)), np.empty((k, 2))
    for i in range(k):
        t = math.radians(float(rng.uniform(*PATCH_ROTATION_DEG)) * (1.0 if rng.random() < 0.5 else -1.0))
        s = 1.0 + float(rng.uniform(*PATCH_SCALE)) * (1.0 if rng.random() < 0.5 else -1.0)
        linear[i] = s * np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]]) - np.eye(2)
        angle = float(rng.uniform(0.0, 2.0 * math.pi))
        shift[i] = float(rng.uniform(*PATCH_SHIFT_RATIO)) * diagonal * np.array([math.cos(angle), math.sin(angle)])
    linear, shift = linear * strength, shift * strength
    jump = max(float(np.linalg.norm(a - b)) for a in shift for b in shift)
    return Patchwork(centres, linear, shift, max(seam_ratio * diagonal, SEAM_PER_JUMP * jump))


def draw_stress(
    rng: np.random.Generator, image_size: Tuple[int, int], bump_centres: List[np.ndarray], strength: float, seam_ratio: float
) -> Tuple[Any, ...]:
    """The stress twin's displacements, every magnitude times *strength*: a
    strong field, a local error at each of *bump_centres*, a patchwork."""
    field = draw_field(rng, image_size, STRESS_FIELD_RMS_RATIO)
    bumps = [draw_bump(rng, image_size, c, STRESS_BUMP_SHIFT_RATIO, STRESS_BUMP_SCALE) for c in bump_centres]
    patchwork = draw_patchwork(rng, image_size, seam_ratio, strength)
    return (
        replace(field, weights=field.weights * strength, rms_ratio=field.rms_ratio * strength),
        *(
            replace(b, shift=b.shift * strength) if b.kind == "shift" else replace(b, scale=b.scale * strength)
            for b in bumps
        ),
        patchwork,
    )
