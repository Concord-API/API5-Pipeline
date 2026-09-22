import psycopg2
import pytest
import requests

from pipeline.datajud import collect
from pipeline.raw_schema import ensure

URL = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def post(self, url, json, timeout):
        self.requests.append(json)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def hit(id_, sort_value):
    return {"_id": id_, "_source": {"n": id_}, "sort": [sort_value]}


@pytest.fixture
def cursor(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cur:
        ensure(cur)
        cur.execute("TRUNCATE raw.datajud_case")
        yield cur
        connection.commit()


def row_count(cursor):
    cursor.execute("SELECT count(*) FROM raw.datajud_case")
    return cursor.fetchone()[0]


def test_collects_until_the_quota_is_reached(cursor):
    session = FakeSession([
        FakeResponse(200, {"hits": {"hits": [hit("a", 1), hit("b", 2)]}}),
        FakeResponse(200, {"hits": {"hits": [hit("c", 3)]}}),
    ])

    inserted = collect(session, cursor, URL, "tjsp", {}, quota=3, sleep=lambda _: None)

    assert inserted == 3
    assert row_count(cursor) == 3


def test_stops_on_an_empty_page(cursor):
    session = FakeSession([
        FakeResponse(200, {"hits": {"hits": [hit("a", 1)]}}),
        FakeResponse(200, {"hits": {"hits": []}}),
    ])

    inserted = collect(session, cursor, URL, "tjsp", {}, quota=100, sleep=lambda _: None)

    assert inserted == 1


def test_is_idempotent_on_the_same_document(cursor):
    session = FakeSession([
        FakeResponse(200, {"hits": {"hits": [hit("a", 1)]}}),
        FakeResponse(200, {"hits": {"hits": [hit("a", 1)]}}),
        FakeResponse(200, {"hits": {"hits": []}}),
    ])

    inserted = collect(session, cursor, URL, "tjsp", {}, quota=100, sleep=lambda _: None)

    assert inserted == 1
    assert row_count(cursor) == 1


def test_uses_the_previous_page_search_after(cursor):
    session = FakeSession([
        FakeResponse(200, {"hits": {"hits": [hit("a", 1), hit("b", 42)]}}),
        FakeResponse(200, {"hits": {"hits": []}}),
    ])

    collect(session, cursor, URL, "tjsp", {}, quota=100, sleep=lambda _: None)

    assert "search_after" not in session.requests[0]
    assert session.requests[1]["search_after"] == [42]


def test_retries_on_a_429_and_then_succeeds(cursor):
    session = FakeSession([
        FakeResponse(429),
        FakeResponse(200, {"hits": {"hits": [hit("a", 1)]}}),
        FakeResponse(200, {"hits": {"hits": []}}),
    ])

    inserted = collect(session, cursor, URL, "tjsp", {}, quota=100, sleep=lambda _: None)

    assert inserted == 1


def test_retries_on_a_network_error_and_then_succeeds(cursor):
    session = FakeSession([
        requests.ConnectionError("connection reset"),
        FakeResponse(200, {"hits": {"hits": [hit("a", 1)]}}),
        FakeResponse(200, {"hits": {"hits": []}}),
    ])

    inserted = collect(session, cursor, URL, "tjsp", {}, quota=100, sleep=lambda _: None)

    assert inserted == 1
    assert row_count(cursor) == 1
