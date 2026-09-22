import psycopg2
import pytest

from pipeline.dw_case import load
from pipeline.dw_reference import load_case_classes, seed_courts


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.dim_case, dw.dim_movement, dw.dim_judging_body, "
            "dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome RESTART IDENTITY CASCADE"
        )
        cur.execute("TRUNCATE staging.case_event")
        seed_courts(cur)
        yield cur
        connection.commit()


def insert_staging_row(cursor, **overrides):
    row = {
        "raw_id": 1, "tribunal": "tjsp", "case_number": "A", "court_level": "First",
        "case_class_code": 7, "case_class_name": "Procedimento Comum Cível",
        "judging_body_code": "123", "judging_body_name": "1ª Vara Cível",
        "filed_at": "2024-01-15T00:00:00Z", "secrecy_level": 0, "subjects": "[]",
        "movement_code": 219, "movement_name": "Procedência", "occurred_at": "2024-06-01T12:00:00Z",
        "source": "datajud", "source_url": "https://x", "extracted_at": "2024-06-01T12:00:00Z",
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    sql = f"INSERT INTO staging.case_event ({columns}) VALUES ({placeholders})"
    cursor.execute(sql, list(row.values()))


def fetch_case(cursor, case_number):
    cursor.execute(
        "SELECT court_level, secrecy_level, case_class_sk, extracted_at "
        "FROM dw.dim_case WHERE case_number = %s",
        (case_number,),
    )
    return cursor.fetchone()


def test_inserts_one_row_per_distinct_case(cursor):
    insert_staging_row(cursor, case_number="A")
    insert_staging_row(cursor, case_number="B")

    load(cursor)

    cursor.execute("SELECT case_number FROM dw.dim_case ORDER BY case_number")
    assert cursor.fetchall() == [("A",), ("B",)]


def test_two_events_of_the_same_case_produce_a_single_row(cursor):
    insert_staging_row(cursor, case_number="A", movement_code=219)
    insert_staging_row(cursor, case_number="A", movement_code=220)

    load(cursor)

    cursor.execute("SELECT count(*) FROM dw.dim_case WHERE case_number = 'A'")
    assert cursor.fetchone() == (1,)


def test_picks_the_data_from_the_most_recently_extracted_row(cursor):
    insert_staging_row(
        cursor, case_number="A", court_level="First", extracted_at="2024-01-01T00:00:00Z"
    )
    insert_staging_row(
        cursor, case_number="A", court_level="Second", extracted_at="2024-06-01T00:00:00Z"
    )

    load(cursor)

    court_level, _, _, _ = fetch_case(cursor, "A")
    assert court_level == "Second"


def test_a_case_without_a_matching_class_gets_a_null_class(cursor):
    insert_staging_row(cursor, case_number="A", case_class_name="Classe Desconhecida")

    load(cursor)

    _, _, case_class_sk, _ = fetch_case(cursor, "A")
    assert case_class_sk is None


def test_a_case_with_a_known_class_resolves_its_key(cursor):
    insert_staging_row(cursor, case_number="A", case_class_name="Procedimento Comum Cível")
    load_case_classes(cursor)

    load(cursor)

    _, _, case_class_sk, _ = fetch_case(cursor, "A")
    assert case_class_sk is not None


def test_a_second_load_updates_court_level_but_not_secrecy_level(cursor):
    insert_staging_row(cursor, case_number="A", court_level="First", secrecy_level=0)
    load(cursor)

    cursor.execute("TRUNCATE staging.case_event")
    insert_staging_row(
        cursor,
        case_number="A",
        court_level="Second",
        secrecy_level=5,
        extracted_at="2024-07-01T00:00:00Z",
    )
    load(cursor)

    court_level, secrecy_level, _, _ = fetch_case(cursor, "A")
    assert court_level == "Second"
    assert secrecy_level == 0
