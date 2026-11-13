import difflib
import sys
from pathlib import Path

from pipeline.dump import dump_schema

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "dw_schema.sql"


def normalize_schema(schema):
    return "\n".join(line.rstrip() for line in schema.splitlines()) + "\n"


def schema_diff(expected, actual):
    expected_lines = schema_signature(expected)
    actual_lines = schema_signature(actual)
    return "".join(
        difflib.unified_diff(
            [f"{line}\n" for line in expected_lines],
            [f"{line}\n" for line in actual_lines],
            fromfile="tests/fixtures/dw_schema.sql",
            tofile="generated dw schema",
        )
    )


def schema_signature(schema):
    lines = normalize_schema(schema).splitlines()
    return sorted(
        line.strip()
        for line in lines
        if (
            (line.startswith(("CREATE ", "ALTER TABLE ONLY"))
             or line.strip().startswith("ADD CONSTRAINT"))
            and "pg_attver" not in line
        )
    )


def main(argv):
    if len(argv) != 1:
        print("usage: python scripts/check_schema_drift.py <dsn migrated by the API>")
        return 1

    difference = schema_diff(FIXTURE.read_text(encoding="utf-8"), dump_schema(argv[0]))
    if difference:
        print(difference, end="")
        return 1

    print("schema fixture matches the migrated database")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
