import json
import os
from datetime import datetime, timezone

import psycopg2

from pipeline.raw_schema import ensure as ensure_raw
from pipeline.run import run
from pipeline.theme_registry import ensure as ensure_theme_registry
from pipeline.tpu import load as load_tpu

FIXTURE_TPU = os.path.join(os.path.dirname(__file__), "fixtures", "tpu_sample.json")


def insert_raw_case(cursor):
    payload = {
        "numeroProcesso": "00000010020248260100",
        "grau": "G1",
        "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
        "orgaoJulgador": {"codigo": 123, "nome": "1ª Vara Cível"},
        "dataAjuizamento": "2024-01-15T10:00:00Z",
        "nivelSigilo": 0,
        "assuntos": [{"codigo": 1127, "nome": "Contratos"}],
        "movimentos": [{"codigo": 219, "nome": "Procedência", "dataHora": "2024-06-01T12:00:00Z"}],
    }
    cursor.execute(
        "INSERT INTO raw.datajud_case (tribunal, source_url, collected_at, payload_hash, payload) "
        "VALUES ('tjsp', 'https://x', %s, 'h1', %s)",
        (datetime.now(timezone.utc), json.dumps(payload)),
    )


def test_run_produces_a_complete_load_file(postgres_container, dw_ready, tmp_path):
    tpu = load_tpu(FIXTURE_TPU)
    local_dsn = (
        f"postgresql://{postgres_container.username}:{postgres_container.password}"
        f"@localhost:5432/{postgres_container.dbname}"
    )

    def container_runner(argv):
        exit_code, output = postgres_container.exec(argv)
        if exit_code != 0:
            raise RuntimeError(output.decode())
        return output.decode()

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE dw.fact_case_event, dw.bridge_case_subject, dw.bridge_theme_subject, "
            "dw.dim_case, dw.dim_theme, dw.dim_subject, dw.dim_movement, dw.dim_judging_body, "
            "dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome, dw.dim_date "
            "RESTART IDENTITY CASCADE"
        )
        cursor.execute("TRUNCATE staging.case_event")
        ensure_theme_registry(cursor)
        cursor.execute("TRUNCATE etl.theme_registry RESTART IDENTITY CASCADE")
        ensure_raw(cursor)
        cursor.execute("TRUNCATE raw.datajud_case RESTART IDENTITY CASCADE")
        insert_raw_case(cursor)

        output_path = tmp_path / "load.sql"
        run(cursor, local_dsn, tpu, groups=[], output_path=output_path, runner=container_runner)
        connection.commit()

    content = output_path.read_text(encoding="utf-8")
    assert content.startswith("BEGIN;")
    assert content.rstrip().endswith("COMMIT;")
    assert "COPY dw.dim_case" in content
    assert "COPY dw.dim_theme" in content
    assert "0000001-00.2024.8.26.0100" in content

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW dw.case_current_result")
        cursor.execute("SELECT count(*) FROM dw.case_current_result")
        assert cursor.fetchone() == (1,)
        cursor.execute("SELECT theme_name FROM dw.dim_theme")
        assert cursor.fetchall() == [("Contratos",)]
        cursor.execute("SELECT count(*) FROM dw.fact_case_event")
        assert cursor.fetchone() == (1,)
