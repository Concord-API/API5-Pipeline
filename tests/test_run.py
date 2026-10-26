import json
import os
from datetime import date, datetime, timezone

import psycopg2
import pytest

from pipeline import integrity
from pipeline.doctrine_link import METHOD
from pipeline.embedding import MODEL
from pipeline.raw_schema import ensure as ensure_raw
from pipeline.run import run
from pipeline.search_synonym import load as load_search_synonyms
from pipeline.theme_registry import ensure as ensure_theme_registry
from pipeline.top_up import themes_with_at_least, thin_subject_codes
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


def insert_raw_doctrine(cursor):
    payload = {
        "title": "Contratos e boa-fé objetiva", "identifiers": ["https://emerj/artigo/1"],
        "dates": ["2021-05-01"], "creators": ["Autora, Ana"], "source": "Revista da EMERJ",
    }
    cursor.execute(
        "INSERT INTO raw.doctrine_article "
        "(source, source_url, collected_at, payload_hash, payload) "
        "VALUES ('oai_emerj', 'https://emerj/artigo/1', %s, 'd1', %s)",
        (datetime.now(timezone.utc), json.dumps(payload)),
    )


def insert_raw_stj_case(cursor):
    payload = {
        "numeroProcesso": "00000020020245000000",
        "grau": "SUP",
        "classe": {"codigo": 1032, "nome": "Recurso Especial"},
        "orgaoJulgador": {"codigo": 900, "nome": "Terceira Turma"},
        "dataAjuizamento": "2024-01-15T10:00:00Z",
        "nivelSigilo": 0,
        "assuntos": [{"codigo": 1127, "nome": "Contratos"}],
        "movimentos": [{"codigo": 237, "nome": "Provimento", "dataHora": "2024-08-01T12:00:00Z"}],
    }
    cursor.execute(
        "INSERT INTO raw.datajud_case (tribunal, source_url, collected_at, payload_hash, payload) "
        "VALUES ('stj', 'https://x', %s, 'h-stj', %s)",
        (datetime.now(timezone.utc), json.dumps(payload)),
    )


def insert_stj_appeal_of_the_tjsp_case(cursor):
    cursor.execute(
        "INSERT INTO dw.dim_court (court_code, court_name, state_uf) "
        "VALUES ('STJ', 'Superior Tribunal de Justiça', 'DF') ON CONFLICT (court_code) DO NOTHING"
    )
    payload = {
        "numeroProcesso": "00000010020248260100",
        "grau": "SUP",
        "classe": {"codigo": 1032, "nome": "Recurso Especial"},
        "orgaoJulgador": {"codigo": 900, "nome": "Terceira Turma"},
        "dataAjuizamento": "2024-01-15T10:00:00Z",
        "nivelSigilo": 0,
        "assuntos": [{"codigo": 1127, "nome": "Contratos"}],
        "movimentos": [
            {"codigo": 239, "nome": "Não-Provimento", "dataHora": "2025-03-01T12:00:00Z"}
        ],
    }
    cursor.execute(
        "INSERT INTO raw.datajud_case (tribunal, source_url, collected_at, payload_hash, payload) "
        "VALUES ('stj', 'https://x', %s, 'h-stj-appeal', %s)",
        (datetime(2026, 1, 1, tzinfo=timezone.utc), json.dumps(payload)),
    )


def insert_raw_stj_vice_presidency_case(cursor):
    payload = {
        "numeroProcesso": "00000030020245000000",
        "grau": "SUP",
        "classe": {"codigo": 11881, "nome": "Agravo em Recurso Especial"},
        "orgaoJulgador": {"codigo": 901, "nome": "VICE-PRESIDÊNCIA"},
        "dataAjuizamento": "2024-01-15T10:00:00Z",
        "nivelSigilo": 0,
        "assuntos": [{"codigo": 1127, "nome": "Contratos"}],
        "movimentos": [
            {"codigo": 239, "nome": "Não-Provimento", "dataHora": "2025-04-01T12:00:00Z"}
        ],
    }
    cursor.execute(
        "INSERT INTO raw.datajud_case (tribunal, source_url, collected_at, payload_hash, payload) "
        "VALUES ('stj', 'https://x', %s, 'h-stj-vp', %s)",
        (datetime.now(timezone.utc), json.dumps(payload)),
    )


def same_vector_encoder(texts):
    return [[1.0, 0.0] for _ in texts]


def run_once(postgres_container, dw_ready, tmp_path, extra_raw=(), extra_precedents=()):
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
            "dw.dim_case_class, dw.dim_court, dw.dim_decision_outcome, dw.dim_date, "
            "dw.dim_doctrine "
            "RESTART IDENTITY CASCADE"
        )
        cursor.execute("TRUNCATE staging.case_event")
        cursor.execute("TRUNCATE dw.strength_config")
        cursor.execute("TRUNCATE dw.search_synonym")
        ensure_theme_registry(cursor)
        cursor.execute("TRUNCATE etl.theme_registry RESTART IDENTITY CASCADE")
        ensure_raw(cursor)
        cursor.execute("TRUNCATE raw.datajud_case RESTART IDENTITY CASCADE")
        insert_raw_case(cursor)
        for insert in extra_raw:
            insert(cursor)
        cursor.execute("TRUNCATE raw.doctrine_article RESTART IDENTITY")
        insert_raw_doctrine(cursor)
        cursor.execute("TRUNCATE raw.stj_precedent")
        for insert in extra_precedents:
            insert(cursor)

        output_path = tmp_path / "load.sql"
        run(
            cursor, local_dsn, tpu, groups=[], output_path=output_path,
            runner=container_runner, encoder=same_vector_encoder,
        )
        connection.commit()

    return output_path.read_text(encoding="utf-8")


def test_run_writes_the_manifest_beside_the_load_file(postgres_container, dw_ready, tmp_path):
    run_once(postgres_container, dw_ready, tmp_path)

    manifest = json.loads((tmp_path / "load.manifest.json").read_text(encoding="utf-8"))
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT max(extracted_at) FROM dw.fact_case_event")
        extracted_at = cursor.fetchone()[0]

    assert manifest["schema_version"] == "V016__add_strength_settings.sql"
    assert manifest["extracted_at"] == extracted_at.isoformat()
    assert manifest["tables"]["fact_case_event"] == 1
    assert manifest["tables"]["dim_theme"] == 1
    assert manifest["cases_decided_in_more_than_one_court"] == 0
    assert manifest["unmapped_stj_judging_bodies"] == 0
    assert "case_current_result" not in manifest["tables"]


def test_run_loads_a_stj_case_at_the_superior_level(postgres_container, dw_ready, tmp_path):
    content = run_once(postgres_container, dw_ready, tmp_path, extra_raw=[insert_raw_stj_case])

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT dc.case_number, c.court_code, dc.court_level FROM dw.dim_case dc "
            "JOIN dw.dim_court c ON c.court_sk = dc.court_sk ORDER BY dc.case_number"
        )
        assert cursor.fetchall() == [
            ("00000010020248260100", "TJSP", "First"),
            ("00000020020245000000", "STJ", "Superior"),
        ]
    assert "00000020020245000000" in content


def test_run_measures_the_cases_decided_in_more_than_one_court(
    postgres_container, dw_ready, tmp_path
):
    run_once(postgres_container, dw_ready, tmp_path, extra_raw=[insert_stj_appeal_of_the_tjsp_case])

    manifest = json.loads((tmp_path / "load.manifest.json").read_text(encoding="utf-8"))
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.court_code FROM dw.case_current_result r "
            "JOIN dw.dim_court c ON c.court_sk = r.court_sk"
        )
        assert cursor.fetchall() == [("STJ",)]
    assert manifest["cases_decided_in_more_than_one_court"] == 1


def test_run_counts_the_stj_decisions_outside_a_panel(postgres_container, dw_ready, tmp_path):
    run_once(
        postgres_container, dw_ready, tmp_path,
        extra_raw=[insert_raw_stj_case, insert_raw_stj_vice_presidency_case],
    )

    manifest = json.loads((tmp_path / "load.manifest.json").read_text(encoding="utf-8"))
    assert manifest["unmapped_stj_judging_bodies"] == 1


def test_lists_the_subjects_of_the_themes_below_five_judged_cases(
    postgres_container, dw_ready, tmp_path
):
    run_once(postgres_container, dw_ready, tmp_path)

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        assert thin_subject_codes(cursor) == [1127]
        assert themes_with_at_least(cursor, 1) == 1
        assert themes_with_at_least(cursor, 5) == 0


def test_run_produces_a_complete_load_file(postgres_container, dw_ready, tmp_path):
    content = run_once(postgres_container, dw_ready, tmp_path)

    assert content.startswith("BEGIN;")
    assert content.rstrip().endswith("COMMIT;")
    assert "COPY dw.dim_case" in content
    assert "COPY dw.dim_theme" in content
    assert "0000001-00.2024.8.26.0100" in content
    assert "COPY dw.strength_config" in content
    assert "COPY dw.search_synonym" in content
    assert "COPY dw.theme_narrative" in content
    assert "COPY dw.dim_date" in content
    assert "negativado\tinclusao indevida cadastro inadimplentes" in content
    assert "Contratos e boa-fé objetiva\tAutora, Ana" in content
    assert f"\t{METHOD}\t" in content

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW dw.case_current_result")
        cursor.execute("SELECT count(*) FROM dw.case_current_result")
        assert cursor.fetchone() == (1,)
        cursor.execute("SELECT theme_name FROM dw.dim_theme")
        assert cursor.fetchall() == [("Contratos",)]
        cursor.execute("SELECT count(*) FROM dw.fact_case_event")
        assert cursor.fetchone() == (1,)
        cursor.execute("SELECT methodology_version, reference_year FROM dw.strength_config")
        assert cursor.fetchall() == [("1.0", datetime.now(timezone.utc).year)]
        cursor.execute("SELECT text_origin, jsonb_array_length(lead) FROM dw.theme_narrative")
        assert cursor.fetchall() == [("template", 3)]
        cursor.execute("SELECT source, article_url FROM dw.dim_doctrine")
        assert cursor.fetchall() == [("oai_emerj", "https://emerj/artigo/1")]
        cursor.execute(
            "SELECT s.subject_name, b.link_method, b.embedding_model "
            "FROM dw.bridge_subject_doctrine b JOIN dw.dim_subject s USING (subject_sk)"
        )
        assert cursor.fetchall() == [("Contratos", METHOD, MODEL)]
        cursor.execute("SELECT count(*) FROM dw.search_synonym")
        assert cursor.fetchone() == (len(load_search_synonyms()),)


def test_run_dates_every_fact_and_the_theme_period(postgres_container, dw_ready, tmp_path):
    run_once(postgres_container, dw_ready, tmp_path)

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM dw.fact_case_event WHERE date_sk IS NULL")
        assert cursor.fetchone() == (0,)
        cursor.execute("SELECT min(full_date), max(full_date) FROM dw.dim_date")
        first, last = cursor.fetchone()
        assert first == date(1940, 1, 1)
        assert last == date(datetime.now(timezone.utc).year + 1, 12, 31)
        cursor.execute("SELECT period_start_year, last_decision_date FROM dw.theme_summary")
        assert cursor.fetchall() == [(2024, date(2024, 6, 1))]


def test_run_does_not_write_the_load_file_when_the_integrity_fails(
    postgres_container, dw_ready, tmp_path, monkeypatch
):
    monkeypatch.setattr(integrity, "violations", lambda cursor, tpu: ["fact without date"])

    with pytest.raises(integrity.IntegrityError, match="fact without date"):
        run_once(postgres_container, dw_ready, tmp_path)

    assert not (tmp_path / "load.sql").exists()


def insert_raw_precedent(cursor):
    payload = {
        "tipoPrecedente": "Tema",
        "numeroPrecedente": "952",
        "teseFirmada": "O reajuste previsto em contrato é válido.",
        "questaoSubmetidaAJulgamento": "Validade do reajuste.",
        "situacao": "Trânsito em Julgado",
        "dataJulgamento": "2016-12-14",
        "orgaoJulgador": "S2",
        "Assuntos": "1127- Contratos",
    }
    cursor.execute(
        "INSERT INTO raw.stj_precedent (kind, number, source_url, payload) VALUES (%s, %s, %s, %s)",
        ("Tema", 952, "https://dadosabertos.web.stj.jus.br/temas.csv", json.dumps(payload)),
    )


def test_run_links_the_stj_theses_to_the_theme_subjects(postgres_container, dw_ready, tmp_path):
    content = run_once(
        postgres_container, dw_ready, tmp_path, extra_precedents=[insert_raw_precedent]
    )

    assert "COPY dw.dim_precedent" in content
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT p.precedent_number, s.subject_name FROM dw.bridge_subject_precedent b "
            "JOIN dw.dim_precedent p USING (precedent_sk) JOIN dw.dim_subject s USING (subject_sk)"
        )
        assert cursor.fetchall() == [(952, "Contratos")]
