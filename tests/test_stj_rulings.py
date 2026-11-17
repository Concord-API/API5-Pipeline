import io
import json
import zipfile

import psycopg2
import pytest
import requests

from pipeline.raw_schema import ensure as ensure_raw
from pipeline.stj_rulings import (
    DATASETS,
    PACKAGE_URL,
    download,
    harvest,
    parse_rulings,
)


def ruling(ruling_id, **fields):
    return {
        "id": ruling_id,
        "numeroProcesso": "1997135",
        "siglaClasse": "AgInt no REsp",
        "nomeOrgaoJulgador": "TERCEIRA TURMA",
        "ementa": "PROCESSUAL CIVIL. AGRAVO INTERNO.",
        "dataDecisao": "20220627",
        **fields,
    }


def as_json(records):
    return json.dumps(records, ensure_ascii=False).encode("utf-8")


def as_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, records in files.items():
            archive.writestr(name, as_json(records))
    return buffer.getvalue()


def test_reads_the_rulings_of_a_monthly_file():
    rulings = parse_rulings("20220630.json", as_json([ruling("000819199"), ruling("000819200")]))

    assert [item["id"] for item in rulings] == ["000819199", "000819200"]
    assert rulings[0]["ementa"] == "PROCESSUAL CIVIL. AGRAVO INTERNO."


def test_reads_every_file_of_the_historical_zip():
    content = as_zip({
        "20220508/a.json": [ruling("1")],
        "20220508/b.json": [ruling("2"), ruling("3")],
    })

    assert [item["id"] for item in parse_rulings("20220508.zip", content)] == ["1", "2", "3"]


def test_ignores_files_inside_the_zip_that_are_not_json():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("leia-me.txt", "não é acórdão")
        archive.writestr("dados.json", as_json([ruling("1")]))

    assert [item["id"] for item in parse_rulings("historico.zip", buffer.getvalue())] == ["1"]


def test_reads_a_file_that_starts_with_a_byte_order_mark():
    content = "﻿".encode("utf-8") + as_json([ruling("1")])

    assert [item["id"] for item in parse_rulings("20220630.json", content)] == ["1"]


def test_skips_a_record_without_an_id():
    content = as_json([ruling("1"), {**ruling("2"), "id": None}, {**ruling("3"), "id": "  "}])

    assert [item["id"] for item in parse_rulings("20220630.json", content)] == ["1"]


def package(dataset, *resources):
    return json.dumps({
        "success": True,
        "result": {
            "name": dataset,
            "resources": [
                {"name": name, "format": fmt, "url": f"https://stj.example/{dataset}/{name}"}
                for name, fmt in resources
            ],
        },
    }).encode("utf-8")


def portal(files):
    def fetch(url):
        if url not in files:
            raise AssertionError(f"requested an unexpected URL: {url}")
        return files[url]

    return fetch


def one_dataset_portal(dataset, monthly, historical):
    return {
        PACKAGE_URL.format(dataset=dataset): package(
            dataset,
            ("20220508.zip", "ZIP"),
            ("dicionario-espelhodoacordao.csv", "CSV"),
            ("20220630.json", "JSON"),
        ),
        f"https://stj.example/{dataset}/20220508.zip": as_zip({"a.json": historical}),
        f"https://stj.example/{dataset}/20220630.json": as_json(monthly),
    }


@pytest.fixture
def cursor(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cur:
        ensure_raw(cur)
        cur.execute("TRUNCATE raw.stj_ruling")
        yield cur


def test_harvests_only_the_civil_panels():
    assert DATASETS == (
        "espelhos-de-acordaos-primeira-secao",
        "espelhos-de-acordaos-segunda-secao",
        "espelhos-de-acordaos-primeira-turma",
        "espelhos-de-acordaos-segunda-turma",
        "espelhos-de-acordaos-terceira-turma",
        "espelhos-de-acordaos-quarta-turma",
    )


def test_stores_each_ruling_of_the_panel_with_its_file(cursor):
    dataset = "espelhos-de-acordaos-terceira-turma"
    files = one_dataset_portal(dataset, monthly=[ruling("2")], historical=[ruling("1")])

    stored = harvest(cursor, portal(files), datasets=(dataset,))

    cursor.execute(
        "SELECT id, dataset, source_url, payload->>'ementa' FROM raw.stj_ruling ORDER BY id"
    )
    summary = "PROCESSUAL CIVIL. AGRAVO INTERNO."
    assert cursor.fetchall() == [
        ("1", dataset, f"https://stj.example/{dataset}/20220508.zip", summary),
        ("2", dataset, f"https://stj.example/{dataset}/20220630.json", summary),
    ]
    assert stored == 2


def test_keeps_one_row_per_ruling_when_files_repeat_it(cursor):
    dataset = "espelhos-de-acordaos-terceira-turma"
    files = one_dataset_portal(
        dataset,
        monthly=[ruling("1", ementa="EMENTA REVISTA.")],
        historical=[ruling("1"), ruling("1")],
    )

    harvest(cursor, portal(files), datasets=(dataset,))
    harvest(cursor, portal(files), datasets=(dataset,))

    cursor.execute("SELECT count(*), max(payload->>'ementa') FROM raw.stj_ruling")
    assert cursor.fetchone() == (1, "EMENTA REVISTA.")


def test_never_downloads_the_data_dictionary(cursor):
    dataset = "espelhos-de-acordaos-terceira-turma"
    files = one_dataset_portal(dataset, monthly=[], historical=[])

    assert harvest(cursor, portal(files), datasets=(dataset,)) == 0


class FakeResponse:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def test_downloads_the_file_as_bytes(monkeypatch):
    calls = []
    monkeypatch.setattr(
        requests, "get", lambda url, **kwargs: calls.append(url) or FakeResponse(200, b"[]")
    )

    assert download("https://stj.example/a.json", sleep=lambda seconds: None) == b"[]"
    assert calls == ["https://stj.example/a.json"]


def test_retries_while_the_portal_is_down(monkeypatch):
    responses = iter([FakeResponse(504), FakeResponse(429), FakeResponse(200, b"[]")])
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: next(responses))

    assert download("https://stj.example/a.json", sleep=lambda seconds: None) == b"[]"


def test_gives_up_when_the_portal_never_answers(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **kwargs: FakeResponse(504))

    with pytest.raises(requests.RequestException):
        download("https://stj.example/a.json", retries=2, sleep=lambda seconds: None)
