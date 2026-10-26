import psycopg2

from pipeline.harvest_precedents import main
from pipeline.raw_schema import ensure

TEMAS = (
    "tipoPrecedente,numeroPrecedente,teseFirmada,situacao,Assuntos\n"
    "Tema,952,Tese firmada.,Trânsito em Julgado,6233- Planos de Saúde\n"
)


def test_harvests_the_theses_from_a_local_file(postgres_url, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        ensure(cursor)
        cursor.execute("TRUNCATE raw.stj_precedent")
    path = tmp_path / "temas.csv"
    path.write_text(TEMAS, encoding="utf-8")

    assert main(["--file", str(path)]) == 0

    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT kind, number FROM raw.stj_precedent")
        assert cursor.fetchall() == [("Tema", 952)]
    assert "1 STJ themes" in capsys.readouterr().out


def test_reports_a_missing_database(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([]) == 1
    assert "DATABASE_URL" in capsys.readouterr().err
