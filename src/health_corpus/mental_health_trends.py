"""Journal cadence and volume statistics — arithmetic only, no diagnosis."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

RECENT_WINDOW_DAYS = 90
MAX_RECENT_ENTRIES = 8
MAX_BODY_CHARS = 1800
MIN_ENTRIES_FOR_CADENCE = 4


@dataclass
class JournalStats:
    total_entries: int
    first_date: str | None
    last_date: str | None
    days_since_last: int | None
    recent_count: int
    prior_count: int
    recent_chars: int
    prior_chars: int
    median_gap_days: float | None
    mean_gap_days: float | None
    longest_gap_days: int | None
    longest_gap_between: tuple[str, str] | None
    per_month: dict[str, int] = field(default_factory=dict)
    recent_entries: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _parse(entries: Iterable[dict]) -> list[dict]:
    out = []
    for entry in entries:
        raw = entry.get("date")
        if not raw:
            continue
        try:
            day = date.fromisoformat(str(raw)[:10])
        except (ValueError, TypeError):
            continue
        out.append({**entry, "_d": day})
    out.sort(key=lambda item: item["_d"])
    return out


def compute(
    entries: Iterable[dict],
    *,
    today: date,
    window_days: int = RECENT_WINDOW_DAYS,
) -> JournalStats:
    rows = _parse(entries)
    if not rows:
        return JournalStats(
            total_entries=0,
            first_date=None,
            last_date=None,
            days_since_last=None,
            recent_count=0,
            prior_count=0,
            recent_chars=0,
            prior_chars=0,
            median_gap_days=None,
            mean_gap_days=None,
            longest_gap_days=None,
            longest_gap_between=None,
        )

    dates = [row["_d"] for row in rows]
    recent_cut = today - timedelta(days=window_days)
    prior_cut = recent_cut - timedelta(days=window_days)
    recent = [row for row in rows if row["_d"] >= recent_cut]
    prior = [row for row in rows if prior_cut <= row["_d"] < recent_cut]

    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    longest_between = None
    longest_gap = None
    if gaps:
        longest_gap = max(gaps)
        idx = gaps.index(longest_gap)
        longest_between = (dates[idx].isoformat(), dates[idx + 1].isoformat())

    per_month: dict[str, int] = {}
    for day in dates:
        key = day.strftime("%Y-%m")
        per_month[key] = per_month.get(key, 0) + 1

    recent_entries = []
    for row in reversed(recent[-MAX_RECENT_ENTRIES:]):
        body = str(row.get("body") or "")[:MAX_BODY_CHARS]
        recent_entries.append(
            {
                "date": row["_d"].isoformat(),
                "title": row.get("title") or "Untitled",
                "body": body,
                "chars": len(body),
            }
        )

    cadence_ready = len(gaps) >= MIN_ENTRIES_FOR_CADENCE - 1
    return JournalStats(
        total_entries=len(rows),
        first_date=dates[0].isoformat(),
        last_date=dates[-1].isoformat(),
        days_since_last=(today - dates[-1]).days,
        recent_count=len(recent),
        prior_count=len(prior),
        recent_chars=sum(len(str(r.get("body") or "")) for r in recent),
        prior_chars=sum(len(str(r.get("body") or "")) for r in prior),
        median_gap_days=statistics.median(gaps) if cadence_ready else None,
        mean_gap_days=statistics.mean(gaps) if cadence_ready else None,
        longest_gap_days=longest_gap if cadence_ready else None,
        longest_gap_between=longest_between if cadence_ready else None,
        per_month=per_month,
        recent_entries=list(reversed(recent_entries)),
    )
