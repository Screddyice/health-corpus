"""Direct health-data client for Health Corpus."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from health_corpus.audit import write_audit_in_txn
from health_corpus.db import close_pool, init_pool
from health_corpus.models import HealthMetric, MentalHealthEntry
from health_corpus.subjects import get_subject


def _parse_health_date(value: str | date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    text = value.replace("Z", "+00:00")
    if "T" in text:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)


class HealthCorpusClient:
    """Health-only Postgres client for physical readings and journal entries."""

    def __init__(self, *, dsn: str, actor: str = "health-corpus"):
        if not dsn:
            raise AssertionError("dsn required")
        self.actor = actor
        self._pool: ConnectionPool = init_pool(dsn)

    @classmethod
    def from_env(cls) -> HealthCorpusClient:
        dsn = os.environ.get("DATABASE_URL") or os.environ.get(
            "HEALTH_CORPUS_DATABASE_URL"
        )
        if not dsn:
            raise RuntimeError(
                "DATABASE_URL or HEALTH_CORPUS_DATABASE_URL must be set"
            )
        return cls(
            dsn=dsn,
            actor=os.environ.get("HEALTH_CORPUS_ACTOR", "health-corpus"),
        )

    def close(self) -> None:
        close_pool(self._pool)

    def ensure_subject(self, subject_id: str) -> None:
        """Insert the configured subject row if missing."""
        subject = get_subject(subject_id)
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                """
                INSERT INTO subjects (id, display_name, species)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET display_name = EXCLUDED.display_name,
                        species = EXCLUDED.species
                """,
                (subject.id, subject.display_name, subject.species),
            )

    def upsert_health_metric(
        self,
        *,
        subject_id: str,
        metric: str,
        value: float,
        unit: str,
        date: str | date | datetime,
        source: str = "apple_health",
        raw: dict | None = None,
    ) -> HealthMetric:
        """Idempotently write one raw physical-health reading."""
        self.ensure_subject(subject_id)
        measured_at = _parse_health_date(date)
        row_id = uuid4()
        now = datetime.now(timezone.utc)
        payload = raw or {}
        with self._pool.connection() as conn, conn.transaction():
            row = conn.execute(
                """
                INSERT INTO health_metrics
                    (id, subject_id, metric, date, value, unit, source, raw, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    subject_id, metric, health_metrics_day_utc(date), source
                ) DO UPDATE
                    SET value = EXCLUDED.value,
                        unit = EXCLUDED.unit,
                        raw = EXCLUDED.raw,
                        created_at = EXCLUDED.created_at
                RETURNING id, subject_id, date, value, unit, source, raw
                """,
                (
                    row_id,
                    subject_id,
                    metric,
                    measured_at,
                    value,
                    unit,
                    source,
                    Jsonb(payload),
                    now,
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError("health metric upsert returned no row")
            actual_id = row[0]
            write_audit_in_txn(
                conn,
                audit_id=uuid4(),
                actor=self.actor,
                operation="UPDATE" if actual_id != row_id else "INSERT",
                entity_kind="HealthMetric",
                entity_id=actual_id,
                before=None,
                after={
                    "subject_id": subject_id,
                    "metric": metric,
                    "date": measured_at.isoformat(),
                    "value": value,
                    "unit": unit,
                    "source": source,
                    "raw": payload,
                },
            )
        return HealthMetric(
            id=row[0],
            subject_id=row[1],
            metric=metric,
            date=row[2],
            value=float(row[3]),
            unit=row[4],
            source=row[5],
            raw=row[6] or {},
        )

    def fetch_health_metrics(
        self,
        metric: str,
        *,
        subject_id: str,
        days: int = 30,
        end_date: date | None = None,
        sources: tuple[str, ...] | None = None,
    ) -> list[dict]:
        if days < 1:
            raise ValueError("days must be at least 1")
        subject = get_subject(subject_id)
        end = end_date or datetime.now(timezone.utc).date()
        start = end - timedelta(days=days - 1)
        use_sources = sources or subject.sources
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT date, value, unit, source, raw
                FROM health_metrics
                WHERE subject_id = %s
                  AND metric = %s
                  AND source = ANY(%s)
                  AND date >= %s::date
                  AND date < (%s::date + INTERVAL '1 day')
                ORDER BY date ASC
                """,
                (subject_id, metric, list(use_sources), start, end),
            ).fetchall()
        return [
            {
                "date": measured_at.isoformat(),
                "value": float(value),
                "unit": unit,
                "source": source,
                "raw": raw or {},
            }
            for measured_at, value, unit, source, raw in rows
        ]

    def fetch_health_window(
        self,
        subject_id: str,
        *,
        end_date: date | None = None,
        days: int = 30,
    ) -> dict:
        if days < 1:
            raise ValueError("days must be at least 1")
        subject = get_subject(subject_id)
        end = end_date or datetime.now(timezone.utc).date()
        start = end - timedelta(days=days - 1)
        with self._pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT date, metric, value, unit, source, raw
                FROM health_metrics
                WHERE subject_id = %s
                  AND source = ANY(%s)
                  AND date >= %s::date
                  AND date < (%s::date + INTERVAL '1 day')
                ORDER BY date ASC, metric ASC
                """,
                (subject_id, list(subject.sources), start, end),
            ).fetchall()
        return {
            "subject": subject_id,
            "display_name": subject.display_name,
            "species": subject.species,
            "end_date": end.isoformat(),
            "days": days,
            "points": [
                {
                    "date": measured_at.date().isoformat(),
                    "metric": metric,
                    "value": float(value),
                    "unit": unit,
                    "source": source,
                    "raw": raw or {},
                }
                for measured_at, metric, value, unit, source, raw in rows
            ],
        }

    def upsert_mental_health_entry(
        self,
        *,
        subject_id: str,
        entry_date: str | date,
        title: str,
        body: str,
        source: str = "journal",
        collection: str | None = None,
        source_entry_path: str | None = None,
        raw: dict | None = None,
    ) -> MentalHealthEntry:
        self.ensure_subject(subject_id)
        entry_day = _parse_health_date(entry_date).date()
        row_id = uuid4()
        now = datetime.now(timezone.utc)
        payload = raw or {}
        with self._pool.connection() as conn, conn.transaction():
            if source_entry_path:
                row = conn.execute(
                    """
                    INSERT INTO mental_health_entries
                        (id, subject_id, entry_date, title, body, source,
                         collection, source_entry_path, raw, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (subject_id, source_entry_path)
                        WHERE source_entry_path IS NOT NULL
                    DO UPDATE
                        SET entry_date = EXCLUDED.entry_date,
                            title = EXCLUDED.title,
                            body = EXCLUDED.body,
                            source = EXCLUDED.source,
                            collection = EXCLUDED.collection,
                            raw = EXCLUDED.raw,
                            created_at = EXCLUDED.created_at
                    RETURNING id, subject_id, entry_date, title, body, source,
                              collection, source_entry_path, raw, created_at
                    """,
                    (
                        row_id,
                        subject_id,
                        entry_day,
                        title,
                        body,
                        source,
                        collection,
                        source_entry_path,
                        Jsonb(payload),
                        now,
                    ),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    INSERT INTO mental_health_entries
                        (id, subject_id, entry_date, title, body, source,
                         collection, source_entry_path, raw, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, subject_id, entry_date, title, body, source,
                              collection, source_entry_path, raw, created_at
                    """,
                    (
                        row_id,
                        subject_id,
                        entry_day,
                        title,
                        body,
                        source,
                        collection,
                        None,
                        Jsonb(payload),
                        now,
                    ),
                ).fetchone()
            if row is None:
                raise RuntimeError("mental-health entry upsert returned no row")
        return MentalHealthEntry(
            id=row[0],
            subject_id=row[1],
            entry_date=datetime.combine(row[2], datetime.min.time(), tzinfo=timezone.utc),
            title=row[3] or "",
            body=row[4],
            source=row[5],
            collection=row[6],
            source_entry_path=row[7],
            raw=row[8] or {},
            created_at=row[9],
        )

    def fetch_mental_health_entries(
        self,
        *,
        subject_id: str,
        days: int = 365,
        end_date: date | None = None,
        collections: tuple[str, ...] | None = None,
    ) -> list[dict]:
        if days < 1:
            raise ValueError("days must be at least 1")
        end = end_date or datetime.now(timezone.utc).date()
        start = end - timedelta(days=days - 1)
        query = (
            "SELECT entry_date, title, body, source, collection, "
            "source_entry_path, raw FROM mental_health_entries "
            "WHERE subject_id = %s AND entry_date BETWEEN %s AND %s"
        )
        params: list[object] = [subject_id, start, end]
        if collections:
            query += " AND collection = ANY(%s)"
            params.append(list(collections))
        query += " ORDER BY entry_date ASC, created_at ASC"
        with self._pool.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "date": entry_day.isoformat(),
                "title": title or "Untitled",
                "body": body,
                "source": source,
                "collection": collection,
                "source_entry_path": source_path,
                "raw": raw or {},
                "chars": len(body or ""),
            }
            for entry_day, title, body, source, collection, source_path, raw in rows
        ]
