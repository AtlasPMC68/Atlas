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
    KIND_REGRESSION,
    normalize_kind,
)
from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG
from app.utils.georeferencing.requirements import (
    MissingUserInputError,
    RequirementKind,
    RequirementLevel,
    RequirementStatus,
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


def test_every_requirement_carries_a_remedy():
    """The error message is the deliverable: a key alone tells a dev nothing."""
    for requirement in georef_requirements(
        DEFAULT_GEOREF_CONFIG.with_overrides(enable_curve_alignment=True)
    ):
        assert requirement.remedy.strip()
        if requirement.kind is RequirementKind.DERIVED:
            assert requirement.producer, f"{requirement.key} must name its producer"


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
    assert "Recreate the case" in str(exc.value)


def test_missing_derived_artifact_is_refreshable_not_blocking():
    """OCR is an expense, never a blocker: re-running it recovers it exactly."""
    report = check_requirements(_full_presence(textRegions=False), ALIGNED)

    assert report.runnable
    assert [s.key for s in report.refreshable] == ["textRegions"]


def test_stale_derived_artifact_is_treated_as_missing():
    """A cache serving a result from another image is worse than no cache."""
    report = check_requirements(
        _full_presence(textRegions=(True, "stale: produced from a different image")),
        ALIGNED,
    )

    assert report.runnable
    assert [s.key for s in report.refreshable] == ["textRegions"]
    state = next(s for s in report.states if s.key == "textRegions")
    assert state.status is RequirementStatus.STALE


def test_missing_framing_box_blocks_the_run():
    """The box is the extent of every reference raster, not a units detail.

    Deriving one from the control points is systematically too tight -- the
    points sit inside the mapped area -- so a case without a drawn box aligns
    against cropped reference curves and reports a worse number for a reason
    unrelated to whatever was being measured.
    """
    report = check_requirements(_full_presence(frameBounds=False), ALIGNED)

    assert not report.runnable
    assert [s.key for s in report.blocked] == ["frameBounds"]
    state = next(s for s in report.states if s.key == "frameBounds")
    assert state.status is RequirementStatus.BLOCKED


def test_there_is_no_middle_level_between_required_and_optional():
    """A comfortable middle is how a case ends up running under-specified."""
    assert {level.value for level in RequirementLevel} == {"required", "optional"}
    assert "fallback" not in {status.value for status in RequirementStatus}


def test_absent_optional_input_is_neither_blocking_nor_refreshable():
    """A map with an unpainted ocean genuinely has no water picks."""
    report = check_requirements(_full_presence(waterPicks=False), ALIGNED)

    assert report.runnable
    assert not report.blocked
    assert not report.refreshable
    state = next(s for s in report.states if s.key == "waterPicks")
    assert state.status is RequirementStatus.ABSENT


def test_report_round_trips_to_json():
    """The state file is read by the UI, so it has to be plain JSON."""
    report = check_requirements(_full_presence(textRegions=False), ALIGNED)
    payload = json.loads(json.dumps(report.to_dict()))

    assert payload["runnable"] is True
    assert payload["refreshable"] == ["textRegions"]
    assert len(payload["requirements"]) == len(georef_requirements(ALIGNED))


# --- case kinds -------------------------------------------------------------


def test_unknown_kinds_fall_back_to_regression():
    """Every case written before kinds existed was created to be scored."""
    assert normalize_kind(None) == KIND_REGRESSION
    assert normalize_kind("") == KIND_REGRESSION
    assert normalize_kind("nonsense") == KIND_REGRESSION
    assert normalize_kind("PROBE") == KIND_PROBE
    assert normalize_kind(" regression ") == KIND_REGRESSION


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


def test_producer_drift_is_reported_but_still_usable(tmp_path, monkeypatch):
    """A library bump is not worth 135 s: record it, do not act on it."""
    import app.utils.dev_test_derived as derived

    monkeypatch.setattr(derived, "DERIVED_DIR", str(tmp_path / "derived"))

    image = tmp_path / "map.jpg"
    image.write_bytes(b"image bytes")

    derived._store_artifact(
        "map2",
        derived.DerivedArtifact(
            key=derived.TEXT_REGIONS_KEY,
            payload=[],
            image_sha=derived._image_fingerprint(str(image)),
            producer={"easyocr": "1.7.1"},
            produced_at="2026-01-01T00:00:00+00:00",
        ),
    )

    state = derived.inspect_derived(
        "map2", derived.TEXT_REGIONS_KEY, str(image), {"easyocr": "1.7.2"}
    )
    assert state.usable
    assert "1.7.1" in state.detail and "1.7.2" in state.detail
    # Not prefixed "stale:", so the requirement check leaves it satisfied.
    assert not state.detail.startswith("stale:")


def test_cached_regions_are_returned_without_running_ocr(tmp_path, monkeypatch):
    import app.utils.dev_test_derived as derived

    monkeypatch.setattr(derived, "DERIVED_DIR", str(tmp_path / "derived"))

    image = tmp_path / "map.jpg"
    image.write_bytes(b"image bytes")

    regions = [[[1.0, 2.0], [3.0, 2.0], [3.0, 4.0], [1.0, 4.0]]]
    derived._store_artifact(
        "map3",
        derived.DerivedArtifact(
            key=derived.TEXT_REGIONS_KEY,
            payload=regions,
            image_sha=derived._image_fingerprint(str(image)),
            producer={},
            produced_at="2026-01-01T00:00:00+00:00",
        ),
    )

    # image_bgr is None: reaching OCR at all would raise, which is the assertion.
    got, state = derived.ensure_text_regions(
        "map3", str(image), None, refresh=False
    )
    assert got == regions
    assert state.usable


def test_uncached_regions_without_permission_to_compute_return_none(
    tmp_path, monkeypatch
):
    import app.utils.dev_test_derived as derived

    monkeypatch.setattr(derived, "DERIVED_DIR", str(tmp_path / "derived"))

    image = tmp_path / "map.jpg"
    image.write_bytes(b"image bytes")

    got, state = derived.ensure_text_regions(
        "never-seen", str(image), None, refresh=False, allow_compute=False
    )
    assert got is None
    assert not state.present


def test_delete_derived_removes_the_map_directory(tmp_path, monkeypatch):
    """A re-upload under the same id must not inherit another map's OCR."""
    import app.utils.dev_test_derived as derived

    monkeypatch.setattr(derived, "DERIVED_DIR", str(tmp_path / "derived"))

    image = tmp_path / "map.jpg"
    image.write_bytes(b"image bytes")
    derived._store_artifact(
        "map4",
        derived.DerivedArtifact(
            key=derived.TEXT_REGIONS_KEY,
            payload=[],
            image_sha=derived._image_fingerprint(str(image)),
            producer={},
            produced_at="2026-01-01T00:00:00+00:00",
        ),
    )
    assert os.path.isdir(derived.derived_dir_for("map4"))

    derived.delete_derived("map4")
    assert not os.path.isdir(derived.derived_dir_for("map4"))


# --- task dispatch ----------------------------------------------------------


def test_task_kwargs_match_the_task_signature(tmp_path, monkeypatch):
    """Every key the builder emits must be a parameter the task accepts.

    `build_extraction_task_kwargs_for_case` dispatches with `**kwargs`, so a key
    the task does not declare is a TypeError raised inside the Celery worker,
    where it surfaces as a task that simply fails with no obvious cause. This
    used to be covered incidentally by the one regression case exercising the
    whole path; it no longer is, because a case can be blocked before dispatch.

    The emitted keys are read back from the builder rather than listed here, so
    adding one to the builder alone still fails this test.

    It does not, and cannot, catch a *worker* running older code than the
    caller. That is why the task resolves the case kind from disk instead of
    taking it as an argument.
    """
    import inspect

    import app.utils.dev_test as dev_test
    from app.tasks import process_dev_test_extraction

    test_id, case_id = "sig-check", "case"

    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    (maps_dir / f"{test_id}.jpg").write_bytes(b"not a real image, never decoded")
    monkeypatch.setattr(dev_test, "MAPS_DIR", str(maps_dir))

    assets_root = tmp_path / "assets"
    case_dir = assets_root / "test_cases" / test_id / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "config.json").write_text(
        json.dumps(
            {
                "testId": test_id,
                "testCaseId": case_id,
                "filename": f"{test_id}.jpg",
                "georef": {
                    "controlPoints": [
                        {
                            "source": "sift",
                            "pixel": {"x": 1.0, "y": 2.0},
                            "geo": {"lon": -70.0, "lat": 50.0},
                        }
                    ],
                    "frameBounds": {
                        "west": -80.0,
                        "south": 40.0,
                        "east": -60.0,
                        "north": 60.0,
                    },
                },
                "colors": {
                    "imposed": [
                        {"x": 0.5, "y": 0.5, "name": "Zone", "radius": 20,
                         "kind": "zone"}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    kwargs = dev_test.build_extraction_task_kwargs_for_case(
        assets_root=str(assets_root), test_id=test_id, test_case_id=case_id
    )

    # `bind=True`, so `self` is supplied by Celery rather than by the caller.
    accepted = set(
        inspect.signature(process_dev_test_extraction.run).parameters
    ) - {"self"}

    assert set(kwargs) <= accepted, (
        f"task does not accept: {sorted(set(kwargs) - accepted)}"
    )


# --- per-run switches -------------------------------------------------------


def test_run_switches_accept_only_known_boolean_fields():
    from app.utils.georeferencing.config import RUN_SWITCHES, parse_run_switches

    assert parse_run_switches({"snap_to_coastline": False}) == {
        "snap_to_coastline": False
    }
    # Every allowlisted switch must be a real field, or the override silently
    # does nothing when applied.
    from app.utils.georeferencing import GeorefConfig

    assert RUN_SWITCHES <= set(GeorefConfig.__dataclass_fields__)


def test_run_switches_drop_unknown_keys():
    """A stale frontend sending a retired switch must not fail the run."""
    from app.utils.georeferencing.config import parse_run_switches

    assert parse_run_switches({"retired_switch": True}) == {}
    # And it must not be able to reach in and retune the algorithm.
    assert parse_run_switches({"coarse_blur_px": (1.0,)}) == {}


def test_run_switches_reject_stringly_typed_booleans():
    """`"false"` is truthy; guessing at it is how a switch silently flips on."""
    from app.utils.georeferencing.config import parse_run_switches

    for bad in ("false", "true", 0, 1, None):
        with pytest.raises(ValueError):
            parse_run_switches({"snap_to_coastline": bad})


def test_run_switches_tolerate_absent_overrides():
    from app.utils.georeferencing.config import parse_run_switches

    assert parse_run_switches(None) == {}
    assert parse_run_switches({}) == {}


def test_switches_actually_change_the_resolved_config():
    from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG
    from app.utils.georeferencing.config import parse_run_switches

    base = DEFAULT_GEOREF_CONFIG.with_overrides(snap_to_coastline=True)
    flipped = base.with_overrides(
        **parse_run_switches({"snap_to_coastline": False})
    )

    assert base.snap_to_coastline is True
    assert flipped.snap_to_coastline is False
    # `with_overrides` drops None, so False must survive rather than be ignored.
    assert flipped.enable_curve_alignment == base.enable_curve_alignment


# --- tuning-panel overrides -------------------------------------------------


def test_field_groups_cover_every_field_exactly_once():
    """A field missing from the groups is untunable from the UI, silently."""
    from app.utils.georeferencing import GeorefConfig
    from app.utils.georeferencing.config import FIELD_GROUPS

    grouped = [name for _title, names in FIELD_GROUPS for name in names]
    assert len(grouped) == len(set(grouped))
    assert set(grouped) == set(GeorefConfig.__dataclass_fields__) - {"version"}


def test_config_overrides_coerce_to_the_field_type():
    from app.utils.georeferencing.config import parse_config_overrides

    parsed = parse_config_overrides(
        {
            "gate_max_rotation_deg": 20,  # int for a float field is fine
            "edge_canny_low": 35.0,  # JS sends integral floats this way
            "edge_water_filter": False,
            "coarse_blur_px": [80, 50, 30],  # JSON list, and a level fewer
        }
    )

    assert parsed == {
        "gate_max_rotation_deg": 20.0,
        "edge_canny_low": 35,
        "edge_water_filter": False,
        "coarse_blur_px": (80.0, 50.0, 30.0),
    }
    assert isinstance(parsed["edge_canny_low"], int)


def test_config_overrides_accept_a_listed_choice_and_reject_others():
    """A free-text model name is a typo away from silently running the wrong
    one, so the dropdown's values are the only ones accepted."""
    from app.utils.georeferencing.config import (
        TRANSFORM_MODELS,
        describe_config,
        parse_config_overrides,
    )
    from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG

    assert parse_config_overrides({"transform_model": "piecewise_affine"}) == {
        "transform_model": "piecewise_affine"
    }
    for bad in ("piecewise", "", "affine ", 3, True, None):
        with pytest.raises(ValueError):
            parse_config_overrides({"transform_model": bad})

    # What the UI renders the dropdown from has to be the same list.
    described = describe_config(DEFAULT_GEOREF_CONFIG)
    assert described["choices"]["transform_model"] == list(TRANSFORM_MODELS)


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


def test_config_overrides_drop_unknown_keys_and_version():
    from app.utils.georeferencing.config import parse_config_overrides

    assert parse_config_overrides({"retired_field": 1.0}) == {}
    # The version labels the code that made a run; a run cannot claim another.
    assert parse_config_overrides({"version": "99"}) == {}
    assert parse_config_overrides(None) == {}


def test_config_overrides_apply_to_a_copy_only():
    from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG
    from app.utils.georeferencing.config import parse_config_overrides

    run = DEFAULT_GEOREF_CONFIG.with_overrides(
        **parse_config_overrides({"gate_min_chamfer_improvement": 0.5})
    )

    assert run.gate_min_chamfer_improvement == 0.5
    assert DEFAULT_GEOREF_CONFIG.gate_min_chamfer_improvement == 0.02


def test_describe_config_reports_ambient_values():
    from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG
    from app.utils.georeferencing.config import describe_config

    ambient = DEFAULT_GEOREF_CONFIG.with_overrides(enable_curve_alignment=True)
    described = describe_config(ambient)

    assert described["values"]["enable_curve_alignment"] is True
    assert described["fileDefaults"]["enable_curve_alignment"] is False
    assert "snap_to_coastline" in described["switches"]
    # Must survive the trip to the browser.
    json.dumps(described)


def test_non_ambient_run_does_not_win_best(tmp_path, monkeypatch):
    """`zones_best` must not mix a snapped run with an unsnapped one."""
    import app.utils.dev_test as dev_test
    from app.utils.dev_test_evaluator import build_test_case_paths

    test_id, case_id = "promo", "case"
    assets_root = tmp_path / "assets"
    paths = build_test_case_paths(str(assets_root), test_id, case_id)
    os.makedirs(paths.case_dir, exist_ok=True)

    with open(paths.extracted_zones_path, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": []}, f)

    # A previous, ambient run that scored worse.
    with open(paths.best_report_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": {"scoreUsed": 0.5}}, f)

    def fake_evaluate(*_args, **_kwargs):
        return {"metrics": {"scoreUsed": 0.99}}, {
            "type": "FeatureCollection",
            "features": [],
        }

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


def test_gcp_sources_override_is_a_subset_in_canonical_order():
    from app.utils.georeferencing.config import parse_config_overrides

    assert parse_config_overrides({"gcp_sources": ["city"]}) == {
        "gcp_sources": ("city",)
    }
    # Order-insensitive, so the same selection always compares equal to the
    # ambient value and a re-ticked "both" stays a promotable run.
    assert parse_config_overrides({"gcp_sources": ["city", "sift"]}) == {
        "gcp_sources": ("sift", "city")
    }
    for bad in ([], ["manual"], ["sift", "sift"], "sift", [1], None):
        with pytest.raises(ValueError):
            parse_config_overrides({"gcp_sources": bad})


def test_describe_config_offers_the_sources_as_checkboxes():
    from app.utils.georeferencing.config import GCP_SOURCES, describe_config

    described = describe_config(DEFAULT_GEOREF_CONFIG)
    assert described["multiChoices"]["gcp_sources"] == list(GCP_SOURCES)
    assert described["values"]["gcp_sources"] == GCP_SOURCES


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


def test_control_points_are_counted_over_the_selected_sources_only():
    """7 SIFT points and 2 cities: SIFT-only and both run, cities-only cannot."""
    inputs = _case_inputs(n_sift=7, n_city=2)

    assert _state(inputs, ("sift", "city")).runnable
    assert _state(inputs, ("sift",)).runnable

    cities_only = _state(inputs, ("city",))
    assert not cities_only.runnable
    assert _status(cities_only, "controlPoints") is RequirementStatus.BLOCKED
    assert "2 point(s) from city" in next(
        s.detail for s in cities_only.requirements.states if s.key == "controlPoints"
    )


def test_cities_are_optional_and_reported():
    without = _state(_case_inputs(n_sift=4, n_city=0), ("sift", "city"))
    assert without.runnable
    assert _status(without, "cityControlPoints") is RequirementStatus.ABSENT

    with_cities = _state(_case_inputs(n_sift=4, n_city=3), ("sift", "city"))
    assert _status(with_cities, "cityControlPoints") is RequirementStatus.SATISFIED
    assert with_cities.to_dict()["controlPointsBySource"] == {"sift": 4, "city": 3}


def test_a_rerun_with_too_few_points_for_its_sources_is_refused_before_dispatch(
    tmp_path, monkeypatch
):
    """"Cities only" on a case without cities is a 400 naming the reason, not a
    task that fails in the worker log."""
    import app.utils.dev_test as dev_test
    from app.tasks import process_dev_test_extraction

    test_id, case_id = "sources-check", "case"
    maps_dir = tmp_path / "maps"
    maps_dir.mkdir()
    (maps_dir / f"{test_id}.jpg").write_bytes(b"never decoded")
    monkeypatch.setattr(dev_test, "MAPS_DIR", str(maps_dir))

    assets_root = tmp_path / "assets"
    case_dir = assets_root / "test_cases" / test_id / case_id
    case_dir.mkdir(parents=True)
    sift = [
        {"source": "sift", "pixel": {"x": float(i), "y": 2.0 * i},
         "geo": {"lon": -70.0 + i, "lat": 50.0}}
        for i in range(4)
    ]
    (case_dir / "config.json").write_text(
        json.dumps(
            {
                "filename": f"{test_id}.jpg",
                "georef": {
                    "controlPoints": sift,
                    "frameBounds": {"west": -80.0, "south": 40.0, "east": -60.0,
                                    "north": 60.0},
                },
                "colors": {"imposed": [{"x": 0.5, "y": 0.5, "name": "Zone",
                                        "radius": 20, "kind": "zone"}]},
            }
        ),
        encoding="utf-8",
    )

    def _no_dispatch(**_kwargs):
        raise AssertionError("the task must not be dispatched")

    monkeypatch.setattr(process_dev_test_extraction, "delay", _no_dispatch)

    with pytest.raises(ValueError, match="controlPoints: 0 point"):
        dev_test._start_extraction_for_case(
            assets_root=str(assets_root),
            test_id=test_id,
            test_case_id=case_id,
            config_overrides={"gcp_sources": ("city",)},
        )


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
    # ...but it is not something the pipeline needs in order to execute.
    assert report.blocks_execution == ()


def test_scored_case_without_legend_answer_cannot_run():
    from app.utils.dev_test_cases import KIND_REGRESSION

    state = _legend_state(KIND_REGRESSION, legend_answered=False)
    assert not state.runnable
    assert [s.key for s in state.run_blockers] == ["legend"]


def test_probe_without_legend_answer_runs_with_a_warning():
    state = _legend_state(KIND_PROBE, legend_answered=False)
    assert state.runnable
    assert [s.key for s in state.warnings] == ["legend"]
    payload = state.to_dict()
    assert payload["runnable"] is True
    assert payload["warnings"] == ["legend"]
    assert any("legend" in line for line in state.summary_lines())


def test_probe_still_stops_on_inputs_the_pipeline_cannot_run_without():
    from types import SimpleNamespace

    from app.utils.dev_test_cases import build_case_state

    inputs = _case_inputs(n_sift=4, n_city=0)
    inputs = SimpleNamespace(**{**vars(inputs), "imposed_click_positions": None})
    state = build_case_state(
        test_id="no-such-map",
        test_case_id="case",
        inputs=inputs,
        image_path="unused.png",
        config=DEFAULT_GEOREF_CONFIG,
        case_config={},
        kind=KIND_PROBE,
    )
    assert not state.runnable
    assert [s.key for s in state.run_blockers] == ["zonePicks"]


def test_no_legend_is_an_answer():
    from app.utils.dev_test import parse_extraction_inputs

    config = {"georef": {"legend": {"present": False, "bounds": None}}}
    inputs = parse_extraction_inputs(config, "map.png")
    assert inputs.legend_answered is True
    assert inputs.legend_bounds is None

    unanswered = parse_extraction_inputs({"georef": {}}, "map.png")
    assert unanswered.legend_answered is False
