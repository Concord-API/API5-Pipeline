import json
import os

import psycopg2
import pytest

from pipeline.dw_case import load as load_case
from pipeline.dw_reference import seed_courts
from pipeline.dw_subject import assert_no_penal_subjects, load_bridge, load_subjects, set_tpu_areas
from pipeline.tpu import load as load_tpu

FIXTURE_TPU = os.path.join(os.path.dirname(__file__), "fixtures", "tpu_sample.json")


@pytest.fixture
def tpu():
    return load_tpu(FIXTURE_TPU)


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.dim_case, dw.dim_movement, dw.dim_judging_body, dw.dim_subject, "
            "dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome RESTART IDENTITY CASCADE"
        )
        cur.execute("TRUNCATE staging.case_event")
        seed_courts(cur)
        yield cur
        connection.commit()


def insert_staging_row(cursor, subjects, **overrides):
    row = {
        "raw_id": 1, "tribunal": "tjsp", "case_number": "A", "court_level": "First",
        "case_class_code": 7, "case_class_name": "Procedimento Comum Cível",
        "judging_body_code": "123", "judging_body_name": "1ª Vara Cível",
        "filed_at": "2024-01-15T00:00:00Z", "secrecy_level": 0, "subjects": json.dumps(subjects),
        "movement_code": 219, "movement_name": "Procedência", "occurred_at": "2024-06-01T12:00:00Z",
        "source": "datajud", "source_url": "https://x", "extracted_at": "2024-06-01T12:00:00Z",
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    sql = f"INSERT INTO staging.case_event ({columns}) VALUES ({placeholders})"
    cursor.execute(sql, list(row.values()))


def fetch_subjects(cursor):
    cursor.execute(
        "SELECT subject_name, subject_code, tpu_area FROM dw.dim_subject ORDER BY subject_name"
    )
    return cursor.fetchall()


def test_a_subject_repeated_across_cases_becomes_one_row(cursor):
    insert_staging_row(cursor, [{"codigo": 1127, "nome": "Contratos"}], case_number="A")
    insert_staging_row(cursor, [{"codigo": 1127, "nome": "Contratos"}], case_number="B")

    load_subjects(cursor)

    assert fetch_subjects(cursor) == [("Contratos", 1127, None)]


def test_a_subject_without_name_or_code_is_ignored(cursor):
    insert_staging_row(
        cursor, [{"codigo": 1127}, {"nome": "Sem código"}, {"codigo": 1128, "nome": "Danos"}]
    )

    load_subjects(cursor)

    assert fetch_subjects(cursor) == [("Danos", 1128, None)]


def test_set_tpu_areas_fills_the_right_area(cursor, tpu):
    insert_staging_row(cursor, [{"codigo": 1127, "nome": "Contratos"}])
    load_subjects(cursor)

    set_tpu_areas(cursor, tpu)

    assert fetch_subjects(cursor) == [("Contratos", 1127, "DIREITO CIVIL")]


def test_assert_no_penal_subjects_raises_when_one_slipped_in(cursor, tpu):
    insert_staging_row(cursor, [{"codigo": 3568, "nome": "Furto"}])
    load_subjects(cursor)

    with pytest.raises(ValueError, match="3568"):
        assert_no_penal_subjects(cursor, tpu)


def test_assert_no_penal_subjects_does_not_raise_when_clean(cursor, tpu):
    insert_staging_row(cursor, [{"codigo": 1127, "nome": "Contratos"}])
    load_subjects(cursor)

    assert_no_penal_subjects(cursor, tpu)


def test_load_bridge_links_case_and_subject(cursor):
    insert_staging_row(cursor, [{"codigo": 1127, "nome": "Contratos"}], case_number="A")
    load_case(cursor)
    load_subjects(cursor)

    load_bridge(cursor)

    cursor.execute(
        "SELECT dc.case_number, ds.subject_name FROM dw.bridge_case_subject b "
        "JOIN dw.dim_case dc ON dc.case_sk = b.case_sk "
        "JOIN dw.dim_subject ds ON ds.subject_sk = b.subject_sk"
    )
    assert cursor.fetchall() == [("A", "Contratos")]


def test_load_bridge_twice_does_not_duplicate(cursor):
    insert_staging_row(cursor, [{"codigo": 1127, "nome": "Contratos"}], case_number="A")
    load_case(cursor)
    load_subjects(cursor)

    load_bridge(cursor)
    load_bridge(cursor)

    cursor.execute("SELECT count(*) FROM dw.bridge_case_subject")
    assert cursor.fetchone() == (1,)
