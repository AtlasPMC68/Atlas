"""Unit tests for the reference layers (Step 2).

These need numpy, scipy and shapely but not cv2, so they run without the image
stack. The ones that build real layers read the Natural Earth files from
``app/geojson`` and are skipped if a layer is missing.
"""

import os

import numpy as np
import pytest
from shapely.geometry import LineString

from app.utils.georeferencing.reference import (
    COASTLINE_FILE,
    LAKES_FILE,
    ReferenceGrid,
    _layer_path,
    build_reference_layers,
    rasterize_layer,
)

# The framing box used by the one existing dev-test case, near enough.
QUEBEC = {"west": -80.0, "south": 44.0, "east": -56.0, "north": 62.0}

_LAYERS_PRESENT = all(
    os.path.exists(_layer_path(name))
    for name in (COASTLINE_FILE, LAKES_FILE)
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


class TestAntimeridianGrid:
    def setup_method(self):
        # A box from 170E east across the date line to 170W.
        self.grid = ReferenceGrid(
            west=170.0, south=-10.0, east=-170.0, north=10.0, width=200, height=100
        )


    def test_round_trips_back_into_source_longitudes(self):
        lon, _ = self.grid.to_lonlat(np.array([150.0]), np.array([50.0]))
        assert -180.0 <= lon[0] <= 180.0
        assert lon[0] == pytest.approx(-175.0)


class TestRasterization:
    def setup_method(self):
        self.grid = ReferenceGrid(
            west=0.0, south=0.0, east=10.0, north=10.0, width=100, height=100
        )


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


@requires_layers
class TestBuildReferenceLayers:
    @classmethod
    def setup_class(cls):
        cls.layers = build_reference_layers(QUEBEC)


    def test_signed_distance_crosses_zero_at_the_coast(self):
        signed = self.layers.signed_distance_px
        assert signed.min() < 0.0 < signed.max()
        assert np.abs(signed[self.layers.coastline]).max() == 0.0


