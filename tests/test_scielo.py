import psycopg2
import pytest
import requests

from pipeline.raw_schema import ensure
from pipeline.scielo import SciELOError, collect


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
    def __init__(self, articles):
        self.articles = articles
        self.requests = []
        self.responses = []

    def get(self, url, params, timeout):
        self.requests.append((url, dict(params)))
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        if url.endswith("/identifiers/"):
            codes = list(self.articles)
            offset = params["offset"]
            limit = params["limit"]
            return FakeResponse(200, {
                "meta": {"total": len(codes)},
                "objects": [{"code": code} for code in codes[offset:offset + limit]],
            })
        return FakeResponse(200, self.articles[params["code"]])


def article(code, title=None):
    return {
        "code": code,
        "collection": "scl",
        "article": {"v12": [{"_": title or f"Article {code}"}]},
        "fulltexts": [{"language": "pt", "url": f"https://www.scielo.br/{code}"}],
    }


@pytest.fixture
def cursor(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cur:
        ensure(cur)
        cur.execute("TRUNCATE raw.doctrine_article")
        yield cur
        connection.commit()


def test_collects_all_identifier_pages_and_preserves_full_response(cursor, monkeypatch):
    monkeypatch.setattr("pipeline.scielo.PAGE_SIZE", 2)
    session = FakeSession({str(i): article(str(i)) for i in range(3)})

    assert collect(session, cursor, issns=("1806-6445",), sleep=lambda _: None) == 3

    offsets = [params["offset"] for url, params in session.requests if url.endswith("/identifiers/")]
    assert offsets == [0, 2]
    cursor.execute("SELECT source, source_url, payload FROM raw.doctrine_article ORDER BY payload->>'code'")
    rows = cursor.fetchall()
    assert len(rows) == 3
    assert rows[0][0] == "scielo"
    assert rows[0][1] == "https://www.scielo.br/scielo.php?script=sci_arttext&pid=0"
    assert rows[0][2]["fulltexts"][0]["language"] == "pt"
    assert collect(session, cursor, issns=("1806-6445",), sleep=lambda _: None) == 0


def test_updates_an_article_without_duplicating_its_code(cursor):
    record = article("abc")
    session = FakeSession({"abc": record})
    assert collect(session, cursor, issns=("1806-6445",), sleep=lambda _: None) == 1

    record["article"]["v12"][0]["_"] = "Updated title"
    assert collect(session, cursor, issns=("1806-6445",), sleep=lambda _: None) == 1

    cursor.execute("SELECT count(*), max(payload->'article'->'v12'->0->>'_') FROM raw.doctrine_article")
    assert cursor.fetchone() == (1, "Updated title")


def test_rejects_an_incomplete_identifier_page(cursor, monkeypatch):
    monkeypatch.setattr("pipeline.scielo.PAGE_SIZE", 2)
    session = FakeSession({})
    session.responses = [
        FakeResponse(200, {"meta": {"total": 3}, "objects": [{"code": "a"}, {"code": "b"}]}),
        FakeResponse(200, {"meta": {"total": 3}, "objects": []}),
    ]

    with pytest.raises(SciELOError, match="incomplete"):
        collect(session, cursor, issns=("1806-6445",), sleep=lambda _: None)


def test_retries_temporary_http_errors(cursor):
    session = FakeSession({"abc": article("abc")})
    session.responses = [requests.ConnectionError("reset"), FakeResponse(429)]

    assert collect(session, cursor, issns=("1806-6445",), sleep=lambda _: None) == 1
    assert len(session.requests) == 4


def test_rejects_an_article_with_the_wrong_code(cursor):
    session = FakeSession({"abc": article("other")})

    with pytest.raises(SciELOError, match="code"):
        collect(session, cursor, issns=("1806-6445",), sleep=lambda _: None)
