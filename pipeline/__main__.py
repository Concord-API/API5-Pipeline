import argparse
import sys

import psycopg2

from pipeline import config, harvest, integrity, theme_build, top_up, tpu
from pipeline.load_file import manifest_path
from pipeline.raw_schema import ensure as ensure_raw
from pipeline.run import run


class MissingSchemaError(Exception):
    pass


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline")
    parser.add_argument("--skip-harvest", action="store_true")
    parser.add_argument("--top-up", action="store_true")
    return parser.parse_args(argv)


def assert_dw_exists(cursor):
    cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'dw'")
    if cursor.fetchone() is None:
        raise MissingSchemaError(
            "schema dw not found: start the API against this database first"
        )


def main(argv=None, session_factory=harvest.new_session, runner=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config.load_env()
    try:
        dsn = config.database_url()
        needs_key = args.top_up or not args.skip_harvest
        api_key = config.datajud_api_key() if needs_key else None
        output_path = config.load_file_path()
        connection = psycopg2.connect(dsn)
        try:
            with connection.cursor() as cursor:
                assert_dw_exists(cursor)
                ensure_raw(cursor)
                connection.commit()
                vocabulary = tpu.load()
                if not args.skip_harvest:
                    inserted = harvest.harvest(session_factory(api_key), cursor, vocabulary)
                    print(f"harvest: {inserted} new cases")
                groups = theme_build.load_groups()
                run(cursor, dsn, vocabulary, groups, output_path, runner=runner)
                if args.top_up:
                    before = top_up.themes_with_at_least(cursor)
                    subjects = top_up.thin_subject_codes(cursor)
                    inserted = top_up.harvest(
                        session_factory(api_key), cursor, vocabulary, subjects
                    )
                    run(cursor, dsn, vocabulary, groups, output_path, runner=runner)
                    after = top_up.themes_with_at_least(cursor)
                    print(
                        f"top-up: {inserted} new cases for {len(subjects)} subjects; "
                        f"themes with {top_up.THRESHOLD}+ judged cases "
                        f"{before} -> {after} (+{after - before})"
                    )
            connection.commit()
        finally:
            connection.close()
    except (config.ConfigurationError, MissingSchemaError, integrity.IntegrityError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"load file: {output_path}")
    print(f"manifest: {manifest_path(output_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
