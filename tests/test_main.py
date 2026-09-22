import psycopg2
import pytest

from pipeline.__main__ import main
from pipeline.raw_schema import ensure as ensure_raw
from pipeline.theme_registry import ensure as ensure_theme_registry

CASE = {
    "numeroProcesso": "00000010020248260100",
    "grau": "G1",
    "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
    "orgaoJulgador": {"codigo": 123, "nome": "1ª Vara Cível"},
    "dataAjuizamento": "2024-01-15T10:00:00Z",
    "nivelSigilo": 0,
    "assuntos": [{"codigo": 4654, "nome": "Assunto de teste"}],
    "movimentos": [{"codigo": 219, "nome": "Procedência", "dataHora": "2024-06-01T12:00:00Z"}],
}


class FakeResponse:
    status_code = 200

    def __init__(self, hits):
        self._hits = hits

    def raise_for_status(self):
        pass

    def json(self):
        return {"hits": {"hits": self._hits}}


class FakeSession:
    def __init__(self):
        self.requests = 0

    def post(self, url, json, timeout):
        self.requests += 1
        if self.requests == 1:
            return FakeResponse([{"_id": "case-1", "_source": CASE, "sort": [1]}])
        return FakeResponse([])


class SessionFactory:
    def __init__(self):
        self.keys = []
        self.session = FakeSession()

    def __call__(self, api_key):
        self.keys.append(api_key)
        return self.session


@pytest.fixture
def clean_database(dw_ready):
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
    return dw_ready


@pytest.fixture
def container_runner(postgres_container, clean_database):
    local_dsn = (
        f"postgresql://{postgres_container.username}:{postgres_container.password}"
        f"@localhost:5432/{postgres_container.dbname}"
    )

    def runner(argv):
        argv = [local_dsn if arg == clean_database else arg for arg in argv]
        exit_code, output = postgres_container.exec(argv)
        if exit_code != 0:
            raise RuntimeError(output.decode())
        return output.decode()

    return runner


@pytest.fixture
def environment(monkeypatch, clean_database, tmp_path):
    output_path = tmp_path / "load.sql"
    monkeypatch.setenv("DATABASE_URL", clean_database)
    monkeypatch.setenv("DATAJUD_API_KEY", "public-key")
    monkeypatch.setenv("LOAD_FILE_PATH", str(output_path))
    return output_path


def test_harvests_and_writes_the_load_file(environment, container_runner):
    factory = SessionFactory()

    exit_code = main([], session_factory=factory, runner=container_runner)

    assert exit_code == 0
    assert factory.keys == ["public-key"]
    content = environment.read_text(encoding="utf-8")
    assert content.startswith("BEGIN;")
    assert content.rstrip().endswith("COMMIT;")
    assert "COPY dw.dim_case" in content
    assert "0000001-00.2024.8.26.0100" in content


def test_skip_harvest_builds_from_the_raw_already_collected(
    environment, container_runner, monkeypatch
):
    main([], session_factory=SessionFactory(), runner=container_runner)
    monkeypatch.delenv("DATAJUD_API_KEY")
    environment.unlink()
    factory = SessionFactory()

    exit_code = main(["--skip-harvest"], session_factory=factory, runner=container_runner)

    assert exit_code == 0
    assert factory.keys == []
    assert "0000001-00.2024.8.26.0100" in environment.read_text(encoding="utf-8")


def test_fails_clearly_without_the_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    factory = SessionFactory()

    exit_code = main([], session_factory=factory)

    assert exit_code == 1
    assert "DATABASE_URL" in capsys.readouterr().err
    assert factory.keys == []


def test_fails_clearly_without_the_datajud_key(environment, monkeypatch, capsys):
    monkeypatch.delenv("DATAJUD_API_KEY")
    factory = SessionFactory()

    exit_code = main([], session_factory=factory)

    assert exit_code == 1
    assert "DATAJUD_API_KEY" in capsys.readouterr().err
    assert factory.keys == []


def test_fails_clearly_when_the_dw_schema_does_not_exist(
    environment, postgres_url, monkeypatch, capsys
):
    connection = psycopg2.connect(postgres_url)
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("DROP DATABASE IF EXISTS without_dw")
        cursor.execute("CREATE DATABASE without_dw")
    connection.close()
    monkeypatch.setenv("DATABASE_URL", postgres_url.rsplit("/", 1)[0] + "/without_dw")
    factory = SessionFactory()

    exit_code = main([], session_factory=factory)

    assert exit_code == 1
    assert "schema dw" in capsys.readouterr().err
    assert factory.keys == []
