import json
from datetime import date, datetime, timezone

import psycopg2
import pytest

from pipeline import dw_ruling
from pipeline.raw_schema import ensure as ensure_raw

COLLECTED_AT = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
SUMMARY = "PROCESSUAL CIVIL. AGRAVO INTERNO NO RECURSO ESPECIAL.\n1. Ementa como publicada.  "


def ruling(ruling_id, **fields):
    return {
        "id": ruling_id,
        "numeroProcesso": "1997135",
        "numeroRegistro": "202201097444",
        "siglaClasse": "AgInt no REsp",
        "nomeOrgaoJulgador": "TERCEIRA TURMA",
        "ementa": SUMMARY,
        "dataDecisao": "20220627",
        "decisao": "Vistos e relatados estes autos, acordam os Ministros...",
        **fields,
    }


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        ensure_raw(cur)
        cur.execute("TRUNCATE raw.stj_ruling")
        cur.execute("TRUNCATE dw.dim_ruling RESTART IDENTITY CASCADE")
        yield cur


def store(cursor, record, dataset="espelhos-de-acordaos-terceira-turma"):
    cursor.execute(
        "INSERT INTO raw.stj_ruling (id, dataset, source_url, collected_at, payload) "
        "VALUES (%s, %s, %s, %s, %s)",
        (record["id"], dataset, "https://stj.example/20220630.json", COLLECTED_AT,
         json.dumps(record, ensure_ascii=False)),
    )


def rulings(cursor):
    cursor.execute(
        "SELECT source, source_id, case_number, court_code, judging_body, judged_at, summary, "
        "source_url, extracted_at FROM dw.dim_ruling ORDER BY source_id"
    )
    return cursor.fetchall()


def test_loads_a_ruling_with_the_summary_as_published(cursor):
    store(cursor, ruling("000819199"))

    assert dw_ruling.load(cursor) == 1

    assert rulings(cursor) == [(
        "stj_espelhos",
        "000819199",
        "AgInt no REsp 1997135",
        "STJ",
        "TERCEIRA TURMA",
        date(2022, 6, 27),
        SUMMARY,
        "https://dadosabertos.web.stj.jus.br/dataset/espelhos-de-acordaos-terceira-turma",
        COLLECTED_AT,
    )]


def test_never_stores_the_full_text_of_the_decision(cursor):
    store(cursor, ruling("000819199"))

    dw_ruling.load(cursor)

    cursor.execute("SELECT to_jsonb(r)::text FROM dw.dim_ruling r")
    assert "Vistos e relatados" not in cursor.fetchone()[0]


def test_skips_a_ruling_without_a_summary(cursor):
    store(cursor, ruling("1", ementa=None))
    store(cursor, ruling("2", ementa="   "))
    store(cursor, ruling("3"))

    assert dw_ruling.load(cursor) == 1
    assert [row[1] for row in rulings(cursor)] == ["3"]


def test_leaves_the_date_empty_when_the_source_has_none(cursor):
    store(cursor, ruling("1", dataDecisao=None))
    store(cursor, ruling("2", dataDecisao="2022-06"))

    dw_ruling.load(cursor)

    assert [row[5] for row in rulings(cursor)] == [None, None]


def test_leaves_the_case_number_empty_without_a_number(cursor):
    store(cursor, ruling("1", numeroProcesso=None))

    dw_ruling.load(cursor)

    assert rulings(cursor)[0][2] is None


def test_loading_twice_keeps_one_row_per_ruling(cursor):
    store(cursor, ruling("1"))

    dw_ruling.load(cursor)
    dw_ruling.load(cursor)

    assert len(rulings(cursor)) == 1


def test_removes_a_ruling_that_left_the_source(cursor):
    store(cursor, ruling("1"))
    store(cursor, ruling("2"))
    dw_ruling.load(cursor)
    cursor.execute("DELETE FROM raw.stj_ruling WHERE id = '1'")

    dw_ruling.load(cursor)

    assert [row[1] for row in rulings(cursor)] == ["2"]
