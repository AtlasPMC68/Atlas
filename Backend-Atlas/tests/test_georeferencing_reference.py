"""Unit tests for the reference layers (Step 2).

These need numpy, scipy and shapely but not cv2, so they run without the image
stack. The ones that build real layers read the Natural Earth files from
``app/geojson`` and are skipped if a layer is missing.
"""

import os

import numpy as np
import pytest
from shapely.geometry import LineString, box

from app.utils.georeferencing import frame_bounds_from_geo_points
from app.utils.georeferencing.reference import (
    COASTLINE_FILE,
    LAKES_FILE,
    RIVERS_FILE,
    ReferenceGrid,
    _layer_path,
    build_reference_layers,
    load_reference_linework,
    rasterize_layer,
)

# The framing box used by the one existing dev-test case, near enough.
QUEBEC = {"west": -80.0, "south": 44.0, "east": -56.0, "north": 62.0}

_LAYERS_PRESENT = all(
    os.path.exists(_layer_path(name))
    for name in (COASTLINE_FILE, LAKES_FILE, RIVERS_FILE)
)
requires_layers = pytest.mark.skipif(
    not _LAYERS_PRESENT, reason="Natural Earth reference layers not present"
)


class TestReferenceGrid:
    def setup_method(self):
        self.grid = ReferenceGrid(
            west=-80.0, south=44.0, east=-56.0, north=62.0, width=1024, height=768
        )

    def test_north_is_at_the_top(self):
        """py grows downward, matching the existing raster convention."""
        _, py_north = self.grid.to_pixel(-70.0, 62.0)
        _, py_south = self.grid.to_pixel(-70.0, 44.0)
        assert float(py_north) == pytest.approx(0.0)
        assert float(py_south) == pytest.approx(768.0)

    def test_west_is_at_the_left(self):
        px_west, _ = self.grid.to_pixel(-80.0, 50.0)
        px_east, _ = self.grid.to_pixel(-56.0, 50.0)
        assert float(px_west) == pytest.approx(0.0)
        assert float(px_east) == pytest.approx(1024.0)

    def test_round_trips(self):
        lon = np.array([-79.0, -70.0, -57.0])
        lat = np.array([45.0, 53.0, 61.0])
        px, py = self.grid.to_pixel(lon, lat)
        back_lon, back_lat = self.grid.to_lonlat(px, py)
        assert np.allclose(back_lon, lon)
        assert np.allclose(back_lat, lat)

    def test_km_per_pixel_is_plausible(self):
        # A 24 deg x 18 deg box at 1024x768 is a couple of km per pixel.
        assert 1.0 < self.grid.km_per_pixel < 5.0

    def test_does_not_wrap_by_default(self):
        assert not self.grid.wraps_antimeridian
        assert len(self.grid.clip_boxes()) == 1


class TestAntimeridianGrid:
    def setup_method(self):
        # A box from 170E east across the date line to 170W.
        self.grid = ReferenceGrid(
            west=170.0, south=-10.0, east=-170.0, north=10.0, width=200, height=100
        )

    def test_detects_the_wrap(self):
        assert self.grid.wraps_antimeridian
        assert self.grid.lon_span == pytest.approx(20.0)

    def test_maps_both_sides_of_the_date_line(self):
        px_west, _ = self.grid.to_pixel(170.0, 0.0)
        px_mid, _ = self.grid.to_pixel(180.0, 0.0)
        px_east, _ = self.grid.to_pixel(-170.0, 0.0)
        assert float(px_west) == pytest.approx(0.0)
        assert float(px_mid) == pytest.approx(100.0)
        assert float(px_east) == pytest.approx(200.0)

    def test_round_trips_back_into_source_longitudes(self):
        lon, _ = self.grid.to_lonlat(np.array([150.0]), np.array([50.0]))
        assert -180.0 <= lon[0] <= 180.0
        assert lon[0] == pytest.approx(-175.0)

    def test_uses_two_clip_boxes(self):
        boxes = self.grid.clip_boxes()
        assert len(boxes) == 2
        assert [shift for _, shift in boxes] == [0.0, 360.0]


class TestRasterization:
    def setup_method(self):
        self.grid = ReferenceGrid(
            west=0.0, south=0.0, east=10.0, north=10.0, width=100, height=100
        )

    def test_draws_a_continuous_line(self):
        raster = rasterize_layer(self.grid, LineString([(1.0, 5.0), (9.0, 5.0)]))
        row = raster[int(round((10.0 - 5.0) / 10.0 * 100))]
        assert row.sum() > 70  # ~80 px of span, no gaps

    def test_line_is_one_pixel_thin(self):
        """A thick stroke would flatten the distance field near the curve."""
        raster = rasterize_layer(self.grid, LineString([(1.0, 5.0), (9.0, 5.0)]))
        columns_with_ink = raster[:, 50]
        assert columns_with_ink.sum() == 1

    def test_clips_instead_of_dropping_out_of_bounds_vertices(self):
        """The artifact that stopped `draw_coastline` being promoted verbatim.

        This line leaves the box to the east and comes back. Dropping the
        out-of-bounds vertex, as the old rasterizer does, would join (1, 1)
        straight to (1, 9) and paint a vertical line along lon=1 that exists
        nowhere on Earth. Clipping produces a V that never touches lon=1 at the
        midpoint latitude.
        """
        detour = LineString([(1.0, 1.0), (20.0, 5.0), (1.0, 9.0)])
        raster = rasterize_layer(self.grid, detour)

        # The phantom chord would run down column 10 (lon=1) through row 50.
        phantom_col = 10
        assert not raster[45:56, phantom_col].any()

        # ...while the real, clipped arms are present near the box edge.
        assert raster[:, 90:].any()

    def test_empty_geometry_gives_an_empty_raster(self):
        assert not rasterize_layer(self.grid, None).any()
        assert not rasterize_layer(self.grid, LineString()).any()

    def test_geometry_entirely_outside_the_box_draws_nothing(self):
        outside = LineString([(50.0, 50.0), (60.0, 60.0)])
        assert not rasterize_layer(self.grid, outside).any()

    def test_polygon_layers_contribute_their_boundary(self):
        """A lake shoreline is a closed curve; its filled interior is not."""
        raster = rasterize_layer(self.grid, box(2.0, 2.0, 8.0, 8.0).boundary)
        interior = raster[40:60, 40:60]
        assert raster.any()
        assert not interior.any()


@requires_layers
class TestLayerLoading:
    def test_lakes_load_as_linework_not_polygons(self):
        geom = load_reference_linework(LAKES_FILE)
        assert geom is not None
        assert "Polygon" not in geom.geom_type

    def test_rivers_layer_is_present_and_linear(self):
        geom = load_reference_linework(RIVERS_FILE)
        assert geom is not None
        assert "Line" in geom.geom_type

    def test_missing_layer_is_none_not_an_exception(self):
        assert load_reference_linework("does_not_exist.geojson") is None


@requires_layers
class TestBuildReferenceLayers:
    @classmethod
    def setup_class(cls):
        cls.layers = build_reference_layers(QUEBEC)

    def test_is_cached_on_the_framing_box(self):
        assert build_reference_layers(dict(QUEBEC)) is self.layers

    def test_every_raster_has_the_grid_shape(self):
        shape = (self.layers.grid.height, self.layers.grid.width)
        for raster in (
            self.layers.coastline,
            self.layers.lakes,
            self.layers.rivers,
            self.layers.land,
            self.layers.curves,
            self.layers.distance_px,
            self.layers.signed_distance_px,
        ):
            assert raster.shape == shape

    def test_all_three_curve_layers_have_content(self):
        coverage = self.layers.coverage()
        assert coverage["coastline"] > 0.0
        assert coverage["lakes"] > 0.0
        assert coverage["rivers"] > 0.0

    def test_curves_is_the_union_of_the_three(self):
        expected = self.layers.coastline | self.layers.lakes | self.layers.rivers
        assert np.array_equal(self.layers.curves, expected)

    def test_quebec_is_mostly_land(self):
        land_fraction = self.layers.coverage()["land"]
        assert 0.4 < land_fraction < 0.9

    def test_distance_is_zero_on_curves_and_positive_off_them(self):
        assert self.layers.distance_px[self.layers.curves].max() == 0.0
        assert self.layers.distance_px[~self.layers.curves].min() > 0.0

    def test_signed_distance_agrees_with_the_land_mask(self):
        """Positive on land, negative in water -- that is what the sign means."""
        signed = self.layers.signed_distance_px
        assert (signed[self.layers.land] >= 0).all()
        assert (signed[~self.layers.land] <= 0).all()

    def test_signed_distance_crosses_zero_at_the_coast(self):
        signed = self.layers.signed_distance_px
        assert signed.min() < 0.0 < signed.max()
        assert np.abs(signed[self.layers.coastline]).max() == 0.0

    def test_gradient_is_finite(self):
        assert np.isfinite(self.layers.gradient_x).all()
        assert np.isfinite(self.layers.gradient_y).all()

    def test_layer_versions_are_recorded(self):
        versions = self.layers.layer_versions
        assert set(versions) == {COASTLINE_FILE, LAKES_FILE, RIVERS_FILE}
        assert all(v is not None for v in versions.values())

    def test_curve_samples_land_inside_the_framing_box(self):
        lon, lat = self.layers.sample_curve_points(spacing_px=4.0)
        assert lon.size > 100
        assert lon.min() >= QUEBEC["west"] - 1e-6
        assert lon.max() <= QUEBEC["east"] + 1e-6
        assert lat.min() >= QUEBEC["south"] - 1e-6
        assert lat.max() <= QUEBEC["north"] + 1e-6

    def test_sample_spacing_controls_density(self):
        dense, _ = self.layers.sample_curve_points(spacing_px=1.0, max_points=None)
        sparse, _ = self.layers.sample_curve_points(spacing_px=8.0, max_points=None)
        assert sparse.size < dense.size

    def test_max_points_is_respected(self):
        lon, _ = self.layers.sample_curve_points(spacing_px=1.0, max_points=500)
        assert lon.size <= 500


class TestBuildValidation:
    @pytest.mark.parametrize(
        "bounds",
        [
            None,
            {},
            {"west": -80.0, "south": 62.0, "east": -56.0, "north": 44.0},
            {"west": -70.0, "south": 44.0, "east": -70.0, "north": 62.0},
        ],
    )
    def test_rejects_unusable_framing_boxes(self, bounds):
        with pytest.raises(ValueError):
            build_reference_layers(bounds)

    def test_rejects_a_degenerate_raster(self):
        with pytest.raises(ValueError):
            build_reference_layers(QUEBEC, width=1, height=1)


class TestFrameBoundsFallback:
    """Maps imported before the framing box existed still need an extent."""

    POINTS = [(-78.8, 56.3), (-64.5, 45.8), (-58.2, 49.2), (-77.9, 60.7)]

    def test_contains_every_control_point(self):
        bounds = frame_bounds_from_geo_points(self.POINTS)
        for lon, lat in self.POINTS:
            assert bounds["west"] < lon < bounds["east"]
            assert bounds["south"] < lat < bounds["north"]

    def test_pads_outwards(self):
        """The points sit inside the mapped area, so their bbox is too tight."""
        bounds = frame_bounds_from_geo_points(self.POINTS)
        assert bounds["west"] < min(p[0] for p in self.POINTS)
        assert bounds["east"] > max(p[0] for p in self.POINTS)

    def test_stays_within_valid_coordinates(self):
        bounds = frame_bounds_from_geo_points([(-179.0, -89.0), (179.0, 89.0)])
        assert bounds["west"] >= -180.0
        assert bounds["east"] <= 180.0
        assert bounds["south"] >= -90.0
        assert bounds["north"] <= 90.0

    def test_needs_at_least_two_points(self):
        assert frame_bounds_from_geo_points([(-70.0, 45.0)]) is None
        assert frame_bounds_from_geo_points([]) is None
        assert frame_bounds_from_geo_points(None) is None

    def test_the_result_builds_reference_layers(self):
        bounds = frame_bounds_from_geo_points(self.POINTS)
        if not _LAYERS_PRESENT:
            pytest.skip("Natural Earth reference layers not present")
        assert build_reference_layers(bounds).has_curves
