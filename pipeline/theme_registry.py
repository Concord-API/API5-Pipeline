DDL = """
CREATE SCHEMA IF NOT EXISTS etl;
CREATE TABLE IF NOT EXISTS etl.theme_registry (
    theme_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    theme_name text NOT NULL UNIQUE,
    first_seen timestamptz NOT NULL DEFAULT now()
);
"""


def ensure(cursor):
    cursor.execute(DDL)


def get_or_create_key(cursor, theme_name):
    cursor.execute(
        "INSERT INTO etl.theme_registry (theme_name) VALUES (%s) "
        "ON CONFLICT (theme_name) DO UPDATE SET theme_name = EXCLUDED.theme_name "
        "RETURNING theme_key",
        (theme_name,),
    )
    return cursor.fetchone()[0]
