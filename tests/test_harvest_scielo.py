import psycopg2

from pipeline.harvest_scielo import main
from pipeline.raw_schema import ensure
from pipeline.scielo import SciELOError


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.closed = False

    def close(self):
        self.closed = True


def test_runs_selected_journal_and_reports_progress(postgres_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    session = FakeSession()

    def collect(session_arg, cursor, issns, on_journal):
        assert session_arg is session
        assert issns == ["1806-6445"]
        cursor.execute("TRUNCATE raw.doctrine_article")
        cursor.execute(
            """
            INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
            VALUES ('scielo', 'https://www.scielo.br/article/abc', 'abc', '{}')
            """
        )
        on_journal("1806-6445", 1, 1)
        return 1

    assert main(["--issn", "1806-6445"],
                session_factory=lambda: session, collect_fn=collect) == 0
    assert session.closed
    output = capsys.readouterr().out
    assert "1806-6445: 1 articles, 1 new or updated" in output
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.doctrine_article")
        assert cursor.fetchone()[0] == 1


def test_fails_without_database_url(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([], session_factory=FakeSession) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_rolls_back_failed_journal(postgres_url, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        cursor.execute("TRUNCATE raw.doctrine_article")

    def collect(session_arg, cursor, issns, on_journal):
        cursor.execute(
            """
            INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
            VALUES ('scielo', 'https://www.scielo.br/article/abc', 'abc', '{}')
            """
        )
        raise SciELOError("incomplete SciELO identifiers")

    assert main([], session_factory=FakeSession, collect_fn=collect) == 1
    assert "incomplete" in capsys.readouterr().err
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.doctrine_article")
        assert cursor.fetchone()[0] == 0
