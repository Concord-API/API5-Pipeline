import json

import psycopg2
import pytest

from pipeline.dw_doctrine import transform
from pipeline.raw_schema import ensure as ensure_raw


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        ensure_raw(cur)
        cur.execute("TRUNCATE raw.doctrine_article RESTART IDENTITY")
        cur.execute("TRUNCATE dw.dim_doctrine RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE staging.doctrine_article")
        yield cur
        connection.commit()


def insert_raw(cursor, source, source_url, payload, collected_at="2026-09-20T10:00:00Z"):
    cursor.execute(
        "INSERT INTO raw.doctrine_article "
        "(source, source_url, collected_at, payload_hash, payload) "
        "VALUES (%s, %s, %s, md5(random()::text), %s)",
        (source, source_url, collected_at, json.dumps(payload)),
    )


def oai(title, identifiers=(), dates=("2020",)):
    return {"title": title, "identifiers": list(identifiers), "dates": list(dates),
            "creators": ["Autor"], "source": "Revista"}


def doaj(title, doi):
    return {"id": title, "bibjson": {
        "title": title, "year": "2021", "identifier": [{"type": "doi", "id": doi}],
        "link": [], "author": [], "subject": [], "journal": {"title": "Revista DOAJ"},
    }}


def staged(cursor):
    cursor.execute(
        "SELECT source, title, doi, article_url FROM staging.doctrine_article "
        "ORDER BY source, title"
    )
    return cursor.fetchall()


def test_stages_one_row_per_harvested_article(cursor):
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Artigo A"))
    insert_raw(cursor, "doaj", "https://doaj.org/article/b", doaj("Artigo B", "10.1/B"))

    assert transform(cursor) == 2

    assert staged(cursor) == [
        ("doaj", "Artigo B", "10.1/b", "https://doaj.org/article/b"),
        ("oai_emerj", "Artigo A", None, "https://emerj/1"),
    ]


def test_skips_articles_without_title(cursor):
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai(None))

    assert transform(cursor) == 0
    assert staged(cursor) == []


def test_keeps_the_latest_harvest_of_the_same_doi_across_sources(cursor):
    insert_raw(cursor, "doaj", "https://doaj.org/article/a", doaj("Antigo", "10.1/x"),
               collected_at="2026-09-01T00:00:00Z")
    insert_raw(cursor, "oai_indexlaw", "https://indexlaw/a",
               oai("Novo", ["https://doi.org/10.1/X"]), collected_at="2026-09-10T00:00:00Z")

    transform(cursor)

    assert staged(cursor) == [("oai_indexlaw", "Novo", "10.1/x", "https://indexlaw/a")]


def test_keeps_one_row_per_source_and_address(cursor):
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Primeira"),
               collected_at="2026-09-01T00:00:00Z")
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Segunda"),
               collected_at="2026-09-10T00:00:00Z")

    transform(cursor)

    assert staged(cursor) == [("oai_emerj", "Segunda", None, "https://emerj/1")]


def test_restages_from_scratch_on_every_run(cursor):
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Artigo A"))
    transform(cursor)

    assert transform(cursor) == 1
    assert len(staged(cursor)) == 1
