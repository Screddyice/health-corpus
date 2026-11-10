"""Pure-Python migration runner for Health Corpus SQL files."""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import psycopg

log = logging.getLogger(__name__)
_MIGRATION_RE = re.compile(r"^(\d{3}_.+)\.sql$")


class MigrationError(RuntimeError):
    """Raised when a migration cannot be safely applied."""


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ensure_schema_migrations(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now(),
            checksum   text NOT NULL
        );
        """
    )


def _discover(sql_dir: Path) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for path in sorted(sql_dir.glob("*.sql")):
        match = _MIGRATION_RE.match(path.name)
        if not match:
            log.warning("ignoring non-conforming migration file: %s", path.name)
            continue
        entries.append((match.group(1), path))
    return entries


def default_sql_dir() -> Path:
    return Path(__file__).resolve().parent / "sql"


def apply_migrations(dsn: str, sql_dir: Path | str | None = None) -> int:
    """Apply unapplied migrations. Returns count newly applied."""
    sql_dir = Path(sql_dir) if sql_dir else default_sql_dir()
    if not sql_dir.is_dir():
        raise MigrationError(f"migrations directory does not exist: {sql_dir}")

    applied_count = 0
    with psycopg.connect(dsn, autocommit=False) as conn:
        _ensure_schema_migrations(conn)
        conn.commit()

        rows = conn.execute(
            "SELECT version, checksum FROM schema_migrations"
        ).fetchall()
        applied_map = {version: checksum for version, checksum in rows}

        for version, path in _discover(sql_dir):
            sql_text = path.read_text()
            expected = _checksum(sql_text)
            if version in applied_map:
                if applied_map[version] != expected:
                    raise MigrationError(
                        f"checksum mismatch for {version}: "
                        f"DB has {applied_map[version][:12]}…, "
                        f"file has {expected[:12]}…"
                    )
                continue
            log.info("applying migration %s", version)
            with conn.transaction():
                conn.execute(sql_text)
                conn.execute(
                    "INSERT INTO schema_migrations (version, checksum) "
                    "VALUES (%s, %s)",
                    (version, expected),
                )
            applied_count += 1
            log.info("applied %s", version)
    return applied_count
