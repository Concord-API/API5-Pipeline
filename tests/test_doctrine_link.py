import math

import psycopg2
import pytest

from pipeline.doctrine_link import (
    METHOD,
    THRESHOLD,
    TOP_K,
    distinctive_tokens,
    lexical_match,
    link,
    links,
)
from pipeline.embedding import MODEL


def unit(angle):
    return [math.cos(math.radians(angle)), math.sin(math.radians(angle))]


VECTORS = {
    "Indenização por Dano Moral": unit(0),
    "Dano moral: quantificação na jurisprudência": unit(10),
    "Moral e contemporaneidade": unit(1),
    "Dano moral em perspectiva comparada": unit(70),
    "Dano Moral Coletivo": unit(15),
    "Contratos Bancários": unit(90),
    "Revisão de contratos bancários": unit(92),
}


def fake_encoder(texts):
    return [VECTORS[text] for text in texts]


def failing_encoder(texts):
    raise AssertionError("the model must not be loaded")


def test_declares_the_threshold_the_method_and_the_model():
    assert THRESHOLD == 0.55
    assert TOP_K == 10
    assert METHOD == "embedding_cosine+lexical"
    assert MODEL == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_keeps_only_the_distinctive_terms_of_a_subject():
    assert distinctive_tokens("Indenização por Dano Moral") == ["indenizacao", "dano", "moral"]
    assert distinctive_tokens("Contratos em Geral") == ["contratos"]
    assert distinctive_tokens("de e da") == []


@pytest.mark.parametrize("subject, title, expected", [
    ("Indenização por Dano Moral", "Dano moral: quantificação", True),
    ("Indenização por Dano Moral", "Moral e contemporaneidade", False),
    ("Contratos em Geral", "Teoria dos contratos", True),
    ("Contratos em Geral", "Responsabilidade civil", False),
    ("Contratos Bancários", "Revisão de contratação bancária", True),
    ("de e da", "de e da", False),
])
def test_requires_the_subject_terms_in_the_title(subject, title, expected):
    assert lexical_match(distinctive_tokens(subject), title) is expected


def test_links_by_similarity_and_lexical_match_recording_score_method_and_model():
    subjects = [(1, "Indenização por Dano Moral"), (2, "Contratos Bancários")]
    articles = [
        (10, "Dano moral: quantificação na jurisprudência"),
        (11, "Moral e contemporaneidade"),
        (12, "Dano moral em perspectiva comparada"),
        (13, "Revisão de contratos bancários"),
    ]

    result = links(subjects, articles, fake_encoder)

    assert [(s, d, m, e) for s, d, m, _, e in result] == [
        (1, 10, METHOD, MODEL),
        (2, 13, METHOD, MODEL),
    ]
    assert result[0][3] == pytest.approx(math.cos(math.radians(10)))


def test_keeps_only_the_most_similar_subjects_of_an_article():
    subjects = [(1, "Indenização por Dano Moral"), (3, "Dano Moral Coletivo")]
    articles = [(10, "Dano moral: quantificação na jurisprudência")]

    assert [row[:2] for row in links(subjects, articles, fake_encoder)] == [(1, 10), (3, 10)]
    assert [row[:2] for row in links(subjects, articles, fake_encoder, top_k=1)] == [(3, 10)]


def test_links_nothing_without_subjects_or_articles():
    assert links([], [(10, "Dano moral")], failing_encoder) == []
    assert links([(1, "Dano Moral")], [], failing_encoder) == []


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_doctrine, dw.dim_subject RESTART IDENTITY CASCADE")
        yield cur
        connection.commit()


def seed(cursor):
    cursor.execute(
        "INSERT INTO dw.dim_subject (subject_name, subject_code) VALUES "
        "('Indenização por Dano Moral', 1), ('Contratos Bancários', 2)"
    )
    cursor.execute(
        "INSERT INTO dw.dim_doctrine (title, article_url, source, extracted_at) VALUES "
        "('Dano moral: quantificação na jurisprudência', 'https://a', 'oai_emerj', now()), "
        "('Moral e contemporaneidade', 'https://b', 'oai_emerj', now()), "
        "('Revisão de contratos bancários', 'https://c', 'doaj', now())"
    )


def bridge(cursor):
    cursor.execute(
        "SELECT s.subject_name, d.title, b.link_method, b.embedding_model, b.similarity > 0.55 "
        "FROM dw.bridge_subject_doctrine b "
        "JOIN dw.dim_subject s USING (subject_sk) JOIN dw.dim_doctrine d USING (doctrine_sk) "
        "ORDER BY 1, 2"
    )
    return cursor.fetchall()


def test_writes_the_links_to_the_bridge(cursor):
    seed(cursor)

    assert link(cursor, fake_encoder) == 2

    assert bridge(cursor) == [
        ("Contratos Bancários", "Revisão de contratos bancários", METHOD, MODEL, True),
        ("Indenização por Dano Moral", "Dano moral: quantificação na jurisprudência",
         METHOD, MODEL, True),
    ]


def test_relinking_rebuilds_the_bridge_without_duplicates(cursor):
    seed(cursor)
    link(cursor, fake_encoder)

    assert link(cursor, fake_encoder) == 2
    assert len(bridge(cursor)) == 2


def test_does_not_load_the_model_without_doctrine(cursor):
    cursor.execute("INSERT INTO dw.dim_subject (subject_name, subject_code) VALUES ('A', 1)")

    assert link(cursor, failing_encoder) == 0
