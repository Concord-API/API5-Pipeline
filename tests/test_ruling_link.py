import math

import psycopg2
import pytest

from pipeline.doctrine_link import METHOD, THRESHOLD
from pipeline.ruling_link import EXACT_METHOD, TOP_K, link, links


def unit(angle):
    return [math.cos(math.radians(angle)), math.sin(math.radians(angle))]


REAJUSTE = "Reajuste por faixa etária em plano de saúde"
CIRURGIA = "Cobertura de cirurgia bariátrica"
EMENTA_REAJUSTE = "PLANO DE SAÚDE. REAJUSTE POR FAIXA ETÁRIA. VALIDADE DA CLÁUSULA."
EMENTA_DISTANTE = "PLANO DE SAÚDE. REAJUSTE POR FAIXA ETÁRIA. PRESCRIÇÃO."
EMENTA_SEM_TERMOS = "PROCESSUAL CIVIL. AGRAVO INTERNO. SÚMULA 7."
EMENTA_EXATA = "PROCESSUAL CIVIL. RECURSO ESPECIAL. CONTRATOS."

VECTORS = {
    REAJUSTE: unit(0),
    CIRURGIA: unit(90),
    EMENTA_REAJUSTE: unit(5),
    EMENTA_DISTANTE: unit(70),
    EMENTA_SEM_TERMOS: unit(2),
    EMENTA_EXATA: unit(80),
}


def fake_encoder(texts):
    return [VECTORS[text] for text in texts]


def test_declares_the_methods_the_threshold_and_the_closest_themes_kept():
    assert EXACT_METHOD == "cnj_exact"
    assert METHOD == "embedding_cosine+lexical"
    assert THRESHOLD == 0.55
    assert TOP_K == 3


def test_ties_a_ruling_to_the_theme_above_the_declared_threshold():
    themes = [(1, REAJUSTE), (2, CIRURGIA)]
    rulings = [(10, EMENTA_REAJUSTE), (11, EMENTA_DISTANTE), (12, EMENTA_SEM_TERMOS)]

    result = links(themes, rulings, fake_encoder)

    ties = [(theme, ruling, method, limit) for theme, ruling, method, _, limit in result]
    assert ties == [(1, 10, METHOD, THRESHOLD)]
    assert result[0][3] == pytest.approx(math.cos(math.radians(5)))


def test_keeps_only_the_closest_themes_of_each_ruling():
    themes = [(1, REAJUSTE), (2, REAJUSTE + " coletivo")]
    VECTORS[REAJUSTE + " coletivo"] = unit(1)

    result = links(themes, [(10, EMENTA_REAJUSTE)], fake_encoder, top_k=1)

    assert [(theme, ruling) for theme, ruling, *_ in result] == [(2, 10)]


def test_ties_nothing_without_themes_or_rulings():
    assert links([], [(10, EMENTA_REAJUSTE)], fake_encoder) == []
    assert links([(1, REAJUSTE)], [], fake_encoder) == []


SEED = """
INSERT INTO dw.dim_court (court_code, court_name, state_uf)
VALUES ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP');
INSERT INTO dw.dim_theme (theme_name, theme_key) VALUES (%(reajuste)s, 1), (%(cirurgia)s, 2);
INSERT INTO dw.dim_subject (subject_name, subject_code)
VALUES ('Planos de Saúde', 6233), ('Contratos', 1127);
INSERT INTO dw.bridge_theme_subject (theme_sk, subject_sk)
SELECT t.theme_sk, s.subject_sk FROM dw.dim_theme t JOIN dw.dim_subject s
ON (t.theme_key, s.subject_code) IN ((1, 6233), (2, 1127));
INSERT INTO dw.dim_case (case_number, court_sk, court_level, source, extracted_at)
SELECT '10000012320248260100', court_sk, 'First', 'datajud', now() FROM dw.dim_court;
INSERT INTO dw.bridge_case_subject (case_sk, subject_sk)
SELECT c.case_sk, s.subject_sk FROM dw.dim_case c CROSS JOIN dw.dim_subject s
WHERE s.subject_code = 1127;
INSERT INTO dw.dim_ruling
    (source, source_id, case_number, court_code, summary, source_url, extracted_at)
VALUES
    ('stj_espelhos', 'r1', 'AgInt no REsp 1997135', 'STJ', %(reajuste_ementa)s,
     'https://stj/1', now()),
    ('stj_espelhos', 'r2', '1000001-23.2024.8.26.0100', 'STJ', %(exata)s,
     'https://stj/2', now()),
    ('stj_espelhos', 'r3', NULL, 'STJ', %(sem_termos)s, 'https://stj/3', now());
"""


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute(
            "TRUNCATE dw.dim_theme, dw.dim_subject, dw.dim_case, dw.dim_court, dw.dim_ruling, "
            "dw.bridge_case_subject, dw.bridge_theme_subject RESTART IDENTITY CASCADE"
        )
        cur.execute(SEED, {
            "reajuste": REAJUSTE,
            "cirurgia": CIRURGIA,
            "reajuste_ementa": EMENTA_REAJUSTE,
            "exata": EMENTA_EXATA,
            "sem_termos": EMENTA_SEM_TERMOS,
        })
        yield cur
        connection.rollback()


def stored_links(cursor):
    cursor.execute(
        "SELECT t.theme_key, r.source_id, b.link_method, b.similarity_threshold, "
        "b.similarity IS NULL "
        "FROM dw.bridge_theme_ruling b JOIN dw.dim_theme t USING (theme_sk) "
        "JOIN dw.dim_ruling r USING (ruling_sk) ORDER BY 1, 2"
    )
    return cursor.fetchall()


def test_ties_a_ruling_with_a_case_number_of_the_theme_exactly(cursor):
    link(cursor, fake_encoder)

    assert (2, "r2", EXACT_METHOD, None, True) in stored_links(cursor)


def test_ties_the_rulings_without_a_case_of_the_theme_by_similarity(cursor):
    assert link(cursor, fake_encoder) == 2

    assert stored_links(cursor) == [
        (1, "r1", METHOD, pytest.approx(THRESHOLD), False),
        (2, "r2", EXACT_METHOD, None, True),
    ]


def test_link_again_replaces_the_previous_ties(cursor):
    link(cursor, fake_encoder)
    cursor.execute(
        "UPDATE dw.dim_ruling SET summary = %s WHERE source_id = 'r1'", (EMENTA_SEM_TERMOS,)
    )

    assert link(cursor, fake_encoder) == 1

    assert stored_links(cursor) == [(2, "r2", EXACT_METHOD, None, True)]
