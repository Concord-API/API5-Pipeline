import os

import psycopg2
import pytest

from pipeline import integrity
from pipeline.doctrine_link import METHOD
from pipeline.embedding import MODEL
from pipeline.raw_schema import ensure as ensure_raw
from pipeline.run import run
from pipeline.theme_registry import ensure as ensure_theme_registry
from pipeline.tpu import load as load_tpu

FIXTURE_TPU = os.path.join(os.path.dirname(__file__), "fixtures", "tpu_sample.json")

CASE = """
{"numeroProcesso": "00000010020248260100", "grau": "G1",
 "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
 "orgaoJulgador": {"codigo": 123, "nome": "1ª Vara Cível"},
 "dataAjuizamento": "2024-01-15T10:00:00Z", "nivelSigilo": 0,
 "assuntos": [{"codigo": 1127, "nome": "Contratos"}],
 "movimentos": [{"codigo": 219, "nome": "Procedência", "dataHora": "2024-06-01T12:00:00Z"}]}
"""


@pytest.fixture(scope="module")
def tpu():
    return load_tpu(FIXTURE_TPU)


@pytest.fixture(scope="module")
def loaded(postgres_container, dw_ready, tpu, tmp_path_factory):
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
            "dw.strength_config, dw.search_synonym, dw.theme_narrative RESTART IDENTITY CASCADE"
        )
        cursor.execute("TRUNCATE staging.case_event")
        ensure_theme_registry(cursor)
        cursor.execute("TRUNCATE etl.theme_registry RESTART IDENTITY CASCADE")
        ensure_raw(cursor)
        cursor.execute("TRUNCATE raw.datajud_case RESTART IDENTITY CASCADE")
        cursor.execute("TRUNCATE raw.doctrine_article RESTART IDENTITY")
        cursor.execute(
            "INSERT INTO raw.datajud_case (tribunal, source_url, payload_hash, payload) "
            "VALUES ('tjsp', 'https://x', 'h1', %s)",
            (CASE,),
        )
        output_path = tmp_path_factory.mktemp("load") / "load.sql"
        run(
            cursor, local_dsn, tpu, groups=[], output_path=output_path,
            runner=container_runner, encoder=lambda texts: [[1.0] for _ in texts],
        )
        connection.commit()
    return dw_ready


@pytest.fixture
def cursor(loaded):
    connection = psycopg2.connect(loaded)
    cur = connection.cursor()
    yield cur
    connection.rollback()
    connection.close()


def test_a_clean_load_has_no_violation(cursor, tpu):
    assert integrity.violations(cursor, tpu) == []


def test_a_fact_without_date(cursor, tpu):
    cursor.execute("UPDATE dw.fact_case_event SET date_sk = NULL")

    assert integrity.violations(cursor, tpu) == ["fact without date"]


def test_a_penal_subject(cursor, tpu):
    cursor.execute(
        "INSERT INTO dw.dim_subject (subject_name, subject_code) VALUES ('Furto', 3568)"
    )

    assert integrity.violations(cursor, tpu) == ["penal subject"]


def test_a_theme_without_subject(cursor, tpu):
    cursor.execute("INSERT INTO etl.theme_registry (theme_name) VALUES ('Sem assunto')")
    cursor.execute(
        "INSERT INTO dw.dim_theme (theme_name, theme_key) "
        "SELECT theme_name, theme_key FROM etl.theme_registry WHERE theme_name = 'Sem assunto'"
    )

    assert integrity.violations(cursor, tpu) == ["theme without subject"]


def test_a_theme_key_outside_the_registry(cursor, tpu):
    cursor.execute("UPDATE dw.dim_theme SET theme_key = theme_key + 1000")

    assert integrity.violations(cursor, tpu) == ["theme key outside the registry"]


def test_a_decision_movement_not_verified(cursor, tpu):
    cursor.execute(
        "INSERT INTO dw.dim_movement (movement_code, movement_name, outcome_sk, code_verified) "
        "SELECT 999, 'Procedência sem conferência', outcome_sk, false "
        "FROM dw.dim_decision_outcome WHERE outcome_code = 'Granted'"
    )

    assert integrity.violations(cursor, tpu) == ["decision movement not verified"]


def test_a_theme_summary_diverging_from_the_facts(cursor, tpu):
    cursor.execute(
        "UPDATE dw.dim_movement SET outcome_sk = "
        "(SELECT outcome_sk FROM dw.dim_decision_outcome WHERE outcome_code = 'Neutral'), "
        "code_verified = false, polarity_reference = NULL WHERE movement_code = 219"
    )

    assert integrity.violations(cursor, tpu) == ["theme summary diverging from the facts"]


def test_provenance_diverging_from_the_facts(cursor, tpu):
    cursor.execute("UPDATE dw.fact_case_event SET source = 'outra'")

    assert integrity.violations(cursor, tpu) == ["provenance diverging from the facts"]


def test_a_judged_theme_without_text(cursor, tpu):
    cursor.execute("DELETE FROM dw.theme_narrative")

    assert integrity.violations(cursor, tpu) == ["judged theme without text"]


def link_doctrine(cursor, **overrides):
    link = {"link_method": METHOD, "similarity": 0.8, "embedding_model": MODEL}
    link.update(overrides)
    cursor.execute(
        "INSERT INTO dw.dim_doctrine (title, article_url, source, extracted_at) "
        "VALUES ('Contratos em espécie', 'https://doutrina/1', 'doaj', now()) "
        "RETURNING doctrine_sk"
    )
    doctrine_sk = cursor.fetchone()[0]
    cursor.execute(
        "INSERT INTO dw.bridge_subject_doctrine "
        "(subject_sk, doctrine_sk, link_method, similarity, embedding_model) "
        "SELECT subject_sk, %s, %s, %s, %s FROM dw.dim_subject LIMIT 1",
        (doctrine_sk, link["link_method"], link["similarity"], link["embedding_model"]),
    )
    cursor.execute("REFRESH MATERIALIZED VIEW dw.data_provenance")


def test_a_complete_doctrine_link_is_clean(cursor, tpu):
    link_doctrine(cursor)

    assert integrity.violations(cursor, tpu) == []


@pytest.mark.parametrize("overrides", [
    {"similarity": None},
    {"similarity": 0.54},
    {"link_method": ""},
    {"embedding_model": None},
])
def test_a_doctrine_link_without_score_or_method(cursor, tpu, overrides):
    link_doctrine(cursor, **overrides)

    assert integrity.violations(cursor, tpu) == ["doctrine link without score or method"]


def test_assert_clean_names_every_failed_check(cursor, tpu):
    cursor.execute("UPDATE dw.fact_case_event SET date_sk = NULL")
    cursor.execute("DELETE FROM dw.theme_narrative")

    with pytest.raises(integrity.IntegrityError, match="fact without date, judged theme"):
        integrity.assert_clean(cursor, tpu)
