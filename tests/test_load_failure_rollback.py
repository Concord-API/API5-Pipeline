import psycopg2

from pipeline.load_file import build


def test_failed_load_after_truncate_preserves_previous_data(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO dw.dim_court (court_code, court_name, state_uf) "
            "VALUES ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP')"
        )

    load_sql = build(
        ["dim_court"],
        [],
        "INSERT INTO dw.dim_court (court_code, court_name, state_uf) "
        "VALUES ('TJRJ', NULL, 'RJ');",
        "V016__add_strength_settings.sql",
    )

    execute_failed_load(dw_ready, load_sql)

    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT court_code, court_name, state_uf FROM dw.dim_court")
        assert cursor.fetchall() == [
            ("TJSP", "Tribunal de Justiça de São Paulo", "SP")
        ]
