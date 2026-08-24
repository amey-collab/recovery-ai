#!/usr/bin/env bash
set -eu

# Render Free plan has no pre-deploy command. Run migrations after dependencies
# are installed, before the web service starts. DATABASE_URL is supplied by
# Render and is intentionally never echoed.
: "${DATABASE_URL:?DATABASE_URL must be configured in Render}"

python -m pip install -r backend/requirements.txt
(cd backend && python -m alembic upgrade head)
