#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p \
  "$ROOT_DIR/data/input" \
  "$ROOT_DIR/data/intermediate" \
  "$ROOT_DIR/data/result" \
  "$ROOT_DIR/models/hub"

echo "Storage folders are ready."
