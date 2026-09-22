import hashlib
import json
import time

PAGE_SIZE = 100
MAX_CONSECUTIVE_EMPTY_PAGES = 5


def payload_hash(hit: dict) -> str:
    return hashlib.sha256(hit["_id"].encode()).hexdigest()


def upsert(cursor, hit: dict, source_url: str, tribunal: str) -> bool:
    cursor.execute(
        """
        INSERT INTO raw.datajud_case (source, tribunal, source_url, payload_hash, payload)
        VALUES ('datajud', %s, %s, %s, %s)
        ON CONFLICT (source, payload_hash) DO NOTHING
        """,
        (tribunal, source_url, payload_hash(hit), json.dumps(hit["_source"])),
    )
    return cursor.rowcount > 0


def search_page(
    session, url: str, query: dict, search_after=None, retries: int = 5, sleep=time.sleep
):
    body = {"size": PAGE_SIZE, "query": query, "sort": [{"@timestamp": "desc"}]}
    if search_after is not None:
        body["search_after"] = search_after

    for attempt in range(retries):
        response = session.post(url, json=body, timeout=180)
        if response.status_code == 429 or response.status_code >= 500:
            sleep(min(30, 3 * (attempt + 1)))
            continue
        response.raise_for_status()
        return response.json()
    return None


def collect(
    session, cursor, url: str, tribunal: str, query: dict, quota: int, sleep=time.sleep
) -> int:
    inserted = seen = 0
    search_after = None
    empty_pages = 0

    while seen < quota:
        data = search_page(session, url, query, search_after, sleep=sleep)
        if data is None:
            break
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            break

        new = sum(upsert(cursor, hit, url, tribunal) for hit in hits)
        seen += len(hits)
        inserted += new
        search_after = hits[-1]["sort"]
        empty_pages = empty_pages + 1 if new == 0 else 0
        if empty_pages >= MAX_CONSECUTIVE_EMPTY_PAGES:
            break

    return inserted
