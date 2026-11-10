"""Typed, date-bounded health windows for Health Corpus."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from health_corpus.subjects import get_subject


class MetricPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    date: date
    metric: str
    value: float
    unit: str


class HealthWindow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    species: str
    end_date: date
    days: int = Field(ge=1, le=90)
    points: tuple[MetricPoint, ...]


def _row_day(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return datetime.fromisoformat(str(raw)).date()
    except ValueError:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            return None


def build_health_window(
    client: Any,
    subject_id: str,
    end_date: date,
    *,
    days: int = 30,
) -> HealthWindow:
    """Build one subject's date-bounded window from allowed health sources."""
    subject = get_subject(subject_id)
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")

    start_date = end_date - timedelta(days=days - 1)
    points: list[MetricPoint] = []
    for metric, spec in subject.metrics.items():
        rows = client.fetch_health_metrics(
            metric,
            subject_id=subject_id,
            days=days + 2,
            end_date=end_date,
            sources=subject.sources,
        )
        for row in rows:
            row_day = _row_day(row.get("date"))
            value = row.get("value")
            unit = row.get("unit") or spec.unit
            if row_day is None or value is None or not unit:
                continue
            if start_date <= row_day <= end_date:
                points.append(
                    MetricPoint(
                        date=row_day,
                        metric=metric,
                        value=float(value),
                        unit=str(unit),
                    )
                )
    points.sort(key=lambda point: (point.date, point.metric))
    return HealthWindow(
        subject=subject_id,
        species=subject.species,
        end_date=end_date,
        days=days,
        points=tuple(points),
    )
