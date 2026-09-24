import sys
from pathlib import Path

from pipeline.dump import dump_schema

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "dw_schema.sql"


def main(argv):
    if len(argv) != 1:
        print("usage: python scripts/refresh_test_schema.py <dsn migrated by the API>")
        return 1
    FIXTURE.write_text(dump_schema(argv[0]), encoding="utf-8", newline="\n")
    print(f"test schema: {FIXTURE}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
