"""The requirement manifest, the derived store, and case kinds.

The thing under test is the distinction that makes the harness trustworthy: a
case missing a *user* input cannot be repaired by re-running anything, while a
case missing a *derived* artifact can. Getting that backwards either blocks a
runnable case or silently runs one with less evidence than the algorithm wants.
"""

import json
import os

import pytest

from app.utils.dev_test_cases import (
    KIND_PROBE,
)
from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG
from app.utils.georeferencing.requirements import (
    MissingUserInputError,
    check_requirements,
    georef_requirements,
)


# --- which requirements are in force ---------------------------------------


def test_text_regions_are_required_only_when_alignment_runs():
    """The suite measures the GCP-only floor, so it must not pay for OCR."""
    off = DEFAULT_GEOREF_CONFIG.with_overrides(enable_curve_alignment=False)
    on = DEFAULT_GEOREF_CONFIG.with_overrides(enable_curve_alignment=True)

    assert "textRegions" not in {r.key for r in georef_requirements(off)}
    assert "textRegions" in {r.key for r in georef_requirements(on)}


# --- user input versus derived ---------------------------------------------


def _full_presence(**overrides):
    presence = {
        "controlPoints": True,
        "frameBounds": True,
        "zonePicks": True,
        "legend": True,
        "waterPicks": True,
        "textRegions": True,
    }
    presence.update(overrides)
    return presence


ALIGNED = DEFAULT_GEOREF_CONFIG.with_overrides(enable_curve_alignment=True)


def test_missing_required_user_input_blocks_the_run():
    report = check_requirements(_full_presence(zonePicks=False), ALIGNED)

    assert not report.runnable
    assert [s.key for s in report.blocked] == ["zonePicks"]
    with pytest.raises(MissingUserInputError) as exc:
        report.raise_if_blocked("some/case")
    # The remedy has to survive into the message, not just the key.
    assert "Compléter les entrées" in str(exc.value)


def test_missing_derived_artifact_is_refreshable_not_blocking():
    """OCR is an expense, never a blocker: re-running it recovers it exactly."""
    report = check_requirements(_full_presence(textRegions=False), ALIGNED)

    assert report.runnable
    assert [s.key for s in report.refreshable] == ["textRegions"]


# --- case kinds -------------------------------------------------------------


# --- the derived store ------------------------------------------------------


def test_derived_artifact_is_invalidated_by_a_different_image(tmp_path, monkeypatch):
    import app.utils.dev_test_derived as derived

    monkeypatch.setattr(derived, "DERIVED_DIR", str(tmp_path / "derived"))

    image = tmp_path / "map.jpg"
    image.write_bytes(b"original image bytes")

    artifact = derived.DerivedArtifact(
        key=derived.TEXT_REGIONS_KEY,
        payload=[[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]],
        image_sha=derived._image_fingerprint(str(image)),
        producer={"easyocr": "1.7.2"},
        produced_at="2026-01-01T00:00:00+00:00",
    )
    derived._store_artifact("map1", artifact)

    fresh = derived.inspect_derived("map1", derived.TEXT_REGIONS_KEY, str(image))
    assert fresh.usable and fresh.present

    # Same path, different content: mtime would not catch this after a checkout.
    image.write_bytes(b"a completely different scan")
    stale = derived.inspect_derived("map1", derived.TEXT_REGIONS_KEY, str(image))
    assert stale.present and not stale.usable
    assert stale.detail.startswith("stale:")
    # Feeds straight into the requirement check as a refresh, not a block.
    report = check_requirements(
        _full_presence(textRegions=stale.as_presence()), ALIGNED
    )
    assert report.runnable
    assert [s.key for s in report.refreshable] == ["textRegions"]


# --- task dispatch ----------------------------------------------------------


# --- per-run switches -------------------------------------------------------


# --- tuning-panel overrides -------------------------------------------------


def test_config_overrides_reject_wrong_types():
    from app.utils.georeferencing.config import parse_config_overrides

    for bad in (
        {"edge_canny_low": 35.5},
        {"edge_canny_low": "35"},
        {"gate_max_rotation_deg": True},
        {"gate_max_rotation_deg": float("nan")},
        {"edge_water_filter": "false"},
        {"coarse_blur_px": []},
        {"coarse_blur_px": [1.0, "x"]},
    ):
        with pytest.raises(ValueError):
            parse_config_overrides(bad)


def test_non_ambient_run_does_not_win_best(tmp_path, monkeypatch):
    """`zones_best` must not mix a snapped run with an unsnapped one."""
    import app.utils.dev_test as dev_test
    from app.utils.dev_test_evaluator import SCORE_VERSION, build_test_case_paths

    test_id, case_id = "promo", "case"
    assets_root = tmp_path / "assets"
    paths = build_test_case_paths(str(assets_root), test_id, case_id)
    os.makedirs(paths.case_dir, exist_ok=True)

    with open(paths.extracted_zones_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": []}, f)

    # A previous, ambient run that scored worse.
    with open(paths.best_report_path, "w", encoding="utf-8") as f:
        json.dump({"scoreVersion": SCORE_VERSION, "metrics": {"scoreUsed": 0.5}}, f)

    def fake_evaluate(*_args, **_kwargs):
        return {"scoreVersion": SCORE_VERSION, "metrics": {"scoreUsed": 0.99}}, {
            "type": "FeatureCollection",
            "features": [],
        }, None

    import app.utils.dev_test_evaluator as evaluator

    monkeypatch.setattr(evaluator, "evaluate_georef_test_case", fake_evaluate)

    dev_test.evaluate_and_persist_case(
        assets_root=str(assets_root),
        test_id=test_id,
        test_case_id=case_id,
        min_iou=None,
        allow_best_promotion=False,
    )

    with open(paths.best_report_path, "r", encoding="utf-8") as f:
        best = json.load(f)
    assert best["metrics"]["scoreUsed"] == 0.5, "a 0.99 non-ambient run took best"

    # The same run, ambient, is allowed to win.
    dev_test.evaluate_and_persist_case(
        assets_root=str(assets_root),
        test_id=test_id,
        test_case_id=case_id,
        min_iou=None,
        allow_best_promotion=True,
    )
    with open(paths.best_report_path, "r", encoding="utf-8") as f:
        best = json.load(f)
    assert best["metrics"]["scoreUsed"] == 0.99


# --- control point sources --------------------------------------------------


def _case_inputs(n_sift: int, n_city: int):
    from types import SimpleNamespace

    from app.utils.georeferencing import ControlPoint

    points = [ControlPoint.sift((i, i), (-70.0, 45.0 + i)) for i in range(n_sift)]
    points += [
        ControlPoint.from_city((50 + i, i), (-71.0, 46.0 + i), 100 + i, f"City {i}")
        for i in range(n_city)
    ]
    return SimpleNamespace(
        control_points=points,
        check_points=[],
        frame_bounds={"west": -80.0, "south": 40.0, "east": -60.0, "north": 60.0},
        imposed_click_positions=[(0.5, 0.5)],
        water_click_positions=None,
        legend_answered=True,
    )


def _state(inputs, sources):
    from app.utils.dev_test_cases import build_case_state

    return build_case_state(
        test_id="no-such-map",
        test_case_id="case",
        inputs=inputs,
        image_path="unused.png",
        config=DEFAULT_GEOREF_CONFIG.with_overrides(gcp_sources=sources),
        case_config={},
        kind=KIND_PROBE,
    )


def _status(state, key):
    return next(s.status for s in state.requirements.states if s.key == key)


# --- legend -------------------------------------------------------------------


def _legend_state(kind, legend_answered):
    from types import SimpleNamespace

    from app.utils.dev_test_cases import build_case_state

    inputs = _case_inputs(n_sift=4, n_city=0)
    inputs = SimpleNamespace(**{**vars(inputs), "legend_answered": legend_answered})
    return build_case_state(
        test_id="no-such-map",
        test_case_id="case",
        inputs=inputs,
        image_path="unused.png",
        config=DEFAULT_GEOREF_CONFIG,
        case_config={},
        kind=kind,
    )


def test_missing_legend_answer_is_blocked():
    report = check_requirements(_full_presence(legend=False), ALIGNED)
    assert [s.key for s in report.blocked] == ["legend"]


