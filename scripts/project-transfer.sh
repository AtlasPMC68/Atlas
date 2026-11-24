#!/usr/bin/env bash
# Export / import of an Atlas project. See Backend-Atlas/scripts/project_transfer.py.
#
#   Local:   npm run export                         -> exports/<projet>_<date>.json
#   Server:  npm run import -- exports/<fichier>.json
#            (or ./scripts/project-transfer.sh import <fichier>.json without npm)
#
# Runs in a one-off backend container: it gets the same DATABASE_URL and the
# media-data volume (reference images) as the backend. The script is mounted
# from this checkout, so no image rebuild is needed after updating it.
set -euo pipefail

CALLER_DIR="${INIT_CWD:-$PWD}"   # npm runs scripts from the repo root
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
    echo "Usage: $0 export [--project-id <uuid>]"
    echo "       $0 import <fichier.json> [--owner demo] [--yes]"
    exit 1
}

RUN=(docker compose run --rm --no-deps
     -v "$ROOT/Backend-Atlas/scripts:/app/scripts:ro")

cmd="${1:-}"
[ $# -gt 0 ] && shift

case "$cmd" in export|import) ;; *) usage ;; esac

# The one-off container reaches the database by its service name: the stack
# (at least db) has to be up, and this script never starts it on its own.
if [ -z "$(docker compose ps -q --status running db 2>/dev/null)" ]; then
    echo "[ERREUR] La base de données (service db) n'est pas démarrée." >&2
    echo "         Lance d'abord la stack : docker compose up -d" >&2
    exit 1
fi

case "$cmd" in
    export)
        mkdir -p "$ROOT/exports"
        "${RUN[@]}" -v "$ROOT/exports:/exports" \
            backend python scripts/project_transfer.py export --out-dir /exports "$@"
        ;;
    import)
        file="${1:-}"
        [ -n "$file" ] || usage
        shift
        case "$file" in /*) ;; *) file="$CALLER_DIR/$file" ;; esac
        [ -f "$file" ] || { echo "[ERREUR] Fichier introuvable : $file" >&2; exit 1; }
        "${RUN[@]}" -v "$file:/import/project.json:ro" \
            backend python scripts/project_transfer.py import /import/project.json "$@"
        ;;
    *)
        usage
        ;;
esac
