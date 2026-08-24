#!/usr/bin/env bash
set -eu

# Render supplies PORT at runtime.  Keep this wrapper limited to process
# startup so the web service never exits after a build/seed task completes.
: "${PORT:?PORT must be configured by Render}"

cd "$(dirname "$0")/../backend"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
