from pathlib import Path

import psycopg2
import pytest

from pipeline import esaj_tjsp
from pipeline.harvest_court_sites import harvest, main
from pipeline.raw_schema import ensure

FIXTURES = Path(__file__).parent / "fixtures" / "esaj"

FIRST = "10000012320248260100"
SECOND = "20000012320248260100"
SEALED = "30000012320248260100"
OTHER_COURT = "40000012320248190001"
NOT_JUDGED = "50000012320248260100"

SEED = f"""
INSERT INTO dw.dim_decision_outcome (outcome_code, outcome_label, counts_in_metric)
VALUES ('Granted', 'Procedente', true);
INSERT INTO dw.dim_movement
    (movement_code, movement_name, outcome_sk, code_verified, polarity_reference)
SELECT 219, 'Procedência', outcome_sk, true, 'pretensao_autor' FROM dw.dim_decision_outcome;
INSERT INTO dw.dim_court (court_code, court_name, state_uf) VALUES
    ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP'),
    ('TJRJ', 'Tribunal de Justiça do Rio de Janeiro', 'RJ');
INSERT INTO dw.dim_date (date_sk, full_date, year, quarter, month, month_name, day)
VALUES (20250615, '2025-06-15', 2025, 2, 6, 'Junho', 15);
INSERT INTO dw.dim_theme (theme_name, theme_key) VALUES ('Tema julgado', 1);
INSERT INTO dw.dim_subject (subject_name, subject_code) VALUES ('Assunto julgado', 100);
INSERT INTO dw.bridge_theme_subject (theme_sk, subject_sk)
SELECT t.theme_sk, s.subject_sk FROM dw.dim_theme t, dw.dim_subject s;
INSERT INTO dw.dim_case (case_number, court_sk, court_level, secrecy_level, source, extracted_at)
SELECT v.case_number, c.court_sk, v.court_level, v.secrecy_level, 'datajud', now()
FROM (VALUES
    ('{FIRST}', 'TJSP', 'First', 0),
    ('{SECOND}', 'TJSP', 'Second', 0),
    ('{SEALED}', 'TJSP', 'First', 1),
    ('{OTHER_COURT}', 'TJRJ', 'First', 0),
    ('{NOT_JUDGED}', 'TJSP', 'First', 0)
) AS v (case_number, court_code, court_level, secrecy_level)
JOIN dw.dim_court c ON c.court_code = v.court_code;
INSERT INTO dw.bridge_case_subject (case_sk, subject_sk)
SELECT dc.case_sk, s.subject_sk FROM dw.dim_case dc CROSS JOIN dw.dim_subject s;
INSERT INTO dw.fact_case_event
    (case_sk, court_sk, movement_sk, date_sk, occurred_at, source_url, extracted_at, natural_key)
SELECT dc.case_sk, dc.court_sk, m.movement_sk, 20250615, TIMESTAMPTZ '2025-06-15',
       'https://example.org', now(), 'evt:' || dc.case_sk
FROM dw.dim_case dc CROSS JOIN dw.dim_movement m
WHERE dc.case_number <> '{NOT_JUDGED}';
REFRESH MATERIALIZED VIEW dw.case_current_result;
"""


def seed(database_url):
    with psycopg2.connect(database_url) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.fact_case_event, dw.bridge_case_subject, dw.bridge_theme_subject, "
            "dw.dim_case, dw.dim_theme, dw.dim_subject, dw.dim_movement, dw.dim_judging_body, "
            "dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome, dw.dim_date "
            "RESTART IDENTITY CASCADE"
        )
        cur.execute(SEED)
        ensure(cur)
        cur.execute("TRUNCATE raw.court_site_case")


@pytest.fixture
def cursor(dw_ready):
    seed(dw_ready)
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        yield cur
        connection.commit()


def page(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def numbered(name, case_number):
    return page(name).replace(
        "1000001-23.2024.8.26.0100", esaj_tjsp.format_case_number(case_number)
    )


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        key = (url, tuple(sorted((params or {}).items())))
        answer = self.pages[key] if key in self.pages else self.pages[url]
        if isinstance(answer, FakeResponse):
            return answer
        return FakeResponse(answer)


def site(first=None, second=None):
    first_search = esaj_tjsp.search_url(FIRST, "First")
    second_search = esaj_tjsp.search_url(SECOND, "Second")
    first_movements = "https://esaj.tjsp.jus.br/cpopg/carregarMovimentacoesAjax.do"
    second_movements = "https://esaj.tjsp.jus.br/cposg/carregarMovimentacoesAjax.do"
    return {
        first_search: first if first is not None else numbered("cpopg_show.html", FIRST),
        (first_movements, (("processo.codigo", "B00001AAA0000"),)): page(
            "cpopg_movements_3.html"
        ),
        second_search: second if second is not None else numbered("cposg_show.html", SECOND),
        (second_movements, (("cdProcesso", "RI000AAA0000"),)): page("cposg_movements_2.html"),
    }


def client(pages):
    session = FakeSession(pages)
    return esaj_tjsp.Client(session, sleep=lambda _seconds: None), session


def stored(cursor):
    cursor.execute(
        "SELECT case_number, court_level, source, status, payload "
        "FROM raw.court_site_case ORDER BY case_number"
    )
    return cursor.fetchall()


def test_harvests_only_the_public_tjsp_cases_of_the_sample(cursor):
    esaj, _ = client(site())

    counts = harvest(cursor, esaj)

    rows = stored(cursor)
    assert [(row[0], row[1], row[2], row[3]) for row in rows] == [
        (FIRST, "First", "esaj_tjsp_cpopg", "found"),
        (SECOND, "Second", "esaj_tjsp_cposg", "found"),
    ]
    assert counts == {"found": 2}


def test_stores_the_fields_and_movements_read_from_the_site(cursor):
    esaj, _ = client(site())

    harvest(cursor, esaj)

    payload = stored(cursor)[0][4]
    assert payload["case_number"] == "1000001-23.2024.8.26.0100"
    assert payload["judging_body"] == "2ª Vara Cível"
    assert payload["movements"] == [
        {
            "date": "2024-08-11",
            "description": "Distribuído Livremente (por Sorteio) "
            "(movimentação exclusiva do distribuidor)",
        }
    ]


def test_never_stores_a_party_or_a_lawyer(cursor):
    esaj, _ = client(site())

    harvest(cursor, esaj)

    cursor.execute("SELECT payload::text FROM raw.court_site_case")
    for (payload,) in cursor.fetchall():
        assert "PARTE AUTORA" not in payload
        assert "EMPRESA RÉ" not in payload
        assert "ADVOGAD" not in payload
        assert "OAB" not in payload


def test_skips_the_cases_already_harvested(cursor):
    esaj, _ = client(site())
    harvest(cursor, esaj)
    again, session = client(site())

    counts = harvest(cursor, again)

    assert counts == {}
    assert session.urls == []


def test_harvests_everything_again_when_asked_to_refresh(cursor):
    esaj, _ = client(site())
    harvest(cursor, esaj)
    again, _ = client(site(first=page("not_found.html")))

    counts = harvest(cursor, again, refresh=True)

    assert counts == {"found": 1, "not_found": 1}
    assert stored(cursor)[0][3] == "not_found"


def test_records_the_cases_the_site_does_not_have_or_seals(cursor):
    esaj, _ = client(site(first=page("not_found.html"), second=page("sealed.html")))

    counts = harvest(cursor, esaj)

    assert counts == {"not_found": 1, "sealed": 1}
    assert [(row[3], row[4]) for row in stored(cursor)] == [("not_found", {}), ("sealed", {})]


def test_harvests_at_most_the_limit(cursor):
    esaj, _ = client(site())

    counts = harvest(cursor, esaj, limit=1)

    assert counts == {"found": 1}
    assert [row[0] for row in stored(cursor)] == [FIRST]


def test_keeps_what_was_harvested_when_the_site_blocks(dw_ready, monkeypatch, capsys):
    seed(dw_ready)
    pages = site(second=FakeResponse("", status_code=403))
    monkeypatch.setenv("DATABASE_URL", dw_ready)

    code = main([], session_factory=lambda: FakeSession(pages), sleep=lambda _seconds: None)

    assert code == 1
    err = capsys.readouterr().err
    assert "403" in err
    assert "1 coletados antes da parada" in err
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("SELECT case_number, status FROM raw.court_site_case")
        assert cur.fetchall() == [(FIRST, "found")]


def test_main_reports_what_was_harvested(dw_ready, monkeypatch, capsys):
    seed(dw_ready)
    pages = site(second=page("not_found.html"))
    monkeypatch.setenv("DATABASE_URL", dw_ready)

    code = main([], session_factory=lambda: FakeSession(pages), sleep=lambda _seconds: None)

    assert code == 0
    assert "TJSP: 1 coletados, 1 não encontrados, 0 em sigilo" in capsys.readouterr().out


def test_main_passes_the_limit_and_the_refresh_flag(dw_ready, monkeypatch, capsys):
    seed(dw_ready)
    monkeypatch.setenv("DATABASE_URL", dw_ready)

    main(["--limit", "1"], session_factory=lambda: FakeSession(site()), sleep=lambda _s: None)
    code = main(
        ["--refresh", "--limit", "1"],
        session_factory=lambda: FakeSession(site()),
        sleep=lambda _s: None,
    )

    assert code == 0
    assert "TJSP: 1 coletados" in capsys.readouterr().out.splitlines()[-1]


def test_main_reports_a_missing_database(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err
