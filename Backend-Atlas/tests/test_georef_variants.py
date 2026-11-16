"""The variant runner's contract (scripts/run_georef_variants.py)."""

import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if not os.path.isdir(_SCRIPTS):
    pytest.skip("scripts/ is not mounted in this container", allow_module_level=True)
sys.path.insert(0, _SCRIPTS)

from app.utils.georeferencing import DEFAULT_GEOREF_CONFIG  # noqa: E402
from app.utils.georeferencing.config import parse_config_overrides  # noqa: E402
from georef_variants import BY_NAME, VARIANTS  # noqa: E402


def test_every_variant_is_a_valid_config():
    """A misspelt override would otherwise fail mid-run, or worse, if the
    parser dropped it, run as the baseline under another name."""
    assert len(BY_NAME) == len(VARIANTS)
    for variant in VARIANTS:
        parsed = parse_config_overrides(dict(variant.overrides))
        assert set(parsed) == set(variant.overrides), variant.name
        DEFAULT_GEOREF_CONFIG.with_overrides(**variant.overrides)


