import math

import psycopg2
import pytest

from pipeline.embedding import MODEL
from pipeline.precedent_link import METHOD, THRESHOLD, TOP_K, link, links, precedent_text


def unit(angle):
    return [math.cos(math.radians(angle)), math.sin(math.radians(angle))]


REAJUSTE = "Reajuste por faixa etária em plano de saúde"
CIRURGIA = "Cobertura de cirurgia bariátrica"
TEMA_952 = "Validade do reajuste. O reajuste por faixa etária do plano é válido."
TEMA_1016 = "Planos coletivos. A tese do reajuste por faixa etária vale para os coletivos."
TEMA_DISTANTE = "Prazo prescricional. O reajuste prescreve em três anos."
TEMA_SEM_TERMOS = "Validade da cláusula. A cláusula do contrato é válida."

VECTORS = {
    REAJUSTE: unit(0),
    CIRURGIA: unit(90),
    TEMA_952: unit(5),
    TEMA_1016: unit(12),
    TEMA_DISTANTE: unit(70),
    TEMA_SEM_TERMOS: unit(2),
}


def fake_encoder(texts):
    return [VECTORS[text] for text in texts]


def test_declares_the_threshold_the_method_and_the_model():
    assert THRESHOLD == 0.55
    assert TOP_K == 10
    assert METHOD == "embedding_cosine+lexical"
    assert MODEL == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_compares_the_theme_with_the_question_and_the_thesis():
    assert precedent_text("Validade do reajuste.", "O reajuste é válido.") == (
        "Validade do reajuste. O reajuste é válido."
    )
    assert precedent_text(None, "O reajuste é válido.") == "O reajuste é válido."


def test_ties_a_precedent_to_the_theme_above_the_declared_threshold():
    themes = [(1, REAJUSTE), (2, CIRURGIA)]
    precedents = [(10, TEMA_952), (11, TEMA_DISTANTE), (12, TEMA_SEM_TERMOS)]

    result = links(themes, precedents, fake_encoder)

    assert [(theme, precedent, method, model) for theme, precedent, method, _, model in result] == [
        (1, 10, METHOD, MODEL),
    ]
    assert result[0][3] == pytest.approx(math.cos(math.radians(5)))


def test_ties_nothing_without_themes_or_precedents():
    assert links([], [(10, TEMA_952)], fake_encoder) == []
    assert links([(1, REAJUSTE)], [], fake_encoder) == []


SEED = """
INSERT INTO dw.dim_theme (theme_name, theme_key) VALUES (%s, 1), (%s, 2);
INSERT INTO dw.dim_precedent
    (precedent_kind, precedent_number, thesis, question, status, source_url, extracted_at)
VALUES
    ('Tema', 952, 'O reajuste por faixa etária do plano é válido.', 'Validade do reajuste.',
     'Trânsito em Julgado', 'https://stj.jus.br/952', now()),
    ('Tema', 990, 'O reajuste prescreve em três anos.', 'Prazo prescricional.',
     'Trânsito em Julgado', 'https://stj.jus.br/990', now());
"""


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_theme, dw.dim_precedent RESTART IDENTITY CASCADE")
        cur.execute(SEED, (REAJUSTE, CIRURGIA))
        yield cur
        connection.rollback()


def stored_links(cursor):
    cursor.execute(
        "SELECT t.theme_key, p.precedent_number, b.link_method, b.embedding_model "
        "FROM dw.bridge_theme_precedent b JOIN dw.dim_theme t USING (theme_sk) "
        "JOIN dw.dim_precedent p USING (precedent_sk) ORDER BY 1, 2"
    )
    return cursor.fetchall()


def test_link_stores_the_ties_of_every_theme(cursor):
    assert link(cursor, fake_encoder) == 1

    assert stored_links(cursor) == [(1, 952, METHOD, MODEL)]
