DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE TABLE IF NOT EXISTS raw.datajud_case (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'datajud',
    tribunal TEXT NOT NULL,
    source_url TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE (source, payload_hash)
);
CREATE TABLE IF NOT EXISTS raw.doctrine_article (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE (source, payload_hash)
);
CREATE INDEX IF NOT EXISTS idx_raw_doctrine_collected
    ON raw.doctrine_article (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_doctrine_payload
    ON raw.doctrine_article USING gin (payload jsonb_path_ops);
"""


def ensure(cursor):
    cursor.execute(DDL)
