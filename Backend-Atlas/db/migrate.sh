#!/bin/sh
# Applies the SQL migrations in this folder, in filename order, each one once.
#
# Runs as the `migrate` service on every `docker compose up` (local and server),
# before the backend and the workers start. Applied files are recorded in the
# schema_migrations table, so an existing database only receives the new ones:
# a schema change never requires dropping the volume.
#
# Each file runs in its own transaction together with its bookkeeping row: if a
# statement fails, nothing from that file is kept and the deploy stops here.
#
# Connection comes from the standard libpq variables: PGHOST, PGUSER,
# PGPASSWORD, PGDATABASE.
set -eu

MIGRATIONS_DIR="${MIGRATIONS_DIR:-$(dirname "$0")}"
PSQL="psql -X -q -v ON_ERROR_STOP=1"
# Hide the "already exists, skipping" notices of idempotent statements
export PGOPTIONS="${PGOPTIONS:--c client_min_messages=warning}"

echo "[migrate] Waiting for ${PGHOST:-localhost}..."
until pg_isready -q; do sleep 1; done

$PSQL <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename   TEXT PRIMARY KEY,
  checksum   TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
SQL

applied=0
for file in "$MIGRATIONS_DIR"/*.sql; do
  [ -e "$file" ] || continue
  name=$(basename "$file")
  sum=$(sha256sum "$file" | cut -d' ' -f1)
  recorded=$($PSQL -tA -v name="$name" <<'SQL'
SELECT checksum FROM schema_migrations WHERE filename = :'name';
SQL
)

  if [ -n "$recorded" ]; then
    # Editing an applied file has no effect on databases that already ran it
    if [ "$recorded" != "$sum" ]; then
      echo "[migrate] WARNING: $name changed after being applied. Put schema changes in a new file instead."
    fi
    continue
  fi

  echo "[migrate] Applying $name"
  $PSQL --single-transaction -v name="$name" -v sum="$sum" -f "$file" -f - <<'SQL'
INSERT INTO schema_migrations (filename, checksum) VALUES (:'name', :'sum');
SQL
  applied=$((applied + 1))
done

echo "[migrate] Done: $applied applied, database up to date."
