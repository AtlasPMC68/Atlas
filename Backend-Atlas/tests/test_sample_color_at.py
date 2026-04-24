import numpy as np

from app.utils.color_in_legends_extraction import sample_color_at


def test_sample_color_at_x_norm_one_maps_to_last_pixel():
    # 3x3 image with unique colors per pixel (so radius=0 is deterministic).
    img = np.zeros((3, 3, 3), dtype=np.uint8)
    img[1, 2] = [10, 20, 30]  # middle row, last column

    color = sample_color_at(img, x_norm=1.0, y_norm=0.5, radius_px=0)
    assert color is not None
    assert color["rgb"] == [10, 20, 30]


def test_sample_color_at_y_norm_one_maps_to_last_pixel():
    img = np.zeros((3, 3, 3), dtype=np.uint8)
    img[2, 1] = [111, 112, 113]  # last row, middle column

    color = sample_color_at(img, x_norm=0.5, y_norm=1.0, radius_px=0)
    assert color is not None
    assert color["rgb"] == [111, 112, 113]
