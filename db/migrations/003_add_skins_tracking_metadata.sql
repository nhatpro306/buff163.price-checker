-- Migration: 003_add_skins_tracking_metadata
-- Idempotent. Adds normalized skin metadata and deployment/runtime tracking.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'snapshots'
          AND column_name = 'ts'
          AND data_type IN ('text', 'character varying')
    ) THEN
        ALTER TABLE snapshots
            ALTER COLUMN ts TYPE TIMESTAMPTZ USING ts::timestamptz;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS skins (
    skin_id      BIGSERIAL PRIMARY KEY,
    family       TEXT NOT NULL DEFAULT '',
    knife_type   TEXT NOT NULL DEFAULT '',
    skin_name    TEXT NOT NULL DEFAULT '',
    condition    TEXT NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (family, knife_type, skin_name, condition)
);

CREATE INDEX IF NOT EXISTS idx_skins_family_condition ON skins (family, condition);

INSERT INTO skins (family, knife_type, skin_name, condition)
SELECT DISTINCT family, knife_type, skin_name, condition
FROM goods
ON CONFLICT (family, knife_type, skin_name, condition) DO UPDATE SET
    updated_at = NOW();

CREATE TABLE IF NOT EXISTS tracking_metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO tracking_metadata (key, value)
VALUES
    ('timestamp_timezone', 'UTC'),
    ('storage_backend', 'postgres')
ON CONFLICT (key) DO UPDATE SET
    value = EXCLUDED.value,
    updated_at = NOW();

INSERT INTO schema_migrations (version) VALUES ('003_add_skins_tracking_metadata')
    ON CONFLICT (version) DO NOTHING;
