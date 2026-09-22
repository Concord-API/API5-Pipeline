import subprocess


def _subprocess_runner(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout


def dump_data(dsn, schema="dw", runner=_subprocess_runner):
    argv = [
        "pg_dump", "--data-only", "--schema", schema,
        "--no-owner", "--no-privileges", dsn,
    ]
    return runner(argv)
