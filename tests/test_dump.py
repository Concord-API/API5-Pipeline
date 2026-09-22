import psycopg2

from pipeline.dump import dump_data


def test_dump_data_calls_the_runner_with_the_expected_arguments():
    calls = []

    def fake_runner(argv):
        calls.append(argv)
        return "-- fake dump"

    result = dump_data("postgresql://x", schema="dw", runner=fake_runner)

    assert result == "-- fake dump"
    assert calls == [[
        "pg_dump", "--data-only", "--schema", "dw",
        "--no-owner", "--no-privileges", "postgresql://x",
    ]]


def test_dump_data_produces_real_copy_statements(postgres_container, dw_ready):
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

    result = dump_data(local_dsn, schema="dw", runner=container_runner)

    assert "COPY dw.dim_court" in result
    assert "TJSP" in result
