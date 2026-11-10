"""Typed records used by the health-only corpus client."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HealthMetric(BaseModel):
    """One raw physical-health reading."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    subject_id: str
    metric: str
    date: datetime
    value: float
    unit: str
    source: str = "apple_health"
    raw: dict = Field(default_factory=dict)


class MentalHealthEntry(BaseModel):
    """One dated journal entry used for mental-health trend analysis."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    subject_id: str
    entry_date: datetime
    title: str = ""
    body: str
    source: str = "journal"
    collection: str | None = None
    source_entry_path: str | None = None
    raw: dict = Field(default_factory=dict)
    created_at: datetime
