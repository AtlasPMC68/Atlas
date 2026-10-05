#!/usr/bin/env python
"""Download Natural Earth administrative borders for the dev-test zone editor.

    python scripts/fetch_natural_earth_borders.py            # countries + states/provinces, 10m
    python scripts/fetch_natural_earth_borders.py --force    # re-download

Into app/geojson/borders/, which app/utils/borders.py indexes. The files are
gitignored: they are only needed while drawing expected zones, and the zones
themselves are what gets committed. Any other admin-0 / admin-1 file (Natural
Earth or geoBoundaries) dropped in the same folder is picked up too.

The plain versions are used, not the "_lakes" ones: lakes are cut out of
expected zones by the cleaning step, with the same lake layer as the pipeline
(app/utils/georeferencing/cleaning.py). Pre-cut lakes from another layer would
disagree with it at every lake shore.
"""

import argparse
import os
import sys
import urllib.request

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
FILES = (
    "ne_10m_admin_0_countries.geojson",  # ~13 MB
    "ne_10m_admin_1_states_provinces.geojson",  # ~41 MB
)
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "geojson", "borders")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Download even if present")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    for name in FILES:
        target = os.path.join(OUT_DIR, name)
        if os.path.exists(target) and not args.force:
            print(f"present  {name}")
            continue
        print(f"fetching {name} ...", flush=True)
        tmp = target + ".part"
        try:
            urllib.request.urlretrieve(f"{BASE}/{name}", tmp)
        except Exception as e:
            print(f"FAILED   {name}: {e}")
            if os.path.exists(tmp):
                os.remove(tmp)
            return 1
        os.replace(tmp, target)
        print(f"saved    {name} ({os.path.getsize(target) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
