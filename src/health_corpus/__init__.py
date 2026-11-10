"""Health Corpus — longitudinal personal health store, trends, and monitors.

Public, configurable twin of a private health-corpus deployment. Stores
physical readings and optional mental-health journal entries, exposes MCP
tools for bounded windows and deterministic trends, and ships HAE-based
pattern alerts plus narrative digests.
"""

from health_corpus.client import HealthCorpusClient
from health_corpus.models import HealthMetric, MentalHealthEntry

__all__ = ["HealthCorpusClient", "HealthMetric", "MentalHealthEntry"]
