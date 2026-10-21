import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

from pipeline import config, theme_build, tpu
from pipeline.raw_schema import ensure as ensure_raw
from pipeline.run import run

SAMPLE_PATH = Path(__file__).resolve().parent / "data" / "raw_sample.json"
COLLECTED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class SampleError(Exception):
    pass


def load_raw_sample(cursor, path=SAMPLE_PATH):
    ensure_raw(cursor)
    cursor.execute("SELECT count(*) FROM raw.datajud_case")
    if cursor.fetchone()[0]:
        raise SampleError("a amostra só é gerada num banco vazio: este já tem coleta")
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    for index, case in enumerate(cases, start=1):
        number = case["payload"]["numeroProcesso"]
        cursor.execute(
            "INSERT INTO raw.datajud_case "
            "(tribunal, source_url, collected_at, payload_hash, payload) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                case["tribunal"],
                f"https://example.org/processo/{number}",
                COLLECTED_AT,
                f"sample-{index}",
                json.dumps(case["payload"], ensure_ascii=False),
            ),
        )
    return len(cases)


def build(cursor, dsn, output_path, runner=None):
    load_raw_sample(cursor)
    return run(cursor, dsn, tpu.load(), theme_build.load_groups(), output_path, runner=runner)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    config.load_env()
    output_path = argv[0] if argv else "ratio-sample.sql"
    try:
        dsn = config.database_url()
        connection = psycopg2.connect(dsn)
        try:
            with connection.cursor() as cursor:
                build(cursor, dsn, output_path)
            connection.commit()
        finally:
            connection.close()
    except (config.ConfigurationError, SampleError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"sample: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
