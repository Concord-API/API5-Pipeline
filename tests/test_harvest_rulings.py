import json

import psycopg2

from pipeline.harvest_rulings import main
from pipeline.raw_schema import ensure

RULINGS = [
    {"id": "000819199", "nomeOrgaoJulgador": "TERCEIRA TURMA", "ementa": "PROCESSUAL CIVIL."},
    {"id": "000819200", "nomeOrgaoJulgador": "TERCEIRA TURMA", "ementa": "CONSUMIDOR."},
]


def empty_raw(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        cursor.execute("TRUNCATE raw.stj_ruling")


def test_harvests_the_rulings_from_a_local_folder(postgres_url, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    empty_raw(postgres_url)
    folder = tmp_path / "espelhos-de-acordaos-terceira-turma"
    folder.mkdir()
    (folder / "20220630.json").write_text(json.dumps(RULINGS), encoding="utf-8")

    assert main(["--dir", str(tmp_path)]) == 0

    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id, dataset FROM raw.stj_ruling ORDER BY id")
        assert cursor.fetchall() == [
            ("000819199", "espelhos-de-acordaos-terceira-turma"),
            ("000819200", "espelhos-de-acordaos-terceira-turma"),
        ]
    assert "2 STJ rulings" in capsys.readouterr().out


def test_skips_a_local_folder_of_a_panel_out_of_scope(postgres_url, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    empty_raw(postgres_url)
    folder = tmp_path / "espelhos-de-acordaos-quinta-turma"
    folder.mkdir()
    (folder / "20220630.json").write_text(json.dumps(RULINGS), encoding="utf-8")

    assert main(["--dir", str(tmp_path)]) == 0

    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.stj_ruling")
        assert cursor.fetchone()[0] == 0


def test_reports_a_missing_database(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err


def test_reports_a_folder_that_does_not_exist(postgres_url, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)

    assert main(["--dir", str(tmp_path / "nada")]) == 1
    assert "error:" in capsys.readouterr().err
