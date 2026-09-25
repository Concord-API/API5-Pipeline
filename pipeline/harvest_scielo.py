import argparse
import sys

import psycopg2
import requests

from pipeline import config, scielo
from pipeline.raw_schema import ensure


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_scielo")
    parser.add_argument("--issn", action="append")
    return parser.parse_args(argv)


def main(argv=None, session_factory=requests.Session, collect_fn=scielo.collect):
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
                changed = collect_fn(
                    session,
                    cursor,
                    issns=args.issn,
                    on_journal=lambda issn, found, updated: print(
                        f"{issn}: {found} articles, {updated} new or updated", flush=True
                    ),
                )
                connection.commit()
            finally:
                session.close()
    except (scielo.SciELOError, requests.RequestException, psycopg2.Error) as error:
        if connection is not None:
            connection.rollback()
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()
    print(f"SciELO harvest: {changed} new or updated articles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
