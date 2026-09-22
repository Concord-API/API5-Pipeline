import json

import psycopg2
import pytest

from pipeline.dw_case import load as load_case
from pipeline.dw_fact import load as load_fact
from pipeline.dw_reference import load_judging_bodies, load_movements, seed_courts, seed_outcomes


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.fact_case_event, dw.dim_case, dw.dim_movement, dw.dim_judging_body, "
            "dw.dim_subject, dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome, dw.dim_date "
            "RESTART IDENTITY CASCADE"
        )
        cur.execute("TRUNCATE staging.case_event")
        seed_courts(cur)
        seed_outcomes(cur)
        yield cur
        connection.commit()


def insert_staging_row(cursor, **overrides):
    row = {
        "raw_id": 1, "tribunal": "tjsp", "case_number": "A", "court_level": "First",
        "case_class_code": 7, "case_class_name": "Procedimento Comum Cível",
        "judging_body_code": "123", "judging_body_name": "1ª Vara Cível",
        "filed_at": "2024-01-15T00:00:00Z", "secrecy_level": 0, "subjects": json.dumps([]),
        "movement_code": 219, "movement_name": "Procedência", "occurred_at": "2024-06-01T12:00:00Z",
        "source": "datajud", "source_url": "https://x", "extracted_at": "2024-06-01T12:00:00Z",
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    sql = f"INSERT INTO staging.case_event ({columns}) VALUES ({placeholders})"
    cursor.execute(sql, list(row.values()))


def build_dimensions(cursor):
    load_case(cursor)
    load_movements(cursor)
    load_judging_bodies(cursor)


def test_loads_one_fact_row_with_the_right_keys(cursor):
    insert_staging_row(cursor)
    build_dimensions(cursor)

    load_fact(cursor)

    cursor.execute(
        "SELECT dc.case_number, c.court_code, dm.movement_code "
        "FROM dw.fact_case_event f "
        "JOIN dw.dim_case dc ON dc.case_sk = f.case_sk "
        "JOIN dw.dim_court c ON c.court_sk = f.court_sk "
        "JOIN dw.dim_movement dm ON dm.movement_sk = f.movement_sk"
    )
    assert cursor.fetchall() == [("A", "TJSP", 219)]


def test_a_fact_without_a_matching_judging_body_gets_a_null_judging_body(cursor):
    insert_staging_row(cursor, judging_body_name="Vara Desconhecida")
    load_case(cursor)
    load_movements(cursor)
    # load_judging_bodies not called: no dim_judging_body row exists for this case

    load_fact(cursor)

    cursor.execute("SELECT judging_body_sk FROM dw.fact_case_event")
    assert cursor.fetchone() == (None,)


def test_a_fact_without_a_matching_date_gets_a_null_date(cursor):
    insert_staging_row(cursor)
    build_dimensions(cursor)

    load_fact(cursor)

    cursor.execute("SELECT date_sk FROM dw.fact_case_event")
    assert cursor.fetchone() == (None,)


def test_loading_the_same_event_twice_does_not_duplicate(cursor):
    insert_staging_row(cursor)
    build_dimensions(cursor)

    load_fact(cursor)
    load_fact(cursor)

    cursor.execute("SELECT count(*) FROM dw.fact_case_event")
    assert cursor.fetchone() == (1,)


def test_two_movements_of_the_same_case_produce_two_facts(cursor):
    insert_staging_row(cursor, movement_code=219, occurred_at="2024-06-01T12:00:00Z")
    insert_staging_row(cursor, movement_code=220, occurred_at="2024-07-01T12:00:00Z")
    build_dimensions(cursor)

    load_fact(cursor)

    cursor.execute("SELECT count(*) FROM dw.fact_case_event")
    assert cursor.fetchone() == (2,)
