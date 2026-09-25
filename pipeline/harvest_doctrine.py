import sys

import psycopg2
import requests

from pipeline import config
from pipeline.raw_schema import ensure


def run(collect, error_type, source, session_factory=requests.Session):
    config.load_env()
    try:
        dsn = config.database_url()
    except config.ConfigurationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    try:
        connection = psycopg2.connect(dsn)
    except psycopg2.Error as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    try:
        with connection.cursor() as cursor:
            ensure(cursor)
            connection.commit()
            session = session_factory()
            session.headers.update({"User-Agent": "Ratio-DW/1.0 (FATEC API-5)"})
            try:
                changed = collect(session, cursor)
                connection.commit()
            finally:
                session.close()
    except (error_type, requests.RequestException, psycopg2.Error) as error:
        connection.rollback()
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    print(f"{source} harvest: {changed} new or updated articles")
    return 0
