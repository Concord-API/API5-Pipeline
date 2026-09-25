from urllib.parse import unquote

import psycopg2
import pytest
import requests

from pipeline.doaj import DOAJError, collect
from pipeline.raw_schema import ensure


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, records, responses=None):
        self.records = records
        self.responses = list(responses or [])
        self.requests = []

    def get(self, url, params, timeout):
        query = unquote(url.rsplit("/", 1)[-1])
        self.requests.append((query, params["page"]))
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        selected = self.records
        if "created_date:[" in query:
            window = query.split("created_date:[", 1)[1].split("}", 1)[0]
            start, end = window.split(" TO ")
            selected = [
                record for record in selected if start <= record["created_date"] < end
            ]
        offset = (params["page"] - 1) * params["pageSize"]
        return FakeResponse(200, {
            "total": len(selected),
            "results": selected[offset:offset + params["pageSize"]],
        })


def article(id_, created_date="2024-02-01T00:00:00Z"):
    return {
        "id": str(id_),
        "created_date": created_date,
        "bibjson": {"title": f"Article {id_}", "year": "2024"},
    }


@pytest.fixture
def cursor(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cur:
        ensure(cur)
        cur.execute("TRUNCATE raw.doctrine_article")
        yield cur
        connection.commit()


def test_collects_full_payload_and_deduplicates_overlapping_terms(cursor):
    session = FakeSession([article("abc")])

    inserted = collect(session, cursor, terms=("direito", "jurisprudência"), years=(2024,))

    assert inserted == 1
    cursor.execute("SELECT source, source_url, payload->>'id' FROM raw.doctrine_article")
    assert cursor.fetchone() == ("doaj", "https://doaj.org/article/abc", "abc")
    assert collect(session, cursor, terms=("direito",), years=(2024,)) == 0


def test_updates_metadata_without_creating_a_second_article(cursor):
    record = article("abc")
    session = FakeSession([record])
    assert collect(session, cursor, terms=("direito",), years=(2024,)) == 1

    record["bibjson"]["title"] = "Updated title"
    changed = collect(session, cursor, terms=("direito",), years=(2024,))

    assert changed == 1
    cursor.execute("SELECT count(*), max(payload->'bibjson'->>'title') FROM raw.doctrine_article")
    assert cursor.fetchone() == (1, "Updated title")
    assert collect(session, cursor, terms=("direito",), years=(2024,)) == 0


def test_reports_each_completed_search_bucket(cursor):
    session = FakeSession([article("abc")])
    completed = []

    collect(
        session,
        cursor,
        terms=("direito", "jurisprudência"),
        years=(2024,),
        on_bucket=lambda term, year, changed: completed.append((term, year, changed)),
    )

    assert completed == [("direito", 2024, 1), ("jurisprudência", 2024, 0)]


def test_splits_above_the_api_limit_and_collects_every_record(cursor):
    records = [article(i) for i in range(500)]
    records += [article(i, "2024-09-01T00:00:00Z") for i in range(500, 1001)]
    session = FakeSession(records)

    inserted = collect(session, cursor, terms=("direito",), years=(2024,))

    assert inserted == 1001
    cursor.execute("SELECT count(*) FROM raw.doctrine_article")
    assert cursor.fetchone()[0] == 1001
    assert any("created_date:[" in query for query, _ in session.requests)
    assert max(page for _, page in session.requests) <= 10


def test_rejects_a_partition_that_cannot_account_for_all_results(cursor):
    session = FakeSession([], responses=[
        FakeResponse(200, {"total": 1001, "results": []}),
        FakeResponse(200, {"total": 1000, "results": []}),
    ])

    with pytest.raises(DOAJError, match="partition"):
        collect(session, cursor, terms=("direito",), years=(2024,))


def test_retries_temporary_errors_and_rejects_incomplete_pages(cursor):
    session = FakeSession([], responses=[
        requests.ConnectionError("reset"),
        FakeResponse(429),
        FakeResponse(200, {"total": 2, "results": [article("a")]}),
        FakeResponse(200, {"total": 2, "results": []}),
    ])

    with pytest.raises(DOAJError, match="incomplete"):
        collect(session, cursor, terms=("direito",), years=(2024,), sleep=lambda _: None)

    assert len(session.requests) == 4


def test_rejects_unexpected_client_errors(cursor):
    session = FakeSession([], responses=[FakeResponse(400)])

    with pytest.raises(requests.HTTPError):
        collect(session, cursor, terms=("direito",), years=(2024,))
