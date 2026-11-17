import io
import json
import time
import zipfile

import requests

PACKAGE_URL = "https://dadosabertos.web.stj.jus.br/api/3/action/package_show?id={dataset}"

DATASETS = (
    "espelhos-de-acordaos-primeira-secao",
    "espelhos-de-acordaos-segunda-secao",
    "espelhos-de-acordaos-primeira-turma",
    "espelhos-de-acordaos-segunda-turma",
    "espelhos-de-acordaos-terceira-turma",
    "espelhos-de-acordaos-quarta-turma",
)

RULING_FORMATS = {"JSON", "ZIP"}


def _records(content):
    return json.loads(content.decode("utf-8-sig"))


def _has_id(record):
    return isinstance(record.get("id"), str) and record["id"].strip() != ""


def parse_rulings(name, content):
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            records = [
                record
                for member in sorted(archive.namelist())
                if member.lower().endswith(".json")
                for record in _records(archive.read(member))
            ]
    else:
        records = _records(content)
    return [record for record in records if _has_id(record)]


def ruling_files(package):
    return sorted(
        (resource["name"], resource["url"])
        for resource in package["result"]["resources"]
        if (resource.get("format") or "").upper() in RULING_FORMATS
    )


def download(url, retries=5, sleep=time.sleep):
    for attempt in range(retries):
        try:
            response = requests.get(
                url, timeout=300, headers={"User-Agent": "Ratio-DW/1.0 (FATEC API-5)"}
            )
        except requests.RequestException:
            sleep(min(30, 5 * (attempt + 1)))
            continue
        if response.status_code >= 500 or response.status_code == 429:
            sleep(min(30, 5 * (attempt + 1)))
            continue
        response.raise_for_status()
        return response.content
    raise requests.RequestException(f"o portal do STJ não respondeu: {url}")


def harvest(cursor, fetch=download, datasets=DATASETS):
    stored = set()
    for dataset in datasets:
        package = json.loads(fetch(PACKAGE_URL.format(dataset=dataset)))
        for name, url in ruling_files(package):
            for record in parse_rulings(name, fetch(url)):
                cursor.execute(
                    """
                    INSERT INTO raw.stj_ruling (id, dataset, source_url, payload)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET dataset = EXCLUDED.dataset,
                        source_url = EXCLUDED.source_url,
                        payload = EXCLUDED.payload,
                        collected_at = now()
                    """,
                    (record["id"], dataset, url, json.dumps(record, ensure_ascii=False)),
                )
                stored.add(record["id"])
    return len(stored)
