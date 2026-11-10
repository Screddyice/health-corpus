"""Configurable subject registry for the health corpus."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

Species = Literal["human", "canine", "other"]


@dataclass(frozen=True)
class MetricSpec:
    label: str
    aggregate: str = "avg"
    unit: str = ""


@dataclass(frozen=True)
class SubjectConfig:
    id: str
    display_name: str
    species: Species
    sources: tuple[str, ...]
    metrics: dict[str, MetricSpec]
    include_mental_health: bool = False


DEFAULT_SUBJECTS: dict[str, SubjectConfig] = {
    "self": SubjectConfig(
        id="self",
        display_name="Me",
        species="human",
        sources=("apple_health",),
        include_mental_health=True,
        metrics={
            "step_count": MetricSpec("Steps", "sum", "count"),
            "distance_walking_running": MetricSpec("Distance", "sum", "km"),
            "flights_climbed": MetricSpec("Flights climbed", "sum", "count"),
            "walking_speed": MetricSpec("Walking speed", "avg", "m/s"),
            "walking_asymmetry_percentage": MetricSpec(
                "Gait asymmetry", "avg", "percent"
            ),
            "active_energy": MetricSpec("Active energy", "sum", "kcal"),
            "apple_exercise_time": MetricSpec("Exercise", "sum", "min"),
            "heart_rate_variability": MetricSpec("HRV", "avg", "ms"),
            "resting_heart_rate": MetricSpec("Resting heart rate", "avg", "bpm"),
            "blood_oxygen_saturation": MetricSpec("Blood oxygen", "avg", "percent"),
            "sleep_analysis": MetricSpec("Sleep", "sum", "hours"),
            "respiratory_rate": MetricSpec(
                "Respiratory rate", "avg", "breaths_per_min"
            ),
            "basal_body_temperature": MetricSpec(
                "Wrist temperature", "avg", "celsius"
            ),
        },
    )
}


def _parse_subjects(payload: dict[str, Any]) -> dict[str, SubjectConfig]:
    rows = payload.get("subjects")
    if not isinstance(rows, list) or not rows:
        raise ValueError("subjects config must contain a non-empty subjects list")
    out: dict[str, SubjectConfig] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each subject must be a mapping")
        subject_id = str(row["id"]).strip()
        if not subject_id:
            raise ValueError("subject id must be non-empty")
        metrics_raw = row.get("metrics") or {}
        metrics = {
            str(metric_id): MetricSpec(
                label=str(spec.get("label", metric_id)),
                aggregate=str(spec.get("aggregate", "avg")),
                unit=str(spec.get("unit", "")),
            )
            for metric_id, spec in metrics_raw.items()
        }
        if not metrics:
            raise ValueError(f"subject {subject_id!r} needs at least one metric")
        sources = tuple(str(s) for s in (row.get("sources") or ["apple_health"]))
        species = str(row.get("species", "human"))
        if species not in ("human", "canine", "other"):
            raise ValueError(f"unsupported species {species!r}")
        out[subject_id] = SubjectConfig(
            id=subject_id,
            display_name=str(row.get("display_name") or subject_id),
            species=species,  # type: ignore[arg-type]
            sources=sources,
            metrics=metrics,
            include_mental_health=bool(row.get("include_mental_health", False)),
        )
    return out


def subjects_config_path() -> Path | None:
    raw = os.environ.get("HEALTH_CORPUS_SUBJECTS_CONFIG", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


@lru_cache(maxsize=4)
def load_subjects(path: str | None = None) -> dict[str, SubjectConfig]:
    """Load subjects from YAML, or the built-in single-human default."""
    cfg_path = Path(path).expanduser() if path else subjects_config_path()
    if cfg_path is None:
        return dict(DEFAULT_SUBJECTS)
    if not cfg_path.is_file():
        raise FileNotFoundError(f"subjects config not found: {cfg_path}")
    payload = yaml.safe_load(cfg_path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError("subjects config root must be a mapping")
    return _parse_subjects(payload)


def get_subject(subject_id: str) -> SubjectConfig:
    subjects = load_subjects()
    if subject_id not in subjects:
        known = ", ".join(sorted(subjects)) or "(none)"
        raise ValueError(f"unknown subject {subject_id!r}; configured: {known}")
    return subjects[subject_id]


def list_subject_ids() -> tuple[str, ...]:
    return tuple(sorted(load_subjects()))


def clear_subjects_cache() -> None:
    load_subjects.cache_clear()
