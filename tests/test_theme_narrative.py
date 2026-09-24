import json
from datetime import date

import psycopg2
import pytest

from pipeline.theme_narrative import compose, generate

FACTS = {
    "judged": 144,
    "upheld_ratio": 0.9861,
    "polarity_label": "acolhimento da pretensão do autor",
    "court_count": 3,
    "period_start_year": 2021,
    "period_end_year": 2026,
    "last_decision_date": date(2026, 8, 30),
    "merit_judged": 144,
    "merit_ratio": 0.9861,
    "appeal_judged": 0,
    "appeal_ratio": None,
}


def test_the_lead_opens_with_the_upheld_ratio_and_its_judged_count():
    lead, _ = compose(FACTS)

    assert lead == [
        {"text": "Em "},
        {"ratio": 0.9861, "n": 144, "unit": "decisões"},
        {"text": " julgadas, houve acolhimento da pretensão do autor."},
    ]


def test_the_body_states_courts_period_and_last_decision():
    _, body = compose(FACTS)

    assert body == [
        {"text": "As decisões vêm de 3 tribunais, entre 2021 e 2026."},
        {"text": " A última decisão é de 30.08.2026."},
    ]


def test_the_body_uses_a_single_court_and_a_single_year():
    facts = {**FACTS, "court_count": 1, "period_start_year": 2026}

    _, body = compose(facts)

    assert body[0] == {"text": "As decisões vêm de 1 tribunal, em 2026."}


def test_the_body_leaves_out_what_the_aggregates_do_not_have():
    facts = {
        **FACTS,
        "period_start_year": None,
        "period_end_year": None,
        "last_decision_date": None,
    }

    _, body = compose(facts)

    assert body == [{"text": "As decisões vêm de 3 tribunais."}]


def test_the_body_separates_merit_and_appeal_when_both_exist():
    facts = {**FACTS, "appeal_judged": 12, "appeal_ratio": 0.25}

    _, body = compose(facts)

    assert body[2:] == [
        {"text": " No mérito, houve acolhimento em "},
        {"ratio": 0.9861, "n": 144, "unit": "decisões"},
        {"text": ". Nos recursos, houve provimento em "},
        {"ratio": 0.25, "n": 12, "unit": "decisões"},
        {"text": "."},
    ]


SEED = """
INSERT INTO dw.strength_config (methodology_version, reference_year) VALUES ('1.0', 2026);
INSERT INTO dw.dim_decision_outcome (outcome_code, outcome_label, counts_in_metric)
VALUES ('Granted', 'Procedente', true), ('Denied', 'Improcedente', true);
INSERT INTO dw.dim_movement
    (movement_code, movement_name, outcome_sk, code_verified, polarity_reference)
SELECT 219, 'Procedência', outcome_sk, true, 'pretensao_autor'
FROM dw.dim_decision_outcome WHERE outcome_code = 'Granted';
INSERT INTO dw.dim_movement
    (movement_code, movement_name, outcome_sk, code_verified, polarity_reference)
SELECT 220, 'Improcedência', outcome_sk, true, 'pretensao_autor'
FROM dw.dim_decision_outcome WHERE outcome_code = 'Denied';
INSERT INTO dw.dim_court (court_code, court_name, state_uf)
VALUES ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP');
INSERT INTO dw.dim_case_class (class_name, claimant_type)
VALUES ('Ação de indenização', 'autor_particular');
INSERT INTO dw.dim_date (date_sk, full_date, year, quarter, month, month_name, day)
VALUES (20250615, '2025-06-15', 2025, 2, 6, 'Junho', 15);
INSERT INTO dw.dim_theme (theme_name, theme_key)
VALUES ('Tema julgado', 1), ('Tema sem processos', 2);
INSERT INTO dw.dim_subject (subject_name, subject_code) VALUES ('Assunto julgado', 100);
INSERT INTO dw.bridge_theme_subject (theme_sk, subject_sk)
SELECT t.theme_sk, s.subject_sk FROM dw.dim_theme t, dw.dim_subject s WHERE t.theme_key = 1;
INSERT INTO dw.dim_case (case_number, court_sk, case_class_sk, court_level, source, extracted_at)
SELECT 'CASE-' || n, c.court_sk, cc.case_class_sk, 'First', 'datajud', now()
FROM generate_series(1, 3) n CROSS JOIN dw.dim_court c CROSS JOIN dw.dim_case_class cc;
INSERT INTO dw.bridge_case_subject (case_sk, subject_sk)
SELECT dc.case_sk, s.subject_sk FROM dw.dim_case dc CROSS JOIN dw.dim_subject s;
INSERT INTO dw.fact_case_event
    (case_sk, court_sk, movement_sk, date_sk, occurred_at, source_url, extracted_at, natural_key)
SELECT dc.case_sk, dc.court_sk, m.movement_sk, 20250615, TIMESTAMPTZ '2025-06-15',
       'https://example.org', now(), 'evt:' || dc.case_sk
FROM dw.dim_case dc
JOIN dw.dim_movement m
    ON m.movement_code = CASE WHEN dc.case_number = 'CASE-3' THEN 220 ELSE 219 END;
"""


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.fact_case_event, dw.bridge_case_subject, dw.bridge_theme_subject, "
            "dw.dim_case, dw.dim_theme, dw.dim_subject, dw.dim_movement, dw.dim_judging_body, "
            "dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome, dw.dim_date, "
            "dw.strength_config, dw.theme_narrative RESTART IDENTITY CASCADE"
        )
        cur.execute(SEED)
        yield cur
        connection.commit()


def narratives(cursor):
    cursor.execute(
        "SELECT t.theme_key, n.lead, n.body, n.text_origin, n.methodology_version, n.generated_at "
        "FROM dw.theme_narrative n JOIN dw.dim_theme t ON t.theme_sk = n.theme_sk "
        "ORDER BY t.theme_key"
    )
    return cursor.fetchall()


def test_generates_the_text_of_a_judged_theme_from_the_aggregates(cursor):
    generate(cursor, date(2026, 9, 23))

    [(theme_key, lead, body, origin, version, generated_at)] = narratives(cursor)
    assert theme_key == 1
    assert lead[1] == {"ratio": 0.6667, "n": 3, "unit": "decisões"}
    assert lead[2] == {"text": " julgadas, houve acolhimento da pretensão do autor."}
    assert body[0] == {"text": "As decisões vêm de 1 tribunal, em 2025."}
    assert (origin, version, generated_at) == ("template", "1.0", date(2026, 9, 23))


def test_generating_twice_keeps_one_text_per_theme(cursor):
    generate(cursor, date(2026, 9, 23))
    generate(cursor, date(2026, 9, 24))

    rows = narratives(cursor)
    assert [row[0] for row in rows] == [1]
    assert rows[0][5] == date(2026, 9, 24)


def test_stores_the_segments_as_json(cursor):
    generate(cursor, date(2026, 9, 23))

    cursor.execute("SELECT jsonb_typeof(lead), jsonb_typeof(body) FROM dw.theme_narrative")
    assert cursor.fetchone() == ("array", "array")
    assert json.loads(json.dumps(narratives(cursor)[0][1]))[0] == {"text": "Em "}
