"""Health-only MCP surface for Health Corpus.

Tools:
  - health_window — raw physical readings (+ journal when configured)
  - health_trends — deterministic physical/mental pattern stats
  - health_breakdown — optional local LLM summary of a bounded window
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

from health_corpus.client import HealthCorpusClient
from health_corpus.health_trends import build_physical_trends
from health_corpus.mental_health_trends import compute as compute_mental_trends
from health_corpus.subjects import get_subject, list_subject_ids

log = logging.getLogger(__name__)
server = FastMCP("health-corpus")

_client: HealthCorpusClient | None = None
_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.I | re.S)


def _get_client() -> HealthCorpusClient:
    global _client
    if _client is None:
        _client = HealthCorpusClient.from_env()
    return _client


def _parse_day(value: str | date | None) -> date:
    if value is None:
        return datetime.now(timezone.utc).date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError("end_date must be YYYY-MM-DD") from exc


def _require_subject(subject: str):
    return get_subject(subject)


def _journal_rows(
    client: HealthCorpusClient,
    *,
    subject_id: str,
    end_day: date,
    days: int,
) -> list[dict[str, Any]]:
    entries = client.fetch_mental_health_entries(
        subject_id=subject_id,
        days=days,
        end_date=end_day,
    )
    start = end_day - timedelta(days=days - 1)
    out = []
    for row in entries:
        try:
            row_day = date.fromisoformat(str(row.get("date", ""))[:10])
        except (TypeError, ValueError):
            continue
        if start <= row_day <= end_day:
            out.append(
                {
                    "date": row_day.isoformat(),
                    "title": row.get("title") or "Untitled",
                    "body": row.get("body") or "",
                    "chars": int(row.get("chars") or len(row.get("body") or "")),
                    "domain": "mental_health",
                }
            )
    out.sort(key=lambda item: item["date"])
    return out


@server.tool()
def list_subjects() -> dict[str, Any]:
    """Return configured subject ids and display metadata."""
    subjects = []
    for subject_id in list_subject_ids():
        cfg = get_subject(subject_id)
        subjects.append(
            {
                "id": cfg.id,
                "display_name": cfg.display_name,
                "species": cfg.species,
                "sources": list(cfg.sources),
                "include_mental_health": cfg.include_mental_health,
                "metrics": sorted(cfg.metrics),
            }
        )
    return {"subjects": subjects}


@server.tool()
def health_window(
    subject: str,
    days: int = 30,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Return raw physical readings and optional dated journal entries.

    Does not diagnose, invent missing readings, or write to the corpus.
    """
    cfg = _require_subject(subject)
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    end_day = _parse_day(end_date)
    client = _get_client()
    result = client.fetch_health_window(subject, end_date=end_day, days=days)
    result["physical_health"] = {
        "points": result.pop("points", []),
        "domain": "physical_health",
    }
    result["mental_health"] = {
        "entries": (
            _journal_rows(client, subject_id=subject, end_day=end_day, days=days)
            if cfg.include_mental_health
            else []
        ),
        "domain": "mental_health",
    }
    return result


@server.tool()
def health_trends(
    subject: str,
    days: int = 7,
    end_date: Optional[str] = None,
) -> dict[str, Any]:
    """Return deterministic physical and mental-health patterns over a window."""
    cfg = _require_subject(subject)
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    end_day = _parse_day(end_date)
    client = _get_client()
    mental: dict[str, Any]
    if cfg.include_mental_health:
        journal = _journal_rows(
            client, subject_id=subject, end_day=end_day, days=max(days, 90)
        )
        stats = compute_mental_trends(journal, today=end_day, window_days=min(days, 90))
        payload = stats.as_dict()
        payload.pop("recent_entries", None)
        mental = {
            "domain": "mental_health",
            "window_start": (end_day - timedelta(days=days - 1)).isoformat(),
            "window_end": end_day.isoformat(),
            "journal": journal,
            "patterns": payload,
        }
    else:
        mental = {"domain": "mental_health", "journal": [], "patterns": {}}
    return {
        "subject": subject,
        "days": days,
        "physical_health": build_physical_trends(
            client, subject, end_day=end_day, days=days
        ),
        "mental_health": mental,
    }


def _breakdown_prompt(window: dict[str, Any], trends: dict[str, Any]) -> list[dict[str, str]]:
    system = (
        "You are a health-data pattern reader. Return JSON only with exactly "
        "these keys: subject, summary, physical, mental_health, patterns, data_limits. "
        "Use only the supplied raw readings and dated journal entries. Report values "
        "and changes over time; never diagnose, prescribe, or invent missing values. "
        "physical and mental_health must be arrays, patterns must be an array, and "
        "data_limits must list missing or sparse coverage."
    )
    payload = json.dumps({"window": window, "trends": trends}, sort_keys=True, default=str)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": payload},
    ]


def _strict_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    match = _JSON_FENCE.match(text)
    if match:
        text = match.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


@server.tool()
def health_breakdown(
    subject: str,
    days: int = 30,
    end_date: Optional[str] = None,
    max_tokens: int = 700,
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Summarize a bounded health window via a local OpenAI-compatible LLM.

    Configure HEALTH_CORPUS_LLM_URL (chat completions endpoint) and optional
    HEALTH_CORPUS_LLM_MODEL. Never diagnoses or invents readings.
    """
    _require_subject(subject)
    if not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    window = health_window(subject=subject, days=days, end_date=end_date)
    trends = health_trends(subject=subject, days=min(days, 14), end_date=end_date)
    url = os.environ.get(
        "HEALTH_CORPUS_LLM_URL",
        "http://127.0.0.1:8801/v1/chat/completions",
    )
    model = os.environ.get("HEALTH_CORPUS_LLM_MODEL", "local-health-model")
    messages = _breakdown_prompt(window, trends)
    try:
        resp = httpx.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return {
            "subject": subject,
            "error": f"LLM breakdown unavailable: {exc}",
            "window": window,
            "trends": trends,
        }
    parsed = _strict_json(content)
    if parsed is None:
        return {
            "subject": subject,
            "error": "LLM returned non-JSON content",
            "raw": content,
            "window": window,
            "trends": trends,
        }
    return parsed
