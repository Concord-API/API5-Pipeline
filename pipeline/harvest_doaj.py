import argparse
import sys

import psycopg2
import requests

from pipeline import config, doaj
from pipeline.raw_schema import ensure


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_doaj")
    parser.add_argument("--term", action="append")
    parser.add_argument("--year", action="append", type=int)
    return parser.parse_args(argv)


def main(argv=None, session_factory=requests.Session, collect_fn=doaj.collect):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config.load_env()
    try:
        dsn = config.database_url()
    except config.ConfigurationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    connection = None
    try:
        connection = psycopg2.connect(dsn)
        with connection.cursor() as cursor:
            ensure(cursor)
            connection.commit()
            session = session_factory()
            session.headers.update({"User-Agent": "Ratio-DW/1.0 (FATEC API-5)"})
            try:
                inserted = collect_fn(
                    session,
                    cursor,
                    terms=args.term,
                    years=args.year,
                    on_bucket=lambda term, year, changed: print(
                        f"{term} / {year}: {changed} new or updated articles", flush=True
                    ),
                )
                connection.commit()
            finally:
                session.close()
    except (doaj.DOAJError, requests.RequestException, psycopg2.Error) as error:
        if connection is not None:
            connection.rollback()
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()
    print(f"DOAJ harvest: {inserted} new or updated articles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
