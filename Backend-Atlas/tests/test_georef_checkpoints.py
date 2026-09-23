import json

from pyproj import Transformer

from app.utils.dev_test_evaluator import evaluate_georef_check_points_from_config
from app.utils.georef_baseline import compare_report_to_baseline


def test_georef_check_points_exact_affine(tmp_path):
    """Independent check points should have near-zero error for an exact affine map."""
    to_wgs84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    # Define a simple exact affine relation in WebMercator:
    # X = 1000*x + 200000, Y = 1000*y + 5000000.
    def world_for_pixel(x: float, y: float) -> dict[str, float]:
        lon, lat = to_wgs84.transform(1000.0 * x + 200000.0, 1000.0 * y + 5_000_000.0)
        return {"lng": lon, "lat": lat}

    config = {
        "georef": {
            "imagePoints": [
                {"x": 0.0, "y": 0.0},
                {"x": 100.0, "y": 0.0},
                {"x": 0.0, "y": 100.0},
                {"x": 100.0, "y": 100.0},
            ],
            "worldPoints": [
                world_for_pixel(0.0, 0.0),
                world_for_pixel(100.0, 0.0),
                world_for_pixel(0.0, 100.0),
                world_for_pixel(100.0, 100.0),
            ],
            "checkPoints": [
                {
                    "name": "center",
                    "image": {"x": 50.0, "y": 50.0},
                    "world": world_for_pixel(50.0, 50.0),
                },
                {
                    "name": "quarter",
                    "image": {"x": 25.0, "y": 75.0},
                    "world": world_for_pixel(25.0, 75.0),
                },
            ],
        }
    }

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    metrics = evaluate_georef_check_points_from_config(str(config_path))

    assert metrics is not None
    assert metrics["controlPointCount"] == 4
    assert metrics["checkpointCount"] == 2
    assert metrics["rmseMeters"] < 0.01
    assert metrics["medianMeters"] < 0.01
    assert metrics["p95Meters"] < 0.01
    assert metrics["maxMeters"] < 0.01


def test_baseline_comparison_accepts_platform_float_drift():
    baseline = {
        "meanIou": 0.94,
        "meanPrecision": 0.99,
        "meanRecall": 0.95,
        "totalFalseNegativeArea": 10.0,
        "totalFalsePositiveArea": 1.5,
        "georefAccuracy": {
            "rmseMeters": 1_344_457.452879488,
            "medianMeters": 1_233_740.435818308,
            "p95Meters": 1_532_999.9666341944,
            "maxMeters": 1_566_251.0256137373,
            "checkPoints": [{"errorMeters": 1_566_251.0256137373}],
        },
    }
    report = {
        "metrics": {
            "mean": {
                "meanIou": 0.94,
                "meanPrecision": 0.99,
                "meanRecall": 0.95,
                "totalFalseNegativeArea": 10.0,
                "totalFalsePositiveArea": 1.5,
            }
        },
        "georefAccuracy": {
            "rmseMeters": 1_344_457.452881115,
            "medianMeters": 1_233_740.435818308,
            "p95Meters": 1_532_999.9666374944,
            "maxMeters": 1_566_251.0256173962,
            "checkPoints": [{"errorMeters": 1_566_251.0256173962}],
        },
    }

    not_worse, strictly_better, problems = compare_report_to_baseline(
        report, baseline
    )

    assert not_worse
    assert not strictly_better
    assert problems == []
