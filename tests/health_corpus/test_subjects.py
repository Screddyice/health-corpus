"""Subject config loading."""
from __future__ import annotations

from pathlib import Path

import pytest

from health_corpus.subjects import clear_subjects_cache, get_subject, load_subjects


def test_default_subject_self():
    clear_subjects_cache()
    subject = get_subject("self")
    assert subject.species == "human"
    assert "step_count" in subject.metrics
    assert subject.include_mental_health is True


def test_custom_subjects_yaml(tmp_path, monkeypatch):
    clear_subjects_cache()
    path = tmp_path / "subjects.yaml"
    path.write_text(
        """
subjects:
  - id: alex
    display_name: Alex
    species: human
    sources: [apple_health]
    include_mental_health: false
    metrics:
      step_count:
        label: Steps
        aggregate: sum
        unit: count
"""
    )
    monkeypatch.setenv("HEALTH_CORPUS_SUBJECTS_CONFIG", str(path))
    clear_subjects_cache()
    subjects = load_subjects()
    assert list(subjects) == ["alex"]
    assert get_subject("alex").display_name == "Alex"
    with pytest.raises(ValueError):
        get_subject("self")
    clear_subjects_cache()
