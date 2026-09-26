import psycopg2

from pipeline.raw_schema import ensure


def table_exists(dsn, table="raw.datajud_case"):
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
        return cursor.fetchone()[0]


def test_creates_the_raw_schema_on_an_empty_database(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
    connection.close()

    assert table_exists(postgres_url)
    assert table_exists(postgres_url, "raw.doctrine_article")


def test_running_it_again_does_not_fail(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        ensure(cursor)
    connection.close()

    assert table_exists(postgres_url)
    assert table_exists(postgres_url, "raw.doctrine_article")


def test_doctrine_source_and_hash_must_be_unique(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        cursor.execute("TRUNCATE raw.doctrine_article")
        cursor.execute(
            """
            INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
            VALUES ('doaj', 'https://doaj.org/article/abc', 'abc', '{}')
            ON CONFLICT (source, payload_hash) DO NOTHING
            """
        )
        cursor.execute(
            """
            INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
            VALUES ('doaj', 'https://doaj.org/article/abc', 'abc', '{}')
            ON CONFLICT (source, payload_hash) DO NOTHING
            """
        )
        cursor.execute("SELECT count(*) FROM raw.doctrine_article")
        assert cursor.fetchone()[0] == 1
