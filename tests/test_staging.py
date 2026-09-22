from datetime import datetime, timezone

import psycopg2

from pipeline.staging import load
from pipeline.staging_schema import ensure

NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def row(case_number, movement_code):
    return (
        1, "tjsp", case_number, "First",
        7, "Procedimento Comum Cível",
        "123", "1ª Vara Cível",
        NOW, 0, "[]",
        movement_code, "Procedência", NOW,
        "datajud", "https://x", NOW,
    )


def fetch_all(dsn):
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT case_number, movement_code FROM staging.case_event ORDER BY case_number")
        return cursor.fetchall()


def test_loads_the_flattened_rows(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        load(cursor, [row("A", 219)])
    connection.close()

    assert fetch_all(postgres_url) == [("A", 219)]


def test_a_second_load_replaces_the_previous_one(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        load(cursor, [row("A", 219)])
        load(cursor, [row("B", 220)])
    connection.close()

    assert fetch_all(postgres_url) == [("B", 220)]
