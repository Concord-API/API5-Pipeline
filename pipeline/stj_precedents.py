import csv
import io
import json
import re
import time

import requests

TEMAS_URL = (
    "https://dadosabertos.web.stj.jus.br/dataset/4238da2f-c07b-4c1a-b345-4402accacdcf"
    "/resource/df29da13-7d6b-41ba-ad96-cd1a5bbd191c/download/temas.csv"
)
TEMA_PAGE = (
    "https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp"
    "?novaConsulta=true&tipo_pesquisa=T&cod_tema_inicial={number}&cod_tema_final={number}"
)
SUBJECT_CODE = re.compile(r"(\d+)\s*-")


def subject_codes(text):
    return [int(code) for code in SUBJECT_CODE.findall(text or "")]


def _text(row, field):
    value = (row.get(field) or "").strip()
    return value or None


def from_row(row):
    number = (row.get("numeroPrecedente") or "").strip()
    if not number.isdigit():
        return None
    return {
        "kind": (row.get("tipoPrecedente") or "").strip(),
        "number": int(number),
        "thesis": _text(row, "teseFirmada"),
        "question": _text(row, "questaoSubmetidaAJulgamento"),
        "status": _text(row, "situacao") or "",
        "judged_at": _text(row, "dataJulgamento"),
        "judging_body": _text(row, "orgaoJulgador"),
        "subject_codes": subject_codes(row.get("Assuntos")),
        "payload": row,
    }


def parse_temas(text):
    rows = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    return [tema for tema in (from_row(row) for row in rows) if tema is not None]


def is_valid(tema):
    return (
        tema["kind"] == "Tema"
        and bool(tema["thesis"])
        and not tema["status"].lower().startswith("cancel")
    )


def tema_link(number):
    return TEMA_PAGE.format(number=number)


def download(url, retries=5, sleep=time.sleep):
    for attempt in range(retries):
        try:
            response = requests.get(
                url, timeout=180, headers={"User-Agent": "Ratio-DW/1.0 (FATEC API-5)"}
            )
        except requests.RequestException:
            sleep(min(30, 5 * (attempt + 1)))
            continue
        if response.status_code >= 500 or response.status_code == 429:
            sleep(min(30, 5 * (attempt + 1)))
            continue
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text
    raise requests.RequestException(f"o portal do STJ não respondeu: {url}")


def harvest(cursor, fetch=download, url=TEMAS_URL):
    temas = parse_temas(fetch(url))
    for tema in temas:
        cursor.execute(
            """
            INSERT INTO raw.stj_precedent (kind, number, source_url, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (kind, number) DO UPDATE
            SET source_url = EXCLUDED.source_url,
                payload = EXCLUDED.payload,
                collected_at = now()
            """,
            (tema["kind"], tema["number"], url, json.dumps(tema["payload"], ensure_ascii=False)),
        )
    return len(temas)
