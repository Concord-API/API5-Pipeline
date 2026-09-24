import psycopg2

from pipeline.dump import dump_schema, schema_ddl

MIGRATED_RELATIONS = {
    "dim_court", "dim_judging_body", "dim_case_class", "dim_case", "dim_date",
    "dim_decision_outcome", "dim_movement", "dim_subject", "dim_theme", "dim_doctrine",
    "fact_case_event", "bridge_case_subject", "bridge_theme_subject", "bridge_subject_doctrine",
    "strength_config", "search_synonym", "theme_narrative",
    "case_current_result", "theme_summary", "theme_strength", "data_provenance",
    "theme_provenance",
}

MIGRATED_FUNCTIONS = {"norm_pt", "expand_query", "search_themes", "top_themes"}


def test_the_test_schema_has_every_object_the_migrations_create(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("SELECT relname FROM pg_class WHERE relnamespace = 'dw'::regnamespace")
        relations = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT proname FROM pg_proc WHERE pronamespace = 'dw'::regnamespace")
        functions = {row[0] for row in cur.fetchall()}

    assert MIGRATED_RELATIONS <= relations
    assert MIGRATED_FUNCTIONS <= functions


def test_the_test_schema_searches_with_the_portuguese_configuration(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("SELECT dw.norm_pt('Inscrição Indevida')")
        assert cur.fetchone()[0] == "inscricao indevida"


def test_schema_ddl_drops_psql_meta_commands_and_the_empty_search_path():
    dump = "\n".join([
        "\\restrict abc",
        "SET statement_timeout = 0;",
        "SELECT pg_catalog.set_config('search_path', '', false);",
        "CREATE SCHEMA dw;",
        "\\unrestrict abc",
    ])

    assert schema_ddl(dump) == "SET statement_timeout = 0;\nCREATE SCHEMA dw;\n"


def test_dump_schema_calls_the_runner_with_the_expected_arguments():
    calls = []

    def fake_runner(argv):
        calls.append(argv)
        return "\\restrict x\nCREATE SCHEMA dw;\n"

    result = dump_schema("postgresql://x", schema="dw", runner=fake_runner)

    assert result == "CREATE SCHEMA dw;\n"
    assert calls == [[
        "pg_dump", "--schema-only", "--schema", "dw",
        "--no-owner", "--no-privileges", "postgresql://x",
    ]]
