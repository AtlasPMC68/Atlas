import os

# This module centralizes on-disk paths for the georef dev-test harness.
# Everything is rooted under Backend-Atlas/tests/assets/georef.

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT_DIR = os.path.dirname(_APP_DIR)
_TEST_ASSETS_DIR = os.path.join(_PROJECT_ROOT_DIR, "tests", "assets")

# Dedicated root for georef dev-test assets.
GEOREF_ASSETS_DIR = os.path.join(_TEST_ASSETS_DIR, "georef")

# Canonical locations
ZONES_DIR = os.path.join(GEOREF_ASSETS_DIR, "georef_zones")
MAPS_DIR = os.path.join(GEOREF_ASSETS_DIR, "maps")
TEST_CASES_DIR = os.path.join(GEOREF_ASSETS_DIR, "test_cases")
TESTS_METADATA_PATH = os.path.join(GEOREF_ASSETS_DIR, "tests_metadata.json")


def ensure_georef_assets_dir() -> None:
    os.makedirs(GEOREF_ASSETS_DIR, exist_ok=True)
