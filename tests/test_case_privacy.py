from pathlib import Path

import psycopg2
import pytest

from pipeline import dw_court_site_case, esaj_tjsp
from pipeline.harvest_court_sites import store
from pipeline.raw_schema import ensure

FIXTURES = Path(__file__).parent / "fixtures" / "esaj"

FIRST = "10000012320248260100"
SECOND = "20000012320248260100"
SEALED_ON_SITE = "30000012320248260100"

PARTY_AND_LAWYER_NAMES = (
    "PARTE AUTORA FICTÍCIA",
    "EMPRESA RÉ FICTÍCIA",
    "ADVOGADA FICTÍCIA",
    "ADVOGADO FICTÍCIO",
    "OAB 000001",
    "OAB 000002",
)

SEED = f"""
INSERT INTO dw.dim_court (court_code, court_name, state_uf)
VALUES ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP');
INSERT INTO dw.dim_case (case_number, court_sk, court_level, secrecy_level, source, extracted_at)
SELECT v.case_number, c.court_sk, v.court_level, 0, 'datajud', now()
FROM (VALUES ('{FIRST}', 'First'), ('{SECOND}', 'Second'), ('{SEALED_ON_SITE}', 'First'))
    AS v (case_number, court_level)
CROSS JOIN dw.dim_court c;
"""


def page(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200
        self.encoding = "utf-8"

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, case_number, pages):
        formatted = esaj_tjsp.format_case_number(case_number)
        self.pages = [
            FakeResponse(page(name).replace("1000001-23.2024.8.26.0100", formatted))
            for name in pages
        ]

    def get(self, url, params=None, timeout=None):
        return self.pages.pop(0)


def fetch(case_number, court_level, pages):
    client = esaj_tjsp.Client(FakeSession(case_number, pages), sleep=lambda _seconds: None)
    return esaj_tjsp.fetch_case(client, case_number, court_level)


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_case, dw.dim_court RESTART IDENTITY CASCADE")
        cur.execute(SEED)
        ensure(cur)
        cur.execute("TRUNCATE raw.court_site_case")
        pages_first = [
            "cpopg_show.html",
            "cpopg_movements_1.html",
            "cpopg_movements_2.html",
            "cpopg_movements_3.html",
        ]
        pages_second = ["cposg_show.html", "cposg_movements_1.html", "cposg_movements_2.html"]
        store(cur, FIRST, "First", fetch(FIRST, "First", pages_first))
        store(cur, SECOND, "Second", fetch(SECOND, "Second", pages_second))
        store(cur, SEALED_ON_SITE, "First", fetch(SEALED_ON_SITE, "First", ["sealed.html"]))
        dw_court_site_case.load(cur)
        yield cur
        connection.rollback()


def warehouse_text(cursor):
    cursor.execute(
        "SELECT concat_ws(' ', status, case_class, array_to_string(subjects, ' '), judging_body, "
        "judge, decision_result, situation, source, source_url) FROM dw.case_site_detail "
        "UNION ALL SELECT description FROM dw.case_site_movement"
    )
    return " ".join(row[0] for row in cursor.fetchall())


def test_no_party_or_lawyer_of_the_site_pages_reaches_the_warehouse(cursor):
    text = warehouse_text(cursor)

    assert text
    for name in PARTY_AND_LAWYER_NAMES:
        assert name not in text


def test_the_public_movements_still_reach_the_warehouse(cursor):
    cursor.execute("SELECT count(*) FROM dw.case_site_movement")

    assert cursor.fetchone()[0] > 0


def test_a_case_sealed_on_the_site_keeps_only_its_status(cursor):
    cursor.execute(
        "SELECT d.status, d.case_class, d.subjects, d.judging_body, d.judge, d.filed_at, "
        "d.decision_date, d.decision_result, d.situation, "
        "(SELECT count(*) FROM dw.case_site_movement m WHERE m.case_sk = d.case_sk) "
        "FROM dw.case_site_detail d JOIN dw.dim_case c USING (case_sk) "
        "WHERE c.case_number = %s",
        (SEALED_ON_SITE,),
    )

    assert cursor.fetchone() == ("sealed", None, [], None, None, None, None, None, None, 0)
