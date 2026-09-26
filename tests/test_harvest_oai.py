import runpy
import sys
from pathlib import Path

import psycopg2
import pytest

from pipeline import harvest_oai
from pipeline.harvest_oai import main
from pipeline.oai import OAIError
from pipeline.raw_schema import ensure


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.closed = False

    def close(self):
        self.closed = True


def test_runs_selected_repository_and_reports_progress(postgres_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    session = FakeSession()

    def collect(session_arg, cursor, repositories, on_repository):
        assert session_arg is session
        assert repositories == ["emerj"]
        cursor.execute("TRUNCATE raw.doctrine_article")
        on_repository("emerj", 1, 1)
        return 1

    assert main(["--repository", "emerj"], session_factory=lambda: session,
                collect_fn=collect) == 0
    assert session.closed
    assert "emerj: 1 articles, 1 new or updated" in capsys.readouterr().out


def test_rolls_back_failed_repository(postgres_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        cursor.execute("TRUNCATE raw.doctrine_article")

    def collect(session_arg, cursor, repositories, on_repository):
        cursor.execute(
            "INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload) "
            "VALUES ('oai_emerj', 'https://example.org', 'x', '{}')"
        )
        raise OAIError("badResumptionToken")

    assert main([], session_factory=FakeSession, collect_fn=collect) == 1
    assert "badResumptionToken" in capsys.readouterr().err
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.doctrine_article")
        assert cursor.fetchone()[0] == 0


def test_module_entrypoint_reports_configuration_error(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["python -m pipeline.harvest_oai"])

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(harvest_oai.__file__)), run_name="__main__")

    assert error.value.code == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_reports_a_disabled_repository(postgres_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)

    def collect(session_arg, cursor, repositories, on_repository):
        on_repository("revistaFADI", 0, 0, "OAI endpoint requires access")
        return 0

    assert main([], session_factory=FakeSession, collect_fn=collect) == 0
    assert "revistaFADI: skipped (OAI endpoint requires access)" in capsys.readouterr().out
