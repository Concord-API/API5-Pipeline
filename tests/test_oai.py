import psycopg2
import pytest
import requests

from pipeline.oai import OAIError, collect, load_sources
from pipeline.raw_schema import ensure

FIRST_PAGE = b'''<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
 xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
 <ListRecords>
  <record><header><identifier>oai:example:article/1</identifier>
   <datestamp>2025-01-01</datestamp></header>
   <metadata><oai_dc:dc><dc:title>First article</dc:title>
    <dc:creator>Ana</dc:creator><dc:creator>Bruno</dc:creator>
    <dc:identifier>https://example.org/article/1</dc:identifier>
    <dc:subject>Direito civil</dc:subject></oai_dc:dc></metadata></record>
  <record><header status="deleted"><identifier>oai:example:article/old</identifier>
   <datestamp>2025-01-01</datestamp></header></record>
  <resumptionToken cursor="0">next-page</resumptionToken>
 </ListRecords>
</OAI-PMH>'''

SECOND_PAGE = b'''<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
 xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
 <ListRecords><record><header><identifier>oai:example:article/2</identifier>
 <datestamp>2025-01-02</datestamp></header><metadata><oai_dc:dc>
 <dc:title>Second article</dc:title><dc:identifier>doi:10.1/second</dc:identifier>
 </oai_dc:dc></metadata></record><resumptionToken></resumptionToken></ListRecords>
</OAI-PMH>'''


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, params, timeout):
        self.requests.append((url, dict(params), timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def cursor(postgres_url):
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cur:
        ensure(cur)
        cur.execute("TRUNCATE raw.doctrine_article")
        yield cur
        connection.commit()


@pytest.fixture
def source():
    return {
        "name": "example", "source": "oai_indexlaw",
        "oai_url": "https://example.org/oai", "journal_url": "https://example.org",
    }


def test_harvests_all_pages_and_preserves_metadata(cursor, source):
    session = FakeSession([FakeResponse(FIRST_PAGE), FakeResponse(SECOND_PAGE)])
    progress = []

    assert collect(session, cursor, sources=[source], sleep=lambda _: None,
                   on_repository=lambda *values: progress.append(values)) == 2
    assert session.requests[0][1] == {"verb": "ListRecords", "metadataPrefix": "oai_dc"}
    assert session.requests[1][1] == {"verb": "ListRecords", "resumptionToken": "next-page"}
    assert progress == [("example", 2, 2)]
    cursor.execute(
        "SELECT source, source_url, payload FROM raw.doctrine_article "
        "ORDER BY payload->>'oai_id'"
    )
    rows = cursor.fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "oai_indexlaw"
    assert rows[0][1] == "https://example.org/article/1"
    assert rows[0][2]["creators"] == ["Ana", "Bruno"]
    assert rows[0][2]["metadata"]["subject"] == ["Direito civil"]
    assert rows[1][1] == "https://example.org"


def test_rerun_updates_metadata_without_duplicating(cursor, source):
    session = FakeSession([FakeResponse(FIRST_PAGE), FakeResponse(SECOND_PAGE)])
    assert collect(session, cursor, sources=[source], sleep=lambda _: None) == 2

    updated = FIRST_PAGE.replace(b"First article", b"Updated article")
    session = FakeSession([FakeResponse(updated), FakeResponse(SECOND_PAGE)])
    assert collect(session, cursor, sources=[source], sleep=lambda _: None) == 1
    cursor.execute("SELECT count(*), max(payload->>'title') FROM raw.doctrine_article")
    assert cursor.fetchone()[0] == 2
    cursor.execute(
        "SELECT payload->>'title' FROM raw.doctrine_article "
        "WHERE payload->>'oai_id' = 'oai:example:article/1'"
    )
    assert cursor.fetchone()[0] == "Updated article"


def test_no_records_match_is_an_empty_repository(cursor, source):
    xml = (b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
           b'<error code="noRecordsMatch">empty</error></OAI-PMH>')
    session = FakeSession([FakeResponse(xml)])

    assert collect(session, cursor, sources=[source], sleep=lambda _: None) == 0


@pytest.mark.parametrize("response", [
    FakeResponse(b"<broken"),
    FakeResponse(b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
                 b'<error code="badResumptionToken">expired</error></OAI-PMH>'),
])
def test_rejects_invalid_or_error_responses(cursor, source, response):
    session = FakeSession([response])

    with pytest.raises(OAIError):
        collect(session, cursor, sources=[source], sleep=lambda _: None)


def test_rejects_a_repeated_resumption_token(cursor, source):
    session = FakeSession([FakeResponse(FIRST_PAGE), FakeResponse(FIRST_PAGE)])

    with pytest.raises(OAIError, match="token"):
        collect(session, cursor, sources=[source], sleep=lambda _: None)


def test_retries_temporary_failure(cursor, source):
    empty = (b'<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">'
             b'<error code="noRecordsMatch"/></OAI-PMH>')
    session = FakeSession([requests.ConnectionError("reset"), FakeResponse(empty)])

    assert collect(session, cursor, sources=[source], sleep=lambda _: None) == 0
    assert len(session.requests) == 2


def test_rejects_unknown_repository(cursor):
    session = FakeSession([])

    with pytest.raises(OAIError, match="unknown repository"):
        collect(session, cursor, repositories=["missing"], sleep=lambda _: None)
    assert session.requests == []


def test_loads_curated_repositories():
    sources = load_sources()
    assert len(sources) == 48
    assert {source["name"] for source in sources} >= {"emerj", "ejef", "direitocivil"}
