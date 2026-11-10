"""Deterministic physical-health trend statistics from corpus rows."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from health_corpus.subjects import SubjectConfig, get_subject

MIN_DAYS_FOR_TREND = 4


@dataclass
class MetricWeek:
    metric: str
    unit: str
    this_week: float | None
    last_week: float | None
    delta: float | None
    delta_pct: float | None
    coverage: int
    prior_coverage: int
    trend: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _aggregate_by_day(rows: Iterable[dict], how: str) -> dict[date, float]:
    buckets: dict[date, list[float]] = {}
    for row in rows:
        raw_date = row.get("date")
        if not raw_date or row.get("value") is None:
            continue
        try:
            day = datetime.fromisoformat(str(raw_date)).date()
        except ValueError:
            try:
                day = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
        buckets.setdefault(day, []).append(float(row["value"]))
    out: dict[date, float] = {}
    for day, values in buckets.items():
        if how == "sum":
            out[day] = sum(values)
        else:
            out[day] = sum(values) / len(values)
    return out


def _trend_label(delta_pct: float | None, coverage: int) -> str:
    if coverage < MIN_DAYS_FOR_TREND or delta_pct is None:
        return "insufficient-data"
    if abs(delta_pct) < 5:
        return "flat"
    return "up" if delta_pct > 0 else "down"


def compare_windows(
    rows: list[dict],
    *,
    start: date,
    end: date,
    how: str,
    unit: str,
    metric: str,
) -> MetricWeek:
    span = (end - start).days + 1
    prior_start = start - timedelta(days=span)
    by_day = _aggregate_by_day(rows, how)
    current_days = {
        day: value for day, value in by_day.items() if start <= day <= end
    }
    prior_days = {
        day: value
        for day, value in by_day.items()
        if prior_start <= day <= start - timedelta(days=1)
    }

    def mean_or_none(values: dict[date, float]) -> float | None:
        if not values:
            return None
        return sum(values.values()) / len(values)

    current = mean_or_none(current_days)
    prior = mean_or_none(prior_days)
    delta = current - prior if current is not None and prior is not None else None
    delta_pct = (delta / abs(prior)) * 100.0 if delta is not None and prior else None
    return MetricWeek(
        metric=metric,
        unit=unit,
        this_week=current,
        last_week=prior,
        delta=delta,
        delta_pct=delta_pct,
        coverage=len(current_days),
        prior_coverage=len(prior_days),
        trend=_trend_label(delta_pct, len(current_days)),
    )


def build_physical_trends(
    client: Any,
    subject_id: str,
    *,
    end_day: date,
    days: int = 7,
) -> dict[str, Any]:
    subject: SubjectConfig = get_subject(subject_id)
    start = end_day - timedelta(days=days - 1)
    metrics: list[dict[str, Any]] = []
    for metric, spec in subject.metrics.items():
        rows = client.fetch_health_metrics(
            metric,
            subject_id=subject_id,
            days=(days * 2) + 2,
            end_date=end_day,
            sources=subject.sources,
        )
        week = compare_windows(
            rows,
            start=start,
            end=end_day,
            how=spec.aggregate,
            unit=spec.unit,
            metric=metric,
        )
        metrics.append(week.as_dict())
    return {
        "domain": "physical_health",
        "window_start": start.isoformat(),
        "window_end": end_day.isoformat(),
        "metrics": metrics,
    }
