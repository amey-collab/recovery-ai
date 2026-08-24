"""Safely seed a tiny, clearly synthetic RecoverAI dataset.

Examples (run from the repository root):
    python scripts/seed_synthetic_data.py --dry-run
    python scripts/seed_synthetic_data.py --count 4 --allow-production

Production execution requires both APP_ENV=production and the explicit
``--allow-production`` flag.  The command never creates tables; run Alembic
separately as part of deployment.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.main import SessionLocal, settings  # noqa: E402
from app.synthetic_seed import DEFAULT_NAMESPACE, MAX_BUNDLES, seed_synthetic_data  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a small idempotent synthetic RecoverAI dataset")
    parser.add_argument("--count", type=int, default=4, choices=range(1, MAX_BUNDLES + 1))
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--dry-run", action="store_true", help="build and validate rows, then roll back")
    parser.add_argument("--allow-production", action="store_true", help="required when APP_ENV=production")
    args = parser.parse_args()

    is_production = settings.app_env.lower() in {"production", "staging"}
    if is_production and not args.allow_production:
        print("Refusing to seed production/staging without --allow-production", file=sys.stderr)
        return 2

    session = SessionLocal()
    try:
        report = seed_synthetic_data(session, count=args.count, namespace=args.namespace)
        if args.dry_run:
            session.rollback()
            mode = "dry-run (rolled back)"
        else:
            session.commit()
            mode = "committed"
        print(f"Synthetic seed {mode}: requested={report.requested}, created_bundles={report.created_bundles}, skipped_bundles={report.skipped_bundles}")
        print(f"created={report.created}")
        print(f"skipped={report.skipped}")
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())

