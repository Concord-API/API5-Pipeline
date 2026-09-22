import psycopg2
import pytest

from pipeline.load_file import build, matview_names, table_names


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS dw.a_test_view")
        cur.execute("CREATE MATERIALIZED VIEW dw.a_test_view AS SELECT 1 AS n")
        yield cur
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS dw.a_test_view")
        connection.commit()


def test_table_names_lists_the_dw_tables(cursor):
    tables = table_names(cursor)

    assert "dim_court" in tables
    assert "fact_case_event" in tables
    assert "a_test_view" not in tables


def test_matview_names_lists_only_materialized_views(cursor):
    matviews = matview_names(cursor)

    assert matviews == ["a_test_view"]


def test_build_puts_begin_first_and_commit_last():
    script = build(["dim_court"], [], "-- dump")

    lines = [line for line in script.splitlines() if line.strip()]
    assert lines[0] == "BEGIN;"
    assert lines[-1] == "COMMIT;"


def test_build_truncates_all_tables_before_the_dump():
    script = build(["dim_court", "dim_case"], [], "-- dump")

    truncate_index = script.index("TRUNCATE")
    dump_index = script.index("-- dump")
    assert "dw.dim_court" in script
    assert "dw.dim_case" in script
    assert "RESTART IDENTITY CASCADE" in script
    assert truncate_index < dump_index


def test_build_refreshes_each_matview_after_the_dump():
    script = build(["dim_court"], ["case_current_result", "theme_summary"], "-- dump")

    dump_index = script.index("-- dump")
    assert script.index("REFRESH MATERIALIZED VIEW dw.case_current_result") > dump_index
    assert script.index("REFRESH MATERIALIZED VIEW dw.theme_summary") > dump_index


def test_build_without_matviews_has_no_refresh():
    script = build(["dim_court"], [], "-- dump")

    assert "REFRESH" not in script
