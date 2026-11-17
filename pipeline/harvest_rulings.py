import argparse
import sys

import psycopg2
import requests

from pipeline import config, stj_rulings
from pipeline.raw_schema import ensure


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_rulings")
    parser.add_argument(
        "--dir", help="pasta com os arquivos já baixados, uma subpasta por órgão julgador"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config.load_env()
    try:
        dsn = config.database_url()
    except config.ConfigurationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    try:
        with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
            ensure(cursor)
            if args.dir:
                stored = stj_rulings.harvest_folder(cursor, args.dir)
            else:
                stored = stj_rulings.harvest(cursor)
    except (psycopg2.Error, OSError, requests.RequestException, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"STJ rulings harvest: {stored} STJ rulings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
