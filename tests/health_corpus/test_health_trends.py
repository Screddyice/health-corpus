"""Deterministic trend helpers."""
from __future__ import annotations

from datetime import date, timedelta

from health_corpus.health_trends import compare_windows


def test_compare_windows_up_trend():
    end = date(2026, 11, 9)
    start = end - timedelta(days=6)
    rows = []
    for i in range(14):
        day = end - timedelta(days=13 - i)
        value = 1000 + i * 100
        rows.append({"date": day.isoformat(), "value": value})
    week = compare_windows(
        rows, start=start, end=end, how="sum", unit="count", metric="step_count"
    )
    assert week.coverage == 7
    assert week.prior_coverage == 7
    assert week.trend in {"up", "flat"}
    assert week.this_week is not None and week.last_week is not None
    assert week.this_week > week.last_week
