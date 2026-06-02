-- Migration: 001_init_postgres
-- Idempotent. Safe to run multiple times.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS goods (
    goods_id        TEXT PRIMARY KEY,
    family          TEXT NOT NULL DEFAULT '',
    knife_type      TEXT NOT NULL DEFAULT '',
    skin_name       TEXT NOT NULL DEFAULT '',
    condition       TEXT NOT NULL DEFAULT '',
    reference_price DOUBLE PRECISION,
    image_url       TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id              BIGSERIAL PRIMARY KEY,
    ts              TEXT        NOT NULL,
    goods_id        TEXT        NOT NULL REFERENCES goods(goods_id) ON DELETE CASCADE,
    price           DOUBLE PRECISION NOT NULL,
    listings        INTEGER     NOT NULL DEFAULT 0,
    buy_orders      INTEGER     NOT NULL DEFAULT 0,
    observed_orders INTEGER     NOT NULL DEFAULT 0,
    UNIQUE (ts, goods_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_goods_ts ON snapshots (goods_id, ts);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts       ON snapshots (ts);

INSERT INTO schema_migrations (version) VALUES ('001_init_postgres')
    ON CONFLICT (version) DO NOTHING;
