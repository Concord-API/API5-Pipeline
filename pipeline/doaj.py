import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

API_URL = "https://doaj.org/api/search/articles"
PAGE_SIZE = 100
RESULT_LIMIT = 1000
REQUEST_INTERVAL = 0.15
MIN_CREATED = datetime(1900, 1, 1, tzinfo=timezone.utc)
MAX_CREATED = datetime(2100, 1, 1, tzinfo=timezone.utc)
TERMS_FILE = Path(__file__).parent / "data" / "doaj_terms.json"


class DOAJError(Exception):
    pass


def load_terms(path=TERMS_FILE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _timestamp(value):
    return value.isoformat().replace("+00:00", "Z")


def _search_page(session, query, page, sleep):
    url = f"{API_URL}/{quote(query, safe='')}"
    for attempt in range(4):
        sleep(REQUEST_INTERVAL)
        try:
            response = session.get(
                url, params={"page": page, "pageSize": PAGE_SIZE}, timeout=30
            )
        except requests.RequestException as error:
            if attempt == 3:
                raise DOAJError(f"DOAJ request failed: {query}, page {page}") from error
            sleep(2 * (attempt + 1))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 3:
                raise DOAJError(f"DOAJ unavailable: {query}, page {page}")
            sleep(2 * (attempt + 1))
            continue
        response.raise_for_status()
        data = response.json()
        if not isinstance(data.get("total"), int) or not isinstance(data.get("results"), list):
            raise DOAJError(f"invalid DOAJ response: {query}, page {page}")
        return data
    raise DOAJError(f"DOAJ request failed: {query}, page {page}")


def _window_query(query, start, end):
    return f"{query} AND created_date:[{_timestamp(start)} TO {_timestamp(end)}}}"


def _insert(cursor, record):
    article_id = record.get("id")
    if not article_id:
        raise DOAJError("DOAJ article has no id")
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
    cursor.execute(
        """
        INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
        VALUES ('doaj', %s, %s, %s)
        ON CONFLICT (source, payload_hash) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            collected_at = now(),
            payload = EXCLUDED.payload
        WHERE raw.doctrine_article.payload IS DISTINCT FROM EXCLUDED.payload
        """,
        (
            f"https://doaj.org/article/{article_id}",
            hashlib.sha256(str(article_id).encode("utf-8")).hexdigest(),
            payload,
        ),
    )
    return cursor.rowcount > 0


def _save_pages(session, cursor, query, first, sleep):
    total = first["total"]
    inserted = seen = 0
    page = 1
    data = first
    while seen < total:
        records = data["results"]
        if not records:
            raise DOAJError(f"incomplete DOAJ result: {query}, {seen}/{total}")
        if seen + len(records) > total:
            raise DOAJError(f"inconsistent DOAJ result: {query}")
        inserted += sum(_insert(cursor, record) for record in records)
        seen += len(records)
        if seen < total:
            page += 1
            if page > RESULT_LIMIT // PAGE_SIZE:
                raise DOAJError(f"DOAJ result exceeds page limit: {query}")
            data = _search_page(session, query, page, sleep)
            if data["total"] != total:
                raise DOAJError(f"DOAJ result changed during paging: {query}")
    return inserted


def _collect_window(session, cursor, query, start, end, first, sleep):
    total = first["total"]
    if total <= RESULT_LIMIT:
        return _save_pages(session, cursor, _window_query(query, start, end), first, sleep)
    midpoint = start + (end - start) / 2
    if midpoint <= start or midpoint >= end:
        raise DOAJError(f"DOAJ partition cannot be split: {query}")
    left_query = _window_query(query, start, midpoint)
    right_query = _window_query(query, midpoint, end)
    left = _search_page(session, left_query, 1, sleep)
    right = _search_page(session, right_query, 1, sleep)
    if left["total"] + right["total"] != total:
        raise DOAJError(f"DOAJ partition totals differ: {query}")
    return (
        _collect_window(session, cursor, query, start, midpoint, left, sleep)
        + _collect_window(session, cursor, query, midpoint, end, right, sleep)
    )


def _collect_query(session, cursor, query, sleep):
    first = _search_page(session, query, 1, sleep)
    if first["total"] <= RESULT_LIMIT:
        return _save_pages(session, cursor, query, first, sleep)
    window_query = _window_query(query, MIN_CREATED, MAX_CREATED)
    window = _search_page(session, window_query, 1, sleep)
    if window["total"] != first["total"]:
        raise DOAJError(f"DOAJ partition does not cover all results: {query}")
    return _collect_window(session, cursor, query, MIN_CREATED, MAX_CREATED, window, sleep)


def collect(session, cursor, terms=None, years=None, sleep=time.sleep, on_bucket=None):
    terms = load_terms() if terms is None else terms
    years = range(1997, datetime.now(timezone.utc).year + 1) if years is None else years
    inserted = 0
    for term in terms:
        for year in years:
            changed = _collect_query(session, cursor, f"{term} AND bibjson.year:{year}", sleep)
            inserted += changed
            cursor.connection.commit()
            if on_bucket is not None:
                on_bucket(term, year, changed)
    return inserted
