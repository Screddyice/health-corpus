-- Health Corpus baseline schema.
-- Subject-scoped physical readings + optional mental-health journal entries.
-- No company roles, vector tables, or personal deployment assumptions.

CREATE TABLE IF NOT EXISTS subjects (
    id            text PRIMARY KEY,
    display_name  text NOT NULL,
    species       text NOT NULL CHECK (species IN ('human', 'canine', 'other')),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS health_metrics (
    id          uuid PRIMARY KEY,
    subject_id  text NOT NULL REFERENCES subjects(id),
    metric      text NOT NULL,
    date        timestamptz NOT NULL,
    value       double precision NOT NULL,
    unit        text NOT NULL,
    source      text NOT NULL DEFAULT 'apple_health',
    raw         jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION health_metrics_day_utc(ts timestamptz)
RETURNS date
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT (ts AT TIME ZONE 'UTC')::date;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS health_metrics_subject_metric_day_source_uidx
    ON health_metrics (subject_id, metric, health_metrics_day_utc(date), source);

CREATE INDEX IF NOT EXISTS health_metrics_subject_date_idx
    ON health_metrics (subject_id, date DESC);

CREATE TABLE IF NOT EXISTS mental_health_entries (
    id                 uuid PRIMARY KEY,
    subject_id         text NOT NULL REFERENCES subjects(id),
    entry_date         date NOT NULL,
    title              text NOT NULL DEFAULT '',
    body               text NOT NULL,
    source             text NOT NULL DEFAULT 'journal',
    collection         text,
    source_entry_path  text,
    raw                jsonb NOT NULL DEFAULT '{}',
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS mental_health_entries_subject_source_path_uidx
    ON mental_health_entries (subject_id, source_entry_path)
    WHERE source_entry_path IS NOT NULL;

CREATE INDEX IF NOT EXISTS mental_health_entries_subject_date_idx
    ON mental_health_entries (subject_id, entry_date DESC);

CREATE TABLE IF NOT EXISTS writes_audit (
    id              uuid PRIMARY KEY,
    actor           text NOT NULL,
    operation       text NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    entity_kind     text NOT NULL,
    entity_id       uuid NOT NULL,
    before          jsonb,
    after           jsonb,
    timestamp       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS writes_audit_entity_idx
    ON writes_audit (entity_kind, entity_id, timestamp DESC);
