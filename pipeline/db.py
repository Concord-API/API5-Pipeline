from contextlib import contextmanager

import psycopg2


@contextmanager
def transaction(dsn: str):
    connection = psycopg2.connect(dsn)
    try:
        with connection.cursor() as cursor:
            yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
