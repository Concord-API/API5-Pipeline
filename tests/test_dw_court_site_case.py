from datetime import date

import psycopg2
import pytest
from psycopg2.extras import Json

from pipeline import dw_court_site_case
from pipeline.raw_schema import ensure

FOUND = "10000012320248260100"
NOT_FOUND = "20000012320248260100"
SEALED = "30000012320248260100"
UNKNOWN = "40000012320248260100"
SOURCE_URL = "https://esaj.tjsp.jus.br/cposg/search.do?numero=1"

SEED = f"""
INSERT INTO dw.dim_court (court_code, court_name, state_uf)
VALUES ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP');
INSERT INTO dw.dim_case (case_number, court_sk, court_level, source, extracted_at)
SELECT v.case_number, c.court_sk, v.court_level, 'datajud', now()
FROM (VALUES ('{FOUND}', 'Second'), ('{NOT_FOUND}', 'First'), ('{SEALED}', 'First'))
    AS v (case_number, court_level)
CROSS JOIN dw.dim_court c;
"""

FOUND_PAYLOAD = {
    "case_number": "1000001-23.2024.8.26.0100",
    "instance": "cposg",
    "case_class": "Apelação Cível",
    "subjects": ["Planos de Saúde"],
    "forum": None,
    "section": "Direito Privado 1",
    "judging_body": "3ª Câmara de Direito Privado",
    "judge": "Relator Exemplo",
    "filed_at": "2024-02-01",
    "situation": "Julgado",
    "decision_date": "2024-05-02",
    "decision_result": "Negaram provimento ao recurso.",
    "movements": [
        {"date": "2024-05-10", "description": "Trânsito em Julgado"},
        {"date": "2024-05-02", "description": "Julgado"},
        {"date": "2024-02-01", "description": "Distribuído"},
    ],
}


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.fact_case_event, dw.bridge_case_subject, dw.dim_case, dw.dim_court "
            "RESTART IDENTITY CASCADE"
        )
        cur.execute(SEED)
        ensure(cur)
        cur.execute("TRUNCATE raw.court_site_case")
        yield cur
        connection.rollback()


def collect(cursor, case_number, status, payload, court_level="Second"):
    cursor.execute(
        "INSERT INTO raw.court_site_case "
        "(court, case_number, court_level, source, source_url, status, payload) "
        "VALUES ('TJSP', %s, %s, 'esaj_tjsp_cposg', %s, %s, %s) "
        "ON CONFLICT (court, case_number) DO UPDATE SET payload = EXCLUDED.payload, "
        "status = EXCLUDED.status, collected_at = now()",
        (case_number, court_level, SOURCE_URL, status, Json(payload)),
    )


def detail(cursor, case_number):
    cursor.execute(
        "SELECT d.status, d.case_class, d.subjects, d.judging_body, d.judge, d.filed_at, "
        "d.decision_date, d.decision_result, d.situation, d.source, d.source_url "
        "FROM dw.case_site_detail d JOIN dw.dim_case c USING (case_sk) WHERE c.case_number = %s",
        (case_number,),
    )
    return cursor.fetchone()


def movements(cursor, case_number):
    cursor.execute(
        "SELECT m.seq, m.moved_at, m.description FROM dw.case_site_movement m "
        "JOIN dw.dim_case c USING (case_sk) WHERE c.case_number = %s ORDER BY m.seq",
        (case_number,),
    )
    return cursor.fetchall()


def test_load_keeps_the_details_of_a_found_case(cursor):
    collect(cursor, FOUND, "found", FOUND_PAYLOAD)

    dw_court_site_case.load(cursor)

    assert detail(cursor, FOUND) == (
        "found", "Apelação Cível", ["Planos de Saúde"], "3ª Câmara de Direito Privado",
        "Relator Exemplo", date(2024, 2, 1), date(2024, 5, 2),
        "Negaram provimento ao recurso.", "Julgado", "esaj_tjsp_cposg", SOURCE_URL,
    )


def test_load_keeps_no_party_lawyer_or_document_of_the_case(cursor):
    payload = {
        **FOUND_PAYLOAD,
        "parties": [{"name": "Fulano de Tal", "lawyer": "Advogado Exemplo"}],
        "documents": ["inteiro-teor.pdf"],
    }
    collect(cursor, FOUND, "found", payload)

    dw_court_site_case.load(cursor)

    cursor.execute("SELECT to_jsonb(d)::text FROM dw.case_site_detail d")
    stored = cursor.fetchone()[0]
    assert "Fulano" not in stored
    assert "Advogado" not in stored
    assert "inteiro-teor" not in stored


def test_load_ignores_a_collected_case_missing_from_the_case_dimension(cursor):
    collect(cursor, UNKNOWN, "found", FOUND_PAYLOAD)

    assert dw_court_site_case.load(cursor) == {"found": 0, "not_found": 0, "sealed": 0}
    cursor.execute("SELECT count(*) FROM dw.case_site_detail")
    assert cursor.fetchone()[0] == 0
