# Health Corpus

Longitudinal personal health store with MCP access, Apple Health pattern alerts, and narrative digests. Public, configurable, and free of any one person's private subjects or tooling.

This repository is the public **Health Corpus** (formerly `screddy-health`). It ships durable Postgres storage, subject-scoped windows and trends, MCP tools, plus HAE monitor and twice-weekly digest pipelines.

## What it does

1. **Corpus store** — Upserts physical readings into `health_metrics` and optional journal rows into `mental_health_entries`, scoped by configurable subject ids.
2. **MCP tools** — `list_subjects`, `health_window`, `health_trends`, and `health_breakdown` (optional local LLM summary of a bounded window). Arithmetic stays in Python; the model never invents readings or diagnoses.
3. **Daily monitor** — Pulls Health Auto Export metrics, computes z-scores, runs 17 pattern detectors, writes a JSONL audit log, upserts into the corpus when `DATABASE_URL` is set, and edge-triggers Telegram (+ optional email) on new sickness/emergency patterns.
4. **Twice-weekly digest** — Assembles last-7-days rollups + journal context, posts to your chat endpoint, and delivers a narrative briefing to Telegram.

## Architecture

```
 Apple Watch / iPhone          Health Auto Export companion
        │                              │
        └────────── pushes ────────────┘
                                       │ HTTPS pull
                                       ▼
                          health_corpus.agents.health_monitor
                          ├─ patterns + JSONL audit
                          └─ upsert → Postgres corpus store
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              Telegram alerts   health_corpus.mcp   health_digest
              (+ optional email)  windows/trends     narrative briefing
```

Private personal deployments (for example Shawn's Corpus) stay separate. This package is the generic public shape; personal subject names, pets, private journal collections, and private model adapters do not belong here.

## Quick start

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/)
- [Health Auto Export](https://www.healthyapps.dev/health-auto-export) + companion server (see `services/health-auto-export/README.md`)
- Telegram bot + chat id
- Postgres (recommended for corpus/MCP; optional if you only want JSONL + Telegram)
- A chat endpoint that accepts `POST {url}` with `{"message":"..."}` and returns `{"answer":"..."}`

### Install

```bash
git clone https://github.com/Screddyice/health-corpus
cd health-corpus
uv sync --extra dev
cp .env.example .env
cp config/subjects.example.yaml config/subjects.yaml
```

### Configure subjects

Edit `config/subjects.yaml` (or point `HEALTH_CORPUS_SUBJECTS_CONFIG` at your file). Each subject needs an id, species, sources, and metric map. The built-in default is a single human subject `self` with common Apple Health metrics.

### Migrate the store

```bash
export DATABASE_URL=postgresql://user:pass@host:5432/health_corpus
uv run python -m health_corpus.migrations
```

### Run

```bash
# daily pattern monitor + corpus upsert
uv run python -m health_corpus.agents.health_monitor

# twice-weekly digest (Tue/Sun in HEALTH_CORPUS_TZ)
uv run python -m health_corpus.agents.health_digest

# MCP over stdio
uv run python -m health_corpus.mcp
```

Systemd unit templates live in `deploy/systemd/`.

## Environment

See [`.env.example`](.env.example). Important variables:

| Variable | Purpose |
|---|---|
| `APPLE_HEALTH_REMOTE_BASE_URL` / `APPLE_HEALTH_REMOTE_READ_TOKEN` | HAE companion API |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Alerts and digests |
| `HEALTH_CORPUS_CHAT_URL` / `HEALTH_CORPUS_CHAT_TOKEN` | Digest narrative endpoint |
| `DATABASE_URL` | Durable corpus store |
| `HEALTH_CORPUS_SUBJECTS_CONFIG` | Path to subjects YAML |
| `HEALTH_CORPUS_DEFAULT_SUBJECT` | Subject id used by the HAE monitor writer (default `self`) |
| `HEALTH_CORPUS_LLM_URL` / `HEALTH_CORPUS_LLM_MODEL` | Optional MCP breakdown model |

## MCP contract

- `list_subjects` — configured subjects and metric catalogs
- `health_window(subject, days=30, end_date?)` — raw physical points (+ journal when enabled)
- `health_trends(subject, days=7, end_date?)` — deterministic physical/mental stats
- `health_breakdown(...)` — JSON-only local LLM summary of a supplied window

Tools report data and changes over time. They do not diagnose, prescribe, or invent missing values.

## Package layout

| Path | Role |
|---|---|
| `src/health_corpus/` | Library + agents + MCP |
| `src/health_corpus/client.py` | Postgres upsert/fetch client |
| `src/health_corpus/subjects.py` | Configurable subject registry |
| `src/health_corpus/mcp/` | FastMCP server |
| `src/health_corpus/agents/` | Monitor + digest pipelines |
| `config/subjects.example.yaml` | Example multi-metric subject |
| `deploy/systemd/` | Timer/service templates |

## Tests

```bash
uv sync --extra dev
uv run pytest
```

## License

MIT — see `LICENSE`.
