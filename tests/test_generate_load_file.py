import psycopg2

from pipeline.load_file import generate


def test_generate_writes_a_complete_load_file(postgres_container, dw_ready, tmp_path):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_court RESTART IDENTITY CASCADE")
        cur.execute(
            "INSERT INTO dw.dim_court (court_code, court_name, state_uf) "
            "VALUES ('TJSP', 'Tribunal de Justiça de São Paulo', 'SP')"
        )
        connection.commit()

    local_dsn = (
        f"postgresql://{postgres_container.username}:{postgres_container.password}"
        f"@localhost:5432/{postgres_container.dbname}"
    )

    def container_runner(argv):
        exit_code, output = postgres_container.exec(argv)
        if exit_code != 0:
            raise RuntimeError(output.decode())
        return output.decode()

    output_path = tmp_path / "load.sql"
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cursor:
        generate(cursor, local_dsn, output_path, runner=container_runner)

    content = output_path.read_text(encoding="utf-8")
    assert content.startswith("BEGIN;")
    assert content.rstrip().endswith("COMMIT;")
    assert "TRUNCATE dw." in content
    assert "COPY dw.dim_court" in content
    assert "TJSP" in content
    assert content.index("TRUNCATE dw.") < content.index("COPY dw.dim_court")
