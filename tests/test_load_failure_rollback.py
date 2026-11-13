import psycopg2

from pipeline.load_file import build


def execute_failed_load(dsn, load_sql):
    try:
        with psycopg2.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(load_sql)
    except psycopg2.Error:
        return
    raise AssertionError("The load was expected to fail")


def test_failed_load_after_truncate_preserves_previous_data(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO dw.dim_court (court_code, court_name, state_uf) "
            "VALUES ('DVP62', 'DVP-62 previous court', 'SP')"
        )
        cursor.execute(
            "SELECT court_code, court_name, state_uf FROM dw.dim_court ORDER BY court_code"
        )
        previous_data = cursor.fetchall()

    load_sql = build(
        ["dim_court"],
        [],
        "INSERT INTO dw.dim_court (court_code, court_name, state_uf) "
        "VALUES ('DVP62-new', NULL, 'RJ');",
        "V016__add_strength_settings.sql",
    )

    execute_failed_load(dw_ready, load_sql)

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT court_code, court_name, state_uf FROM dw.dim_court ORDER BY court_code"
        )
        assert cursor.fetchall() == previous_data
