import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote

import requests

API_URL = "https://articlemeta.scielo.org/api/v1/article/"
IDENTIFIERS_URL = f"{API_URL}identifiers/"
PAGE_SIZE = 1000
REQUEST_INTERVAL = 0.05
ISSNS_FILE = Path(__file__).parent / "data" / "scielo_issns.json"


class SciELOError(Exception):
    pass


def load_issns(path=ISSNS_FILE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _get_json(session, url, params, sleep):
    attempt = 0
    while True:
        sleep(REQUEST_INTERVAL)
        try:
            response = session.get(url, params=params, timeout=30)
        except requests.RequestException as error:
            if attempt == 3:
                raise SciELOError(f"SciELO request failed: {url}") from error
            sleep(2 * (attempt + 1))
            attempt += 1
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 3:
                raise SciELOError(f"SciELO unavailable: {url}")
            sleep(2 * (attempt + 1))
            attempt += 1
            continue
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise SciELOError(f"invalid SciELO response: {url}")
        return data


def _parse_identifier_page(data, issn, offset, total, seen):
    page_total = data.get("meta", {}).get("total")
    objects = data.get("objects")
    if not isinstance(page_total, int) or page_total < 0 or not isinstance(objects, list):
        raise SciELOError(f"invalid SciELO identifier page: {issn}, offset {offset}")
    if total is not None and page_total != total:
        raise SciELOError(f"SciELO identifier total changed: {issn}")
    if not objects and offset < page_total:
        raise SciELOError(f"incomplete SciELO identifiers: {issn}, {offset}/{page_total}")
    if offset + len(objects) > page_total:
        raise SciELOError(f"inconsistent SciELO identifiers: {issn}")

    codes = []
    for item in objects:
        code = item.get("code") if isinstance(item, dict) else None
        if not code or code in seen:
            raise SciELOError(f"invalid or duplicate SciELO code: {issn}")
        seen.add(code)
        codes.append(code)
    return page_total, codes


def _article_codes(session, issn, sleep):
    codes = []
    seen = set()
    total = None
    offset = 0
    while total is None or offset < total:
        data = _get_json(session, IDENTIFIERS_URL, {
            "collection": "scl", "issn": issn, "offset": offset, "limit": PAGE_SIZE,
        }, sleep)
        total, page_codes = _parse_identifier_page(data, issn, offset, total, seen)
        codes.extend(page_codes)
        offset += len(page_codes)
    return codes


def _insert(cursor, code, payload):
    source_url = f"https://www.scielo.br/scielo.php?script=sci_arttext&pid={quote(code, safe='')}"
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    cursor.execute(
        """
        INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
        VALUES ('scielo', %s, %s, %s)
        ON CONFLICT (source, payload_hash) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            collected_at = now(),
            payload = EXCLUDED.payload
        WHERE raw.doctrine_article.payload IS DISTINCT FROM EXCLUDED.payload
        """,
        (source_url, hashlib.sha256(code.encode("utf-8")).hexdigest(), serialized),
    )
    return cursor.rowcount > 0


def collect(session, cursor, issns=None, sleep=time.sleep, on_journal=None):
    issns = load_issns() if issns is None else issns
    changed = 0
    for issn in issns:
        codes = _article_codes(session, issn, sleep)
        journal_changed = 0
        for code in codes:
            data = _get_json(session, API_URL, {"collection": "scl", "code": code}, sleep)
            if data.get("code") != code or not isinstance(data.get("article"), dict):
                raise SciELOError(f"SciELO article code or metadata is invalid: {code}")
            journal_changed += _insert(cursor, code, data)
        cursor.connection.commit()
        changed += journal_changed
        if on_journal is not None:
            on_journal(issn, len(codes), journal_changed)
    return changed
