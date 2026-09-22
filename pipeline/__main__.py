import argparse
import sys

import psycopg2

from pipeline import config, harvest, theme_build, tpu
from pipeline.raw_schema import ensure as ensure_raw
from pipeline.run import run


class MissingSchemaError(Exception):
    pass


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("--skip-harvest", action="store_true")
    return parser.parse_args(argv)


def assert_dw_exists(cursor):
    cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'dw'")
    if cursor.fetchone() is None:
        raise MissingSchemaError(
            "schema dw not found: start the API against this database first"
        )


def main(argv=None, session_factory=harvest.new_session, runner=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        dsn = config.database_url()
        api_key = None if args.skip_harvest else config.datajud_api_key()
        output_path = config.load_file_path()
        connection = psycopg2.connect(dsn)
        try:
            with connection.cursor() as cursor:
                assert_dw_exists(cursor)
                ensure_raw(cursor)
                connection.commit()
                vocabulary = tpu.load()
                if api_key is not None:
                    inserted = harvest.harvest(session_factory(api_key), cursor, vocabulary)
                    print(f"harvest: {inserted} new cases")
                run(
                    cursor, dsn, vocabulary, theme_build.load_groups(), output_path,
                    runner=runner,
                )
            connection.commit()
        finally:
            connection.close()
    except (config.ConfigurationError, MissingSchemaError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"load file: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
