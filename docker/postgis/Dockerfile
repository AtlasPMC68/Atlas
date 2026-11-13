# PostGIS on the official multi-arch postgres image.
# postgis/postgis only publishes amd64 images, which don't run on the ARM64 VM.
#
# Only the major version (17) is pinned. postgresql-17 is installed together
# with PostGIS so apt upgrades the server to the latest 17.x patch at the same
# time: the PostGIS build from the PGDG repo always targets the newest patch,
# and loading it into an older server fails (undefined symbol).
FROM postgres:17-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       postgresql-17 \
       postgresql-17-postgis-3 \
       postgresql-17-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
