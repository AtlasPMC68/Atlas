"""Seed -> synthetic map."""

from dataclasses import dataclass, replace
from typing import Dict, Optional, Sequence

import numpy as np
import shapely
from shapely.geometry import Polygon

from .case import SyntheticCase, SyntheticMap
from .generalise import Generalisation, draw_generalisation, drawn_feature_pixels, drawn_zone_geometries
from .regions import (
    RegionDraw,
    Rejected,
    UnitSource,
    border_units,
    choose_zones,
    draw_region,
    frame_bounds,
    land_layers,
    visible_region,
)
from .render import (
    RenderStyle,
    assign_colours,
    coast_signals,
    draw_style,
    drawn_layers,
    render_map,
)
from .user import (
    FAMILY_OPEN,
    FAMILY_PROTOCOL,
    LayoutOptions,
    city_candidates,
    draw_check_points,
    draw_layout,
    sift_candidates,
    water_pick,
)
from .warps import (
    LocalBump,
    Projection,
    SmoothField,
    Warp,
    WarpOptions,
    STRESS_BUMPS,
    STRESS_FOLD_CHECK_GRID,
    SEAM_RATIO,
    draw_bump,
    draw_field,
    draw_projection,
    draw_stress,
    fit_affine,
)

#: Bump whenever the same seed would produce a different case. Results from two
#: versions are never compared.
GENERATOR_VERSION = "11"

#: The twins of a map (georeferencing-synthetic.md §3.2): the same
#: map with no displacement, with its smooth field only, with its local error
#: only; and the stress twin, far stronger than the others (a strong field,
#: several local errors and a patchwork at once), drawn from a stream of its
#: own so the other three are the same with or without it.
DEFORMATIONS = ("none", "field", "local", "stress")
#: The twins the framing box is drawn around: the stress twin uses theirs.
_FRAMED = ("none", "field", "local")

#: A stress draw that folds or shows no usable map is redrawn this much
#: weaker, its seam this much wider, rather than rejecting the map (which
#: would change the other twins).
STRESS_SOFTENING = 0.85
STRESS_ATTEMPTS = 25

MAX_ATTEMPTS = 50
BUMP_CENTRE_TRIES = 50

#: The per-map draws made from the shared fork (``_Shared.rng``).
_FRAME, _COLOURS, _STRESS = 0, 1, 2
#: A layout's check points, from a stream of their own: they changed no
#: control point when added, so no input of a run, and the version stayed.
_CHECKS = 0
#: A layout's family (``user.FAMILY_*``), from a stream of its own too: an
#: open layout makes the draws it made before protocol layouts existed.
_FAMILY = 1


def map_id(map_seed: int, deformation: Optional[str] = None) -> str:
    """``m00042`` as drawn, ``m00042-field`` for a twin."""
    return f"m{map_seed:05d}" + (f"-{deformation}" if deformation else "")


def _land_pixel(rng: np.random.Generator, warp: Warp) -> Optional[np.ndarray]:
    """A pixel uniform in the image that shows land, or None."""
    land = land_layers().land
    w, h = warp.image_size
    for _ in range(BUMP_CENTRE_TRIES):
        p = np.array([rng.uniform(0, w), rng.uniform(0, h)])
        lon, lat = warp.inverse(p[:1], p[1:])
        if np.isfinite(lon[0]) and shapely.contains_xy(land, lon[0], lat[0]):
            return p
    return None


@dataclass(frozen=True)
class _Shared:
    """What a map's twins have in common: every draw that does not depend on
    the displacement. The field and the local error are always drawn, and the
    coins say whether the map as drawn applies them, so the stream is the same
    whatever is applied."""

    region: RegionDraw
    projection: Projection
    affine: np.ndarray
    affine_params: Dict[str, float]
    field: SmoothField
    bump: LocalBump
    apply_field: bool
    apply_bump: bool
    #: How the coast is drawn; None when the options turn it off.
    generalisation: Optional[Generalisation]
    style: RenderStyle
    #: Seeds the draws that depend on the warp (frame, colours), so twins make
    #: the same ones.
    fork: int

    def warp(self, deformation: Optional[str]) -> Warp:
        """The warp of a twin, or of the map as drawn (None)."""
        field, bump = {
            None: (self.apply_field, self.apply_bump),
            "none": (False, False),
            "field": (True, False),
            "local": (False, True),
        }[deformation]
        displacements = ((self.field,) if field else ()) + ((self.bump,) if bump else ())
        warp = Warp(self.projection, self.affine, self.region.image_size, displacements, self.affine_params)
        if displacements and warp.min_jacobian_determinant() <= 0.0:
            raise Rejected("warp folds")
        return warp

    def rng(self, purpose: int) -> np.random.Generator:
        return np.random.default_rng(np.random.SeedSequence([self.fork, purpose]))


def _shared_draws(rng: np.random.Generator, options: WarpOptions) -> _Shared:
    region = draw_region(rng)
    lon0, lat0 = region.centre
    projection = draw_projection(rng, lon0, lat0, region.lat_span, options.projection_weights)
    x_west, _ = projection.forward(lon0 - region.lon_span / 2.0, lat0)
    x_east, _ = projection.forward(lon0 + region.lon_span / 2.0, lat0)
    affine, affine_params = fit_affine(
        projection, region.centre, float(x_east - x_west), region.image_size, rng
    )

    apply_field = bool(rng.random() < options.field_probability)
    field = draw_field(rng, region.image_size)
    apply_bump = bool(rng.random() < options.bump_probability)
    centre = _land_pixel(rng, Warp(projection, affine, region.image_size, (), affine_params))
    if centre is None:
        raise Rejected("no land for a local error")
    bump = draw_bump(rng, region.image_size, centre)
    generalisation = draw_generalisation(rng, region.image_size)
    style = draw_style(rng, region.lon_span)
    return _Shared(
        region, projection, affine, affine_params, field, bump, apply_field, apply_bump,
        generalisation if options.coast_generalisation else None, style,
        fork=int(rng.integers(2**63)),
    )


def _render(
    map_seed: int,
    deformation: Optional[str],
    shared: _Shared,
    warp: Warp,
    visible: Polygon,
    frame: Dict[str, float],
    units: UnitSource,
) -> SyntheticMap:
    region, style, generalisation = shared.region, shared.style, shared.generalisation
    layers = drawn_layers(warp, visible, land_layers(), style.graticule_step, generalisation)
    ocean_fraction = float(layers.ocean_mask(region.image_size).mean())
    land_fraction = float(layers.land_mask(region.image_size).mean())
    # No minimum of land or sea: the centre is on a coastline, so every map has
    # one, and how much is recorded (coast_signals) rather than required.

    level, zones = choose_zones(visible, warp, units)
    sift = sift_candidates(frame, warp)
    if generalisation is not None:
        drawn = drawn_zone_geometries(
            [z.pixel_geometry for z in zones],
            layers.true_land,
            layers.land_with_lakes.difference(layers.lakes),
            generalisation.reach_px,
        )
        zones = [replace(z, drawn_geometry=g) for z, g in zip(zones, drawn) if not g.is_empty]
        coastal = [c for c in sift if c["feature"] == "coastline"]
        if coastal:
            true_px = np.array([c["pixel"] for c in coastal])
            moved = drawn_feature_pixels(layers.coastline, true_px, generalisation)
            for c, p in zip(coastal, moved):
                c["drawnPixel"] = (float(p[0]), float(p[1]))
            # A feature the map does not draw (an island dropped, a cape
            # simplified away) cannot be matched: its nearest drawn coast is
            # another feature, tens of pixels off.
            shifted = generalisation.move(true_px)
            undrawn = {
                id(c) for c, s, p in zip(coastal, shifted, moved)
                if np.hypot(*(p - s)) > generalisation.snap_px
            }
            sift = [c for c in sift if id(c) not in undrawn]
    coast = coast_signals(layers, zones, region.image_size)
    colours = assign_colours(zones, style.sea, shared.rng(_COLOURS))
    image = render_map(layers, zones, colours, style, region.image_size)

    return SyntheticMap(
        map_id=map_id(map_seed, deformation),
        seed=map_seed,
        deformation=deformation,
        generator_version=GENERATOR_VERSION,
        attempts=0,
        rejections={},
        region=region,
        warp=warp,
        visible=visible,
        frame_bounds=frame,
        zone_level=level,
        zones=zones,
        colours=colours,
        style=style,
        layers=layers,
        land_fraction=land_fraction,
        ocean_fraction=ocean_fraction,
        coast=coast,
        image=image,
        water_pick=water_pick(layers.ocean_mask(region.image_size)),
        sift_candidates=sift,
        city_candidates=city_candidates(frame, warp),
        generalisation=generalisation,
    )


def _attempt(
    rng: np.random.Generator,
    map_seed: int,
    units: UnitSource,
    options: WarpOptions,
    deformations: Sequence[Optional[str]],
) -> Dict[Optional[str], SyntheticMap]:
    """One draw of the map under each of *deformations*. Any of them rejected
    rejects them all, so twins always come from the same draw; the stress
    twin is softened instead (``_stress_twin``)."""
    shared = _shared_draws(rng, options)
    base = [d for d in deformations if d != "stress"]
    # Twins are framed on the three base twins whichever are drawn; the map as
    # drawn on itself.
    framed = list(_FRAMED) if None not in deformations else base
    warps = {d: shared.warp(d) for d in dict.fromkeys(base + framed)}
    visible = {d: visible_region(w) for d, w in warps.items()}
    # One framing box for all twins, enclosing what each shows, as a user's
    # loose box would: the same box gives the same SIFT and city suggestions,
    # so a layout clicks the same features on every twin.
    frame = frame_bounds(shapely.union_all([visible[d] for d in framed]).envelope, shared.rng(_FRAME))
    maps = {d: _render(map_seed, d, shared, warps[d], visible[d], frame, units) for d in base}
    if "stress" in deformations:
        maps["stress"] = _stress_twin(map_seed, shared, frame, units)
    return {d: maps[d] for d in deformations}


def _stress_twin(map_seed: int, shared: _Shared, frame: Dict[str, float], units: UnitSource) -> SyntheticMap:
    """The stress twin, from its own stream. A draw that folds, or leaves no
    usable map, is drawn again weaker and with a wider seam; how much weaker
    is in its ``rejections`` (``stress softened``)."""
    rng = shared.rng(_STRESS)
    size = shared.region.image_size
    plain = Warp(shared.projection, shared.affine, size, (), shared.affine_params)
    centres = [c for c in (_land_pixel(rng, plain) for _ in range(int(rng.integers(STRESS_BUMPS[0], STRESS_BUMPS[1] + 1)))) if c is not None]
    strength, seam = 1.0, SEAM_RATIO
    for attempt in range(STRESS_ATTEMPTS):
        displacements = draw_stress(rng, size, centres, strength, seam)
        warp = Warp(shared.projection, shared.affine, size, displacements, shared.affine_params)
        try:
            if warp.min_jacobian_determinant(STRESS_FOLD_CHECK_GRID) <= 0.0:
                raise Rejected("warp folds")
            synthetic = _render(map_seed, "stress", shared, warp, visible_region(warp), frame, units)
        except Rejected:
            strength *= STRESS_SOFTENING
            seam /= STRESS_SOFTENING
            continue
        synthetic.stress = {"strength": round(strength, 4), "softenings": attempt}
        return synthetic
    raise Rejected("no stress warp")


def _generate(
    map_seed: int, units: UnitSource, options: WarpOptions, deformations: Sequence[Optional[str]]
) -> Dict[Optional[str], SyntheticMap]:
    # Rejected draws loop inside the same generator, so a seed always lands on
    # the same map.
    rng = np.random.default_rng(np.random.SeedSequence([map_seed]))
    rejections: Dict[str, int] = {}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            maps = _attempt(rng, map_seed, units, options, deformations)
        except Rejected as e:
            rejections[str(e)] = rejections.get(str(e), 0) + 1
            continue
        for synthetic in maps.values():
            synthetic.attempts = attempt
            synthetic.rejections = rejections
        return maps
    raise RuntimeError(f"No map for seed {map_seed} in {MAX_ATTEMPTS} attempts: {rejections}")


def generate_map(
    map_seed: int, units: UnitSource = border_units, options: WarpOptions = WarpOptions()
) -> SyntheticMap:
    """The map of *map_seed*, its displacements as drawn by *options*."""
    return _generate(map_seed, units, options, (None,))[None]


def generate_twins(
    map_seed: int,
    units: UnitSource = border_units,
    options: WarpOptions = WarpOptions(),
    deformations: Sequence[str] = DEFORMATIONS,
) -> Dict[str, SyntheticMap]:
    """The twins of *map_seed* (some of ``DEFORMATIONS``). A twin is the same
    whichever others are drawn with it: they share every draw but the
    displacement, and the framing box of the three base twins. The map as
    drawn is a different draw of the same seed. *options* only sets the
    projections: the twins ignore its coins."""
    return _generate(map_seed, units, options, tuple(deformations))


def case_id(map_seed: int, layout_index: int, deformation: Optional[str] = None) -> str:
    return f"{map_id(map_seed, deformation)}-l{layout_index:02d}"


def generate_case(
    synthetic: SyntheticMap, layout_index: int, options: LayoutOptions = LayoutOptions()
) -> SyntheticCase:
    """Layout *layout_index* on *synthetic*, from its own seed: adding layouts
    never changes a map or another layout. Raises ``Rejected`` when the map has
    too few SIFT suggestions. Twins share the seed, so a layout makes the same
    draws on each of them."""
    rng = np.random.default_rng(np.random.SeedSequence([synthetic.seed, layout_index]))
    family_rng = np.random.default_rng(np.random.SeedSequence([synthetic.seed, layout_index, _FAMILY]))
    family = FAMILY_PROTOCOL if family_rng.random() < options.protocol_probability else FAMILY_OPEN
    curves = {"coastline": synthetic.layers.coastline, "lake": synthetic.layers.lakes.boundary}
    layout = draw_layout(
        rng, synthetic.warp, synthetic.sift_candidates, synthetic.city_candidates, curves, options, family
    )
    check_rng = np.random.default_rng(np.random.SeedSequence([synthetic.seed, layout_index, _CHECKS]))
    layout.check_points = draw_check_points(
        check_rng,
        synthetic.warp,
        synthetic.sift_candidates,
        synthetic.city_candidates,
        layout,
        shapely.union_all([z.drawn for z in synthetic.zones]),
    )
    return SyntheticCase(synthetic, layout_index, layout)
