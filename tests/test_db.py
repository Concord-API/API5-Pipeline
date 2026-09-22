import psycopg2
import pytest

from pipeline.db import transaction


@pytest.fixture
def table(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TABLE marks (id serial PRIMARY KEY)")
    return postgres_url


def row_count(dsn):
    with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM marks")
        return cursor.fetchone()[0]


def test_commits_when_the_block_succeeds(table):
    with transaction(table) as cursor:
        cursor.execute("INSERT INTO marks DEFAULT VALUES")

    assert row_count(table) == 1


def test_rolls_back_when_the_block_raises(table):
    with pytest.raises(ValueError):
        with transaction(table) as cursor:
            cursor.execute("INSERT INTO marks DEFAULT VALUES")
            raise ValueError("boom")

    assert row_count(table) == 0
