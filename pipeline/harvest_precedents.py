import argparse
import sys
from pathlib import Path

import psycopg2
import requests

from pipeline import config, stj_precedents
from pipeline.raw_schema import ensure


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_precedents")
    parser.add_argument("--file", help="Temas.csv já baixado, quando o portal do STJ estiver fora")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config.load_env()
    try:
        dsn = config.database_url()
    except config.ConfigurationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    def read_file(_url):
        return Path(args.file).read_text(encoding="utf-8")

    fetch = read_file if args.file else stj_precedents.download
    try:
        with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
            ensure(cursor)
            stored = stj_precedents.harvest(cursor, fetch)
    except (requests.RequestException, psycopg2.Error, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"STJ precedents harvest: {stored} STJ themes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
