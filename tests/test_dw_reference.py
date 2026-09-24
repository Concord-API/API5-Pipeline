import psycopg2
import pytest

from pipeline.dw_reference import (
    VERIFIED_MOVEMENTS,
    load_case_classes,
    load_judging_bodies,
    load_movements,
    seed_courts,
    seed_outcomes,
    seed_verified_movements,
    verified_movement_codes,
)


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.dim_movement, dw.dim_judging_body, dw.dim_case_class, "
            "dw.dim_court, dw.dim_decision_outcome RESTART IDENTITY CASCADE"
        )
        cur.execute("TRUNCATE staging.case_event")
        yield cur
        connection.commit()


def insert_staging_row(cursor, **overrides):
    row = {
        "raw_id": 1, "tribunal": "tjsp", "case_number": "A", "court_level": "First",
        "case_class_code": 7, "case_class_name": "Procedimento Comum Cível",
        "judging_body_code": "123", "judging_body_name": "1ª Vara Cível",
        "filed_at": None, "secrecy_level": 0, "subjects": "[]",
        "movement_code": 219, "movement_name": "Procedência", "occurred_at": "2024-06-01T12:00:00Z",
        "source": "datajud", "source_url": "https://x", "extracted_at": "2024-06-01T12:00:00Z",
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join(["%s"] * len(row))
    sql = f"INSERT INTO staging.case_event ({columns}) VALUES ({placeholders})"
    cursor.execute(sql, list(row.values()))


def fetch_scalars(cursor, sql):
    cursor.execute(sql)
    return [r[0] for r in cursor.fetchall()]


def test_seed_courts_creates_the_three_courts(cursor):
    seed_courts(cursor)

    codes = fetch_scalars(cursor, "SELECT court_code FROM dw.dim_court ORDER BY court_code")

    assert codes == ["TJMG", "TJRJ", "TJSP"]


def test_seed_courts_twice_does_not_duplicate(cursor):
    seed_courts(cursor)
    seed_courts(cursor)

    codes = fetch_scalars(cursor, "SELECT court_code FROM dw.dim_court")

    assert len(codes) == 3


def test_seed_outcomes_creates_the_five_outcomes(cursor):
    seed_outcomes(cursor)

    codes = fetch_scalars(
        cursor, "SELECT outcome_code FROM dw.dim_decision_outcome ORDER BY outcome_code"
    )

    assert codes == ["Denied", "Dismissed", "Granted", "Neutral", "PartiallyGranted"]


def test_seed_outcomes_only_neutral_and_dismissed_do_not_count(cursor):
    seed_outcomes(cursor)

    codes = fetch_scalars(
        cursor,
        "SELECT outcome_code FROM dw.dim_decision_outcome "
        "WHERE NOT counts_in_metric ORDER BY outcome_code",
    )

    assert codes == ["Dismissed", "Neutral"]


def test_load_case_classes_inserts_distinct_classes(cursor):
    insert_staging_row(cursor, case_number="A", case_class_name="Procedimento Comum Cível")
    insert_staging_row(cursor, case_number="B", case_class_name="Procedimento Comum Cível")
    insert_staging_row(cursor, case_number="C", case_class_name=None)

    load_case_classes(cursor)

    classes = fetch_scalars(cursor, "SELECT class_name FROM dw.dim_case_class")

    assert classes == ["Procedimento Comum Cível"]


def test_load_judging_bodies_matches_the_right_court(cursor):
    seed_courts(cursor)
    insert_staging_row(cursor, tribunal="tjsp", judging_body_name="1ª Vara Cível")

    load_judging_bodies(cursor)

    cursor.execute(
        "SELECT c.court_code, jb.body_name FROM dw.dim_judging_body jb "
        "JOIN dw.dim_court c ON c.court_sk = jb.court_sk"
    )

    assert cursor.fetchall() == [("TJSP", "1ª Vara Cível")]


def test_load_movements_inserts_a_new_code_as_unverified_neutral(cursor):
    seed_outcomes(cursor)
    insert_staging_row(cursor, movement_code=219, movement_name="Procedência")

    load_movements(cursor)

    cursor.execute(
        "SELECT dm.movement_name, dm.code_verified, o.outcome_code "
        "FROM dw.dim_movement dm JOIN dw.dim_decision_outcome o ON o.outcome_sk = dm.outcome_sk "
        "WHERE dm.movement_code = 219"
    )

    assert cursor.fetchone() == ("Procedência", False, "Neutral")


def test_load_movements_does_not_overwrite_a_verified_code(cursor):
    seed_outcomes(cursor)
    cursor.execute(
        "INSERT INTO dw.dim_movement "
        "(movement_code, movement_name, outcome_sk, code_verified, polarity_reference) "
        "SELECT 219, 'Procedência', outcome_sk, true, 'pretensao_autor' "
        "FROM dw.dim_decision_outcome WHERE outcome_code = 'Granted'"
    )
    insert_staging_row(cursor, movement_code=219, movement_name="Procedência")

    load_movements(cursor)

    cursor.execute(
        "SELECT code_verified, "
        "(SELECT outcome_code FROM dw.dim_decision_outcome o WHERE o.outcome_sk = dm.outcome_sk) "
        "FROM dw.dim_movement dm WHERE movement_code = 219"
    )

    assert cursor.fetchone() == (True, "Granted")


def movement(cursor, code):
    cursor.execute(
        "SELECT o.outcome_code, dm.code_verified, dm.polarity_reference "
        "FROM dw.dim_movement dm JOIN dw.dim_decision_outcome o ON o.outcome_sk = dm.outcome_sk "
        "WHERE dm.movement_code = %s",
        (code,),
    )
    return cursor.fetchone()


def test_seed_verified_movements_maps_each_code_to_its_outcome(cursor):
    seed_outcomes(cursor)

    seed_verified_movements(cursor)

    assert movement(cursor, 219) == ("Granted", True, "pretensao_autor")
    assert movement(cursor, 220) == ("Denied", True, "pretensao_autor")
    assert movement(cursor, 221) == ("PartiallyGranted", True, "pretensao_autor")
    assert movement(cursor, 237) == ("Granted", True, "pretensao_recorrente")
    assert movement(cursor, 238) == ("PartiallyGranted", True, "pretensao_recorrente")
    assert movement(cursor, 239) == ("Denied", True, "pretensao_recorrente")


def test_seed_verified_movements_upgrades_a_code_loaded_as_neutral(cursor):
    seed_outcomes(cursor)
    insert_staging_row(cursor, movement_code=219, movement_name="Procedência")
    load_movements(cursor)

    seed_verified_movements(cursor)

    assert movement(cursor, 219) == ("Granted", True, "pretensao_autor")


def test_a_new_load_does_not_downgrade_a_verified_code(cursor):
    seed_outcomes(cursor)
    seed_verified_movements(cursor)
    insert_staging_row(cursor, movement_code=219, movement_name="Procedência")

    load_movements(cursor)

    assert movement(cursor, 219) == ("Granted", True, "pretensao_autor")


def test_a_code_outside_the_list_stays_neutral_and_unverified(cursor):
    seed_outcomes(cursor)
    seed_verified_movements(cursor)
    insert_staging_row(cursor, movement_code=999, movement_name="Outro")

    load_movements(cursor)

    assert movement(cursor, 999) == ("Neutral", False, None)


def test_the_harvest_codes_are_the_verified_movements():
    assert verified_movement_codes() == [219, 220, 221, 237, 238, 239]
    assert verified_movement_codes() == [code for code, *_ in VERIFIED_MOVEMENTS]
