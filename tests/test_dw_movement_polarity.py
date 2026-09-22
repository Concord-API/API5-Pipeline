import psycopg2
import pytest

from pipeline.dw_movement_polarity import set_polarity
from pipeline.dw_reference import seed_outcomes


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.dim_movement, dw.dim_decision_outcome RESTART IDENTITY CASCADE"
        )
        seed_outcomes(cur)
        yield cur
        connection.commit()


def insert_movement(cursor, code):
    cursor.execute(
        "INSERT INTO dw.dim_movement (movement_code, movement_name, outcome_sk) "
        "SELECT %s, 'Movimento', outcome_sk FROM dw.dim_decision_outcome "
        "WHERE outcome_code = 'Neutral'",
        (code,),
    )


def polarity_of(cursor, code):
    cursor.execute(
        "SELECT polarity_reference FROM dw.dim_movement WHERE movement_code = %s", (code,)
    )
    return cursor.fetchone()[0]


def test_marks_a_claimant_code_as_pretensao_autor(cursor):
    insert_movement(cursor, 219)

    set_polarity(cursor)

    assert polarity_of(cursor, 219) == "pretensao_autor"


def test_marks_an_appellant_code_as_pretensao_recorrente(cursor):
    insert_movement(cursor, 237)

    set_polarity(cursor)

    assert polarity_of(cursor, 237) == "pretensao_recorrente"


def test_leaves_an_unrelated_code_untouched(cursor):
    insert_movement(cursor, 999)

    set_polarity(cursor)

    assert polarity_of(cursor, 999) is None


def test_running_it_twice_keeps_the_same_result(cursor):
    insert_movement(cursor, 219)

    set_polarity(cursor)
    set_polarity(cursor)

    assert polarity_of(cursor, 219) == "pretensao_autor"
