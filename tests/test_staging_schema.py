import psycopg2

from pipeline.staging_schema import ensure


def table_exists(dsn):
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('staging.case_event') IS NOT NULL")
        return cursor.fetchone()[0]


def test_creates_the_staging_schema_on_an_empty_database(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
    connection.close()

    assert table_exists(postgres_url)


def test_running_it_again_does_not_fail(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        ensure(cursor)
    connection.close()

    assert table_exists(postgres_url)
