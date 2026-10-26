import json
from datetime import date

import psycopg2
import pytest
import requests

from pipeline import dw_precedent
from pipeline.raw_schema import ensure as ensure_raw
from pipeline.stj_precedents import (
    TEMAS_URL,
    download,
    harvest,
    is_valid,
    parse_temas,
    subject_codes,
    tema_link,
)

HEADER = (
    "sequencialPrecedente,tipoPrecedente,numeroPrecedente,dataPrimeiraAfetacao,dataJulgamento,"
    "dataPublicacaoAcordao,situacao,informacoesComplementares,questaoSubmetidaAJulgamento,teseFirmada,"
    "anotacoesNUGEPNAC,delimitacaoJulgado,entendimentoAnterior,referenciaLegislativa,referenciaSumular,"
    "sumulaOriginada,audienciaPublica,dataAudienciaPublica,orgaoJulgador,Assuntos,"
    "numeroRepercussaoGeralSTF,descricaoRepercussaoGeral"
)


def row(seq, kind, number, judged, status, question, thesis, body, subjects):
    return (
        f'{seq},{kind},{number},,{judged},,{status},,"{question}","{thesis}",'
        f',,,,,,,,{body},"{subjects}",,'
    )


TEMAS = "\n".join([
    HEADER,
    row(1, "Tema", 952, "2016-12-14", "Trânsito em Julgado", "Reajuste por faixa etária.\n",
        "O reajuste por faixa etária é válido.\nDesde que previsto.", "S2",
        "1156- DIREITO DO CONSUMIDOR, 7771- Contratos de Consumo, 6233- Planos de Saúde"),
    row(2, "Tema", 1016, "", "Afetado", "Planos coletivos.", "", "S2", "6233- Planos de Saúde"),
    row(3, "Tema", 400, "2010-05-12", "Cancelado", "Tema cancelado.", "Tese antiga.", "S1",
        "6233- Planos de Saúde"),
    row(4, "Controvérsia", 7, "", "Vinculada a Tema", "Controvérsia.",
        "Tese da controvérsia.", "S2", "6233- Planos de Saúde"),
    row(5, "Tema", 1100, "2023-02-01", "Acórdão Publicado", "Outro assunto.",
        "Tese de outro assunto.", "CE", "9985- DIREITO ADMINISTRATIVO"),
]) + "\n"


def test_reads_every_field_of_a_thesis():
    temas = parse_temas(TEMAS)

    first = temas[0]
    assert first["kind"] == "Tema"
    assert first["number"] == 952
    assert first["thesis"] == "O reajuste por faixa etária é válido.\nDesde que previsto."
    assert first["question"] == "Reajuste por faixa etária."
    assert first["status"] == "Trânsito em Julgado"
    assert first["judged_at"] == "2016-12-14"
    assert first["judging_body"] == "S2"
    assert first["subject_codes"] == [1156, 7771, 6233]


def test_reads_the_subject_codes_in_order():
    assert subject_codes("1156- DIREITO DO CONSUMIDOR, 6233- Planos de Saúde") == [1156, 6233]
    assert subject_codes("") == []


def test_keeps_only_repetitive_themes_with_a_thesis_that_were_not_cancelled():
    temas = parse_temas(TEMAS)

    assert [tema["number"] for tema in temas if is_valid(tema)] == [952, 1100]


def test_links_to_the_official_page_of_the_theme():
    assert tema_link(952) == (
        "https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp"
        "?novaConsulta=true&tipo_pesquisa=T&cod_tema_inicial=952&cod_tema_final=952"
    )


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        ensure_raw(cur)
        cur.execute("TRUNCATE raw.stj_precedent")
        cur.execute("TRUNCATE dw.dim_precedent RESTART IDENTITY CASCADE")
        cur.execute("TRUNCATE dw.dim_subject RESTART IDENTITY CASCADE")
        cur.execute(
            "INSERT INTO dw.dim_subject (subject_name, subject_code) VALUES "
            "('DIREITO DO CONSUMIDOR', 1156), ('Contratos de Consumo', 7771), "
            "('Planos de Saúde', 6233), "
            "('DIREITO ADMINISTRATIVO', 9985)"
        )
        yield cur
        connection.rollback()


def test_stores_every_theme_of_the_file_in_raw(cursor):
    stored = harvest(cursor, lambda url: TEMAS)

    cursor.execute(
        "SELECT kind, number, source_url FROM raw.stj_precedent ORDER BY kind, number"
    )
    assert stored == 5
    assert cursor.fetchall()[0] == ("Controvérsia", 7, TEMAS_URL)


def test_harvesting_twice_keeps_one_row_per_theme(cursor):
    harvest(cursor, lambda url: TEMAS)
    harvest(cursor, lambda url: TEMAS)

    cursor.execute("SELECT count(*) FROM raw.stj_precedent")
    assert cursor.fetchone()[0] == 5


def test_loads_the_valid_theses_into_the_warehouse(cursor):
    harvest(cursor, lambda url: TEMAS)

    dw_precedent.load(cursor, area_codes={1156, 9985})

    cursor.execute(
        "SELECT precedent_kind, precedent_number, thesis, status, judged_at, judging_body, "
        "source_url FROM dw.dim_precedent ORDER BY precedent_number"
    )
    rows = cursor.fetchall()
    assert [r[1] for r in rows] == [952, 1100]
    assert rows[0][2] == "O reajuste por faixa etária é válido.\nDesde que previsto."
    assert rows[0][4] == date(2016, 12, 14)
    assert rows[0][6] == tema_link(952)


def test_links_a_thesis_to_its_subjects_but_not_to_the_area(cursor):
    harvest(cursor, lambda url: TEMAS)

    dw_precedent.load(cursor, area_codes={1156, 9985})

    cursor.execute(
        "SELECT p.precedent_number, s.subject_code FROM dw.bridge_subject_precedent b "
        "JOIN dw.dim_precedent p ON p.precedent_sk = b.precedent_sk "
        "JOIN dw.dim_subject s ON s.subject_sk = b.subject_sk ORDER BY 1, 2"
    )
    assert cursor.fetchall() == [(952, 6233), (952, 7771)]


def test_loading_twice_keeps_one_row_per_thesis(cursor):
    harvest(cursor, lambda url: TEMAS)

    dw_precedent.load(cursor, area_codes={1156, 9985})
    dw_precedent.load(cursor, area_codes={1156, 9985})

    cursor.execute("SELECT count(*) FROM dw.dim_precedent")
    assert cursor.fetchone()[0] == 2
    cursor.execute("SELECT count(*) FROM dw.bridge_subject_precedent")
    assert cursor.fetchone()[0] == 2


def test_keeps_the_payload_of_the_file_as_it_came(cursor):
    harvest(cursor, lambda url: TEMAS)

    cursor.execute("SELECT payload FROM raw.stj_precedent WHERE number = 952")
    payload = cursor.fetchone()[0]
    assert payload["teseFirmada"].startswith("O reajuste")
    assert json.dumps(payload)


class FakeResponse:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text
        self.encoding = None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_downloads_the_file_as_utf8(monkeypatch):
    calls = []
    monkeypatch.setattr(
        requests, "get", lambda url, **kwargs: calls.append(url) or FakeResponse(200, "ok")
    )

    assert download(TEMAS_URL, sleep=lambda seconds: None) == "ok"
    assert calls == [TEMAS_URL]


def test_retries_while_the_portal_is_down(monkeypatch):
    responses = iter([FakeResponse(504), FakeResponse(429), FakeResponse(200, "ok")])
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: next(responses))

    assert download(TEMAS_URL, sleep=lambda seconds: None) == "ok"


def test_retries_after_a_connection_error(monkeypatch):
    attempts = []

    def get(url, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            raise requests.ConnectionError("down")
        return FakeResponse(200, "ok")

    monkeypatch.setattr(requests, "get", get)

    assert download(TEMAS_URL, sleep=lambda seconds: None) == "ok"


def test_gives_up_when_the_portal_never_answers(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: FakeResponse(504))

    with pytest.raises(requests.RequestException):
        download(TEMAS_URL, retries=2, sleep=lambda seconds: None)


def test_reports_a_client_error_at_once(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: FakeResponse(404))

    with pytest.raises(requests.HTTPError):
        download(TEMAS_URL, sleep=lambda seconds: None)
