import psycopg2
import pytest

from pipeline.load_file import build, matview_names, refresh_order, schema_version, table_names

VERSION = "V016__add_strength_settings.sql"


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS dw.z_source CASCADE")
        cur.execute("CREATE MATERIALIZED VIEW dw.z_source AS SELECT 1 AS n WITH NO DATA")
        cur.execute(
            "CREATE MATERIALIZED VIEW dw.a_dependent AS SELECT n FROM dw.z_source WITH NO DATA"
        )
        yield cur
        connection.rollback()
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS dw.z_source CASCADE")
        connection.commit()


def test_table_names_lists_the_dw_tables(cursor):
    tables = table_names(cursor)

    assert "dim_court" in tables
    assert "fact_case_event" in tables
    assert "a_dependent" not in tables


def test_matview_names_lists_only_materialized_views(cursor):
    matviews = matview_names(cursor)

    assert "a_dependent" in matviews
    assert "dim_court" not in matviews


def test_build_puts_begin_first_and_commit_last():
    script = build(["dim_court"], [], "-- dump", VERSION)

    lines = [line for line in script.splitlines() if line.strip()]
    assert lines[0] == "BEGIN;"
    assert lines[-1] == "COMMIT;"


def test_build_truncates_all_tables_before_the_dump():
    script = build(["dim_court", "dim_case"], [], "-- dump", VERSION)

    truncate_index = script.index("TRUNCATE")
    dump_index = script.index("-- dump")
    assert "dw.dim_court" in script
    assert "dw.dim_case" in script
    assert "RESTART IDENTITY CASCADE" in script
    assert truncate_index < dump_index


def test_build_refreshes_each_matview_after_the_dump():
    script = build(["dim_court"], ["case_current_result", "theme_summary"], "-- dump", VERSION)

    dump_index = script.index("-- dump")
    assert script.index("REFRESH MATERIALIZED VIEW dw.case_current_result") > dump_index
    assert script.index("REFRESH MATERIALIZED VIEW dw.theme_summary") > dump_index


def test_build_without_matviews_has_no_refresh():
    script = build(["dim_court"], [], "-- dump", VERSION)

    assert "REFRESH" not in script


def test_refresh_order_puts_each_view_after_the_view_it_reads():
    order = refresh_order(["a", "b", "c"], [("a", "b"), ("b", "c")])

    assert order == ["c", "b", "a"]


def test_refresh_order_keeps_independent_views_alphabetical():
    order = refresh_order(["theme_summary", "case_current_result"], [])

    assert order == ["case_current_result", "theme_summary"]


def test_refresh_order_handles_a_view_read_by_two_others():
    order = refresh_order(["a", "b", "c", "d"], [("b", "a"), ("c", "a"), ("d", "b"), ("d", "c")])

    assert order == ["a", "b", "c", "d"]


def test_matview_names_lists_a_view_after_the_view_it_reads(cursor):
    matviews = matview_names(cursor)

    assert matviews.index("z_source") < matviews.index("a_dependent")


def test_refreshing_in_the_listed_order_populates_dependent_views(cursor):
    for view in matview_names(cursor):
        cursor.execute(f"REFRESH MATERIALIZED VIEW dw.{view}")

    cursor.execute("SELECT n FROM dw.a_dependent")
    assert cursor.fetchall() == [(1,)]


def test_build_checks_the_schema_version_before_truncating():
    script = build(["dim_court"], [], "-- dump", VERSION)

    assert script.index("BEGIN;") < script.index(VERSION) < script.index("TRUNCATE")


def test_schema_version_is_the_file_name_of_the_last_migration_applied(cursor):
    cursor.execute(
        "INSERT INTO migrations.schema_versions (scriptname, applied) "
        "VALUES ('Ratio.Infrastructure.Migrations.Scripts.V099__later.sql', now())"
    )

    assert schema_version(cursor) == "V099__later.sql"


def test_load_with_the_same_schema_version_runs(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("CREATE TABLE dw.z_guard (n integer)")
        connection.commit()
        try:
            cur.execute(build(["z_guard"], [], "", schema_version(cur)))
        finally:
            connection.rollback()
            cur.execute("DROP TABLE dw.z_guard")
            connection.commit()


def test_load_with_another_schema_version_fails_before_deleting_anything(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_court RESTART IDENTITY CASCADE")
        cur.execute(
            "INSERT INTO dw.dim_court (court_code, court_name, state_uf) "
            "VALUES ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP')"
        )
        connection.commit()

        with pytest.raises(psycopg2.Error) as error:
            cur.execute(build(table_names(cur), [], "", "V999__other.sql"))
        connection.rollback()

        cur.execute("SELECT court_code FROM dw.dim_court")
        assert cur.fetchall() == [("TJSP",)]
    assert "V999__other.sql" in str(error.value)
    assert VERSION in str(error.value)


def test_load_on_a_database_the_api_never_migrated_fails_with_a_clear_message(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("ALTER TABLE migrations.schema_versions RENAME TO schema_versions_hidden")
        with pytest.raises(psycopg2.Error) as error:
            cur.execute(build(["dim_court"], [], "", VERSION))
        connection.rollback()

    assert "não foi migrado pela API" in str(error.value)
