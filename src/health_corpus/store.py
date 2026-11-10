"""Helpers that bridge the HAE monitor/digest pipelines into the corpus store.

Gracefully no-op when DATABASE_URL is unset so JSONL-only installs still work.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime
from typing import Optional

from health_corpus.client import HealthCorpusClient

logger = logging.getLogger(__name__)

_UNIT_MAP = {
    "step_count": "count",
    "flights_climbed": "count",
    "active_energy": "kcal",
    "apple_exercise_time": "min",
    "apple_stand_time": "min",
    "mindful_session": "min",
    "resting_heart_rate": "bpm",
    "walking_heart_rate_average": "bpm",
    "heart_rate_variability": "ms",
    "sleep_analysis": "hours",
    "blood_oxygen_saturation": "percent",
    "walking_asymmetry_percentage": "percent",
    "apple_walking_steadiness": "percent",
    "respiratory_rate": "breaths_per_min",
    "walking_speed": "m_per_s",
    "vo2_max": "ml_kg_min",
    "basal_body_temperature": "celsius",
    "distance_walking_running": "km",
    "irregular_heart_rhythm_event": "events",
    "high_heart_rate_event": "events",
    "low_heart_rate_event": "events",
}


def database_url() -> Optional[str]:
    return os.environ.get("DATABASE_URL") or os.environ.get(
        "HEALTH_CORPUS_DATABASE_URL"
    )


def default_subject_id() -> str:
    return os.environ.get("HEALTH_CORPUS_DEFAULT_SUBJECT", "self")


def _scrub_for_jsonb(value):
    if isinstance(value, dict):
        return {k: _scrub_for_jsonb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_for_jsonb(x) for x in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_health_metrics(
    daily_per_metric: dict[str, dict[str, float]],
    findings: dict,
    *,
    run_at: datetime,
    source: str = "apple_health",
    subject_id: str | None = None,
) -> int:
    """Upsert one row per metric for today's run into the corpus store."""
    if not daily_per_metric or not database_url():
        return 0
    subject = subject_id or default_subject_id()
    try:
        client = HealthCorpusClient.from_env()
    except Exception as exc:
        logger.warning("health corpus client unavailable: %s", exc)
        return 0
    written = 0
    try:
        for metric_id, daily in daily_per_metric.items():
            if not daily:
                continue
            sorted_days = sorted(daily.keys())
            latest_value = daily[sorted_days[-1]]
            if isinstance(latest_value, float) and (
                math.isnan(latest_value) or math.isinf(latest_value)
            ):
                continue
            finding = findings.get(metric_id) or {}
            client.upsert_health_metric(
                subject_id=subject,
                metric=metric_id,
                value=float(latest_value),
                unit=_UNIT_MAP.get(metric_id, "unknown"),
                date=run_at,
                source=source,
                raw={
                    "latest_day": sorted_days[-1],
                    "days_in_window": len(sorted_days),
                    "finding": _scrub_for_jsonb(finding),
                },
            )
            written += 1
    except Exception as exc:
        logger.warning("health_metrics write failed: %s", exc)
        return written
    finally:
        client.close()
    return written


def load_recent_mental_health_entries(
    *,
    days: int = 7,
    limit: int = 14,
    subject_id: str | None = None,
) -> list[dict]:
    """Read recent mental-health journal entries for digest prompts."""
    if not database_url():
        return []
    subject = subject_id or default_subject_id()
    try:
        client = HealthCorpusClient.from_env()
    except Exception as exc:
        logger.warning("health corpus client unavailable: %s", exc)
        return []
    try:
        rows = client.fetch_mental_health_entries(
            subject_id=subject,
            days=days,
        )
    except Exception as exc:
        logger.warning("mental-health entry read failed: %s", exc)
        return []
    finally:
        client.close()

    out: list[dict] = []
    for row in reversed(rows):
        out.append(
            {
                "entry_date": row.get("date"),
                "text": row.get("body") or "",
                "title": row.get("title") or "",
                "created_at": None,
                "tags": ["mental-health", "journal"],
            }
        )
        if len(out) >= limit:
            break
    return out
