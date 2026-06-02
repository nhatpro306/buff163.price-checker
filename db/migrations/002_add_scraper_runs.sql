-- Migration: 002_add_scraper_runs
-- Idempotent. Safe to run multiple times.
-- Tracks one row per scraper execution for audit and alerting.

CREATE TABLE IF NOT EXISTS scraper_runs (
    run_id          TEXT        PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    backend         TEXT        NOT NULL DEFAULT 'postgres',
    total_items     INTEGER     NOT NULL DEFAULT 0,
    success_count   INTEGER     NOT NULL DEFAULT 0,
    failure_count   INTEGER     NOT NULL DEFAULT 0,
    skipped_count   INTEGER     NOT NULL DEFAULT 0,
    status          TEXT        NOT NULL DEFAULT 'running',
    error_summary   TEXT        NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_started_at ON scraper_runs (started_at DESC);

INSERT INTO schema_migrations (version) VALUES ('002_add_scraper_runs')
    ON CONFLICT (version) DO NOTHING;
