import psycopg2
import pytest

from pipeline.theme_registry import ensure, get_or_create_key


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        ensure(cur)
        cur.execute("TRUNCATE etl.theme_registry RESTART IDENTITY CASCADE")
        yield cur
        connection.commit()


def test_running_ensure_again_does_not_fail(cursor):
    ensure(cursor)


def test_a_new_name_gets_a_new_key(cursor):
    key = get_or_create_key(cursor, "Tema A")

    assert key is not None


def test_the_same_name_always_gets_the_same_key(cursor):
    first = get_or_create_key(cursor, "Tema A")
    second = get_or_create_key(cursor, "Tema A")

    assert first == second


def test_different_names_get_different_keys(cursor):
    a = get_or_create_key(cursor, "Tema A")
    b = get_or_create_key(cursor, "Tema B")

    assert a != b
