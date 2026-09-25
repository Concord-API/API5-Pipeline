import psycopg2

from pipeline.doaj import DOAJError
from pipeline.harvest_doaj import main
from pipeline.raw_schema import ensure


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.closed = False

    def close(self):
        self.closed = True


def test_runs_manual_harvest_with_selected_terms_and_years(postgres_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    session = FakeSession()
    received = []

    def collect(session_arg, cursor, terms, years):
        received.append((session_arg, terms, years))
        cursor.execute("TRUNCATE raw.doctrine_article")
        cursor.execute(
            """
            INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
            VALUES ('doaj', 'https://doaj.org/article/abc', 'abc', '{}')
            """
        )
        return 1

    exit_code = main(
        ["--term", "direito civil", "--year", "2024"],
        session_factory=lambda: session,
        collect_fn=collect,
    )

    assert exit_code == 0
    assert received == [(session, ["direito civil"], [2024])]
    assert session.closed
    assert "1 new articles" in capsys.readouterr().out
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.doctrine_article")
        assert cursor.fetchone()[0] == 1


def test_fails_without_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([], session_factory=FakeSession) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_fails_clearly_when_database_cannot_be_reached(monkeypatch, capsys):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test?connect_timeout=1"
    )

    assert main([], session_factory=FakeSession) == 1
    assert "error:" in capsys.readouterr().err


def test_rolls_back_a_failed_harvest(postgres_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    session = FakeSession()
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        cursor.execute("TRUNCATE raw.doctrine_article")

    def collect(session_arg, cursor, terms, years):
        cursor.execute("TRUNCATE raw.doctrine_article")
        cursor.execute(
            """
            INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
            VALUES ('doaj', 'https://doaj.org/article/abc', 'abc', '{}')
            """
        )
        raise DOAJError("incomplete DOAJ result")

    assert main(
        ["--term", "direito", "--year", "2024"],
        session_factory=lambda: session,
        collect_fn=collect,
    ) == 1
    assert "incomplete" in capsys.readouterr().err
    assert session.closed
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.doctrine_article")
        assert cursor.fetchone()[0] == 0
