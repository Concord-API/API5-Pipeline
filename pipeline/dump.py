import subprocess


def _subprocess_runner(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout


def dump_data(dsn, schema="dw", runner=_subprocess_runner):
    argv = [
        "pg_dump", "--data-only", "--schema", schema,
        "--no-owner", "--no-privileges", dsn,
    ]
    return runner(argv)


def schema_ddl(dump):
    kept = [
        line for line in dump.splitlines()
        if not line.startswith("\\")
        and not line.startswith("SELECT pg_catalog.set_config('search_path'")
    ]
    return "\n".join(kept).strip() + "\n"


def dump_schema(dsn, schema="dw", runner=_subprocess_runner):
    argv = [
        "pg_dump", "--schema-only", "--schema", schema,
        "--no-owner", "--no-privileges", dsn,
    ]
    return schema_ddl(runner(argv))
