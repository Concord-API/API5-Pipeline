from datetime import date

import psycopg2
import pytest

from pipeline.dw_date import FIRST_DAY, seed


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_date RESTART IDENTITY CASCADE")
        yield cur
        connection.rollback()


def test_the_calendar_starts_in_1940():
    assert FIRST_DAY == date(1940, 1, 1)


def test_seeds_every_day_until_the_end_of_the_given_year(cursor):
    seed(cursor, 2027)

    cursor.execute("SELECT count(*), min(full_date), max(full_date) FROM dw.dim_date")
    count, first, last = cursor.fetchone()
    assert first == date(1940, 1, 1)
    assert last == date(2027, 12, 31)
    assert count == (date(2027, 12, 31) - date(1940, 1, 1)).days + 1


def test_the_day_key_and_its_attributes(cursor):
    seed(cursor, 2027)

    cursor.execute(
        "SELECT date_sk, year, quarter, month, month_name, day "
        "FROM dw.dim_date WHERE full_date = '2025-06-15'"
    )
    assert cursor.fetchone() == (20250615, 2025, 2, 6, "June", 15)


def test_seeding_twice_does_not_duplicate_a_day(cursor):
    seed(cursor, 2027)
    seed(cursor, 2027)

    cursor.execute("SELECT count(*) - count(DISTINCT full_date) FROM dw.dim_date")
    assert cursor.fetchone()[0] == 0


def test_a_later_load_extends_the_calendar(cursor):
    seed(cursor, 2027)
    seed(cursor, 2028)

    cursor.execute("SELECT max(full_date) FROM dw.dim_date")
    assert cursor.fetchone()[0] == date(2028, 12, 31)
