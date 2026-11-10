"""Apply Health Corpus migrations: ``python -m health_corpus.migrations``."""
from __future__ import annotations

import os
import sys

from health_corpus.migrations.runner import apply_migrations


def main() -> int:
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("HEALTH_CORPUS_DATABASE_URL")
    if not dsn:
        print("Set DATABASE_URL or HEALTH_CORPUS_DATABASE_URL", file=sys.stderr)
        return 2
    count = apply_migrations(dsn)
    print(f"applied {count} migration(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
