import io
import json
import zipfile

from pipeline.stj_rulings import parse_rulings


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
