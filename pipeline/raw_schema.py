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
CREATE TABLE IF NOT EXISTS raw.stj_precedent (
    kind TEXT NOT NULL,
    number INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL,
    PRIMARY KEY (kind, number)
);
CREATE TABLE IF NOT EXISTS raw.stj_ruling (
    id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    source_url TEXT NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS raw.court_site_case (
    court TEXT NOT NULL,
    case_number TEXT NOT NULL,
    court_level TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('found', 'not_found', 'sealed')),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL,
    PRIMARY KEY (court, case_number)
);
"""


def ensure(cursor):
    cursor.execute(DDL)
