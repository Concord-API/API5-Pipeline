import json

import psycopg2
import pytest

from pipeline.raw_schema import ensure as ensure_raw
from pipeline.sample import SampleError, build, main
from pipeline.theme_registry import ensure as ensure_theme_registry


@pytest.fixture
def empty_database(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE dw.fact_case_event, dw.bridge_case_subject, dw.bridge_theme_subject, "
            "dw.dim_case, dw.dim_theme, dw.dim_subject, dw.dim_movement, dw.dim_judging_body, "
            "dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome, dw.dim_date, "
            "dw.dim_doctrine RESTART IDENTITY CASCADE"
        )
        cursor.execute("TRUNCATE staging.case_event")
        cursor.execute("TRUNCATE dw.strength_config")
        cursor.execute("TRUNCATE dw.search_synonym")
        ensure_theme_registry(cursor)
        cursor.execute("TRUNCATE etl.theme_registry RESTART IDENTITY CASCADE")
        ensure_raw(cursor)
        cursor.execute("TRUNCATE raw.datajud_case RESTART IDENTITY CASCADE")
        cursor.execute("TRUNCATE raw.doctrine_article RESTART IDENTITY")
    return dw_ready


@pytest.fixture
def container_runner(postgres_container, empty_database):
    local_dsn = (
        f"postgresql://{postgres_container.username}:{postgres_container.password}"
        f"@localhost:5432/{postgres_container.dbname}"
    )

    def runner(argv):
        argv = [local_dsn if arg == empty_database else arg for arg in argv]
        exit_code, output = postgres_container.exec(argv)
        if exit_code != 0:
            raise RuntimeError(output.decode())
        return output.decode()

    return runner


def test_build_runs_the_pipeline_on_the_fixed_sample(empty_database, container_runner, tmp_path):
    output_path = tmp_path / "ratio-sample.sql"

    with psycopg2.connect(empty_database) as connection, connection.cursor() as cursor:
        build(cursor, empty_database, output_path, runner=container_runner)

    content = output_path.read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "ratio-sample.manifest.json").read_text(encoding="utf-8"))
    assert content.startswith("BEGIN;")
    assert "00001010020248260100" in content
    assert manifest["tables"]["fact_case_event"] == 12
    assert manifest["tables"]["dim_court"] == 3
    assert manifest["tables"]["dim_theme"] == 3
    assert manifest["extracted_at"] is not None


def test_build_refuses_a_database_that_already_has_collected_cases(empty_database, tmp_path):
    with psycopg2.connect(empty_database) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO raw.datajud_case "
            "(tribunal, source_url, collected_at, payload_hash, payload) "
            "VALUES ('tjsp', 'https://x', now(), 'real-1', '{}')"
        )
        connection.commit()

        with pytest.raises(SampleError, match="banco vazio"):
            build(cursor, empty_database, tmp_path / "ratio-sample.sql")
        connection.rollback()

        cursor.execute("SELECT payload_hash FROM raw.datajud_case")
        assert cursor.fetchall() == [("real-1",)]


def test_main_builds_the_sample_from_the_settings(
    empty_database, container_runner, tmp_path, monkeypatch, capsys
):
    output_path = tmp_path / "ratio-sample.sql"
    monkeypatch.setenv("DATABASE_URL", empty_database)

    exit_code = main([str(output_path)], runner=container_runner)

    assert exit_code == 0
    assert output_path.exists()
    assert f"sample: {output_path}" in capsys.readouterr().out


def test_main_fails_clearly_without_the_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    exit_code = main(["ratio-sample.sql"])

    assert exit_code == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_main_refuses_a_database_with_collected_cases(empty_database, monkeypatch, capsys):
    with psycopg2.connect(empty_database) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO raw.datajud_case "
            "(tribunal, source_url, collected_at, payload_hash, payload) "
            "VALUES ('tjsp', 'https://x', now(), 'real-1', '{}')"
        )
    monkeypatch.setenv("DATABASE_URL", empty_database)

    exit_code = main(["ratio-sample.sql"])

    assert exit_code == 1
    assert "banco vazio" in capsys.readouterr().err
