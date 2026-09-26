import json

import psycopg2
import pytest

from pipeline.dw_doctrine import load, transform
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


def dimension(cursor):
    cursor.execute(
        "SELECT doctrine_sk, source, title, doi, article_url, publication_year "
        "FROM dw.dim_doctrine ORDER BY doctrine_sk"
    )
    return cursor.fetchall()


def transform_and_load(cursor):
    transform(cursor)
    load(cursor)


def test_loads_articles_with_and_without_doi(cursor):
    insert_raw(cursor, "doaj", "https://doaj.org/article/b", doaj("Artigo B", "10.1/b"))
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Artigo A"))

    transform_and_load(cursor)

    assert sorted(row[1:] for row in dimension(cursor)) == [
        ("doaj", "Artigo B", "10.1/b", "https://doaj.org/article/b", 2021),
        ("oai_emerj", "Artigo A", None, "https://emerj/1", 2020),
    ]


def test_loading_twice_does_not_duplicate_an_article(cursor):
    insert_raw(cursor, "doaj", "https://doaj.org/article/b", doaj("Artigo B", "10.1/b"))
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Artigo A"))
    transform_and_load(cursor)
    first = dimension(cursor)

    transform_and_load(cursor)

    assert dimension(cursor) == first


def test_updates_an_article_harvested_again(cursor):
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Titulo antigo"),
               collected_at="2026-09-01T00:00:00Z")
    transform_and_load(cursor)
    [(key, *_)] = dimension(cursor)

    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Titulo novo", dates=["2019"]),
               collected_at="2026-09-10T00:00:00Z")
    transform_and_load(cursor)

    assert dimension(cursor) == [(key, "oai_emerj", "Titulo novo", None, "https://emerj/1", 2019)]


def test_an_article_that_gains_a_doi_keeps_its_row(cursor):
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Artigo A"),
               collected_at="2026-09-01T00:00:00Z")
    transform_and_load(cursor)
    [(key, *_)] = dimension(cursor)

    insert_raw(cursor, "oai_emerj", "https://emerj/1",
               oai("Artigo A", ["https://doi.org/10.9/a", "https://emerj/1"]),
               collected_at="2026-09-10T00:00:00Z")
    transform_and_load(cursor)

    assert dimension(cursor) == [(key, "oai_emerj", "Artigo A", "10.9/a", "https://emerj/1", 2020)]


def test_every_loaded_article_has_a_doi_or_an_address(cursor):
    insert_raw(cursor, "doaj", "https://doaj.org/article/b", doaj("Artigo B", "10.1/b"))
    insert_raw(cursor, "oai_emerj", "https://emerj/1", oai("Artigo A"))

    transform_and_load(cursor)

    cursor.execute(
        "SELECT count(*) FROM dw.dim_doctrine WHERE doi IS NULL AND article_url IS NULL"
    )
    assert cursor.fetchone() == (0,)
