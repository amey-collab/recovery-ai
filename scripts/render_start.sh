#!/usr/bin/env bash
set -eu

# Render supplies PORT at runtime. Keep this wrapper limited to an optional,
# one-time seed followed by the long-running web process.
: "${PORT:?PORT must be configured by Render}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ "${RUN_SYNTHETIC_SEED:-false}" = "true" ]; then
  # The seeder is bounded, idempotent, and requires an explicit production
  # acknowledgement. With `set -e`, any seed failure stops startup.
  python "$ROOT_DIR/scripts/seed_synthetic_data.py" --count 4 --allow-production
fi

cd "$ROOT_DIR/backend"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
