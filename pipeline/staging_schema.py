DDL = """
CREATE SCHEMA IF NOT EXISTS staging;
CREATE TABLE IF NOT EXISTS staging.case_event (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_id BIGINT,
    tribunal TEXT NOT NULL,
    case_number TEXT NOT NULL,
    court_level TEXT,
    case_class_code INTEGER,
    case_class_name TEXT,
    judging_body_code TEXT,
    judging_body_name TEXT,
    filed_at TIMESTAMPTZ,
    secrecy_level SMALLINT,
    subjects JSONB,
    movement_code INTEGER NOT NULL,
    movement_name TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL
);
"""


def ensure(cursor):
    cursor.execute(DDL)
