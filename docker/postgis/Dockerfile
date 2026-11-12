# PostGIS on the official multi-arch postgres image.
# postgis/postgis only publishes amd64 images, which don't run on the ARM64 VM.
FROM postgres:17.11-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       postgresql-17-postgis-3 \
       postgresql-17-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
