import hashlib
import json
import time
from pathlib import Path
from urllib.parse import quote, urlencode
from xml.etree import ElementTree as ET

import requests

NAMESPACES = {
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
    "dc": "http://purl.org/dc/elements/1.1/",
}
SOURCES_FILE = Path(__file__).parent / "data" / "oai_sources.json"
REQUEST_INTERVAL = 0.3


class OAIError(Exception):
    pass


def load_sources(path=SOURCES_FILE):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _get_xml(session, url, params, sleep):
    attempt = 0
    while True:
        sleep(REQUEST_INTERVAL)
        try:
            response = session.get(url, params=params, timeout=30)
        except requests.RequestException as error:
            if attempt == 3:
                raise OAIError(f"OAI-PMH request failed: {url}") from error
            sleep(2 * (attempt + 1))
            attempt += 1
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == 3:
                raise OAIError(f"OAI-PMH unavailable: {url}")
            sleep(2 * (attempt + 1))
            attempt += 1
            continue
        response.raise_for_status()
        return response.content


def _parse_record(element, url):
    header = element.find("oai:header", NAMESPACES)
    if header is None:
        raise OAIError(f"OAI-PMH record has no header: {url}")
    identifier = header.findtext("oai:identifier", namespaces=NAMESPACES)
    if not identifier:
        raise OAIError(f"OAI-PMH record has no identifier: {url}")
    if header.get("status") == "deleted":
        return None
    metadata = element.find("oai:metadata/oai_dc:dc", NAMESPACES)
    if metadata is None:
        raise OAIError(f"OAI-PMH record has no Dublin Core metadata: {identifier}")

    fields = {}
    for child in metadata:
        value = child.text.strip() if child.text else None
        if child.tag.startswith(f"{{{NAMESPACES['dc']}}}") and value:
            name = child.tag.split("}", 1)[1]
            fields.setdefault(name, []).append(value)

    def first(name):
        return next(iter(fields.get(name, [])), None)

    return {
        "oai_id": identifier,
        "datestamp": header.findtext("oai:datestamp", namespaces=NAMESPACES),
        "title": first("title"),
        "creators": fields.get("creator", []),
        "dates": fields.get("date", []),
        "identifiers": fields.get("identifier", []),
        "description": first("description"),
        "language": first("language"),
        "source": first("source"),
        "metadata": fields,
    }


def _parse_page(content, url, token):
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise OAIError(f"invalid OAI-PMH XML: {url}") from error
    if root.tag != f"{{{NAMESPACES['oai']}}}OAI-PMH":
        raise OAIError(f"invalid OAI-PMH response: {url}")
    error = root.find("oai:error", NAMESPACES)
    if error is not None:
        if error.get("code") == "noRecordsMatch" and token is None:
            return [], None
        raise OAIError(f"OAI-PMH error {error.get('code')}: {url}")
    listing = root.find("oai:ListRecords", NAMESPACES)
    if listing is None:
        raise OAIError(f"OAI-PMH ListRecords is missing: {url}")
    records = [
        parsed
        for element in listing.findall("oai:record", NAMESPACES)
        if (parsed := _parse_record(element, url)) is not None
    ]
    token = listing.findtext("oai:resumptionToken", namespaces=NAMESPACES)
    return records, token.strip() if token and token.strip() else None


def _source_url(source, record):
    identifiers = record["identifiers"]
    article_url = next(
        (value for value in identifiers if value.startswith(("http://", "https://"))), None,
    )
    if article_url:
        return article_url
    doi = next((value[4:].strip() for value in identifiers
                if value.lower().startswith("doi:")), None)
    if doi:
        return f"https://doi.org/{quote(doi, safe='/')}"
    query = urlencode({
        "verb": "GetRecord", "metadataPrefix": "oai_dc", "identifier": record["oai_id"],
    })
    return f"{source['oai_url']}?{query}"


def _insert(cursor, source, record):
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
    source_url = _source_url(source, record)
    identity = f"{source['oai_url']}\0{record['oai_id']}"
    cursor.execute(
        """
        INSERT INTO raw.doctrine_article (source, source_url, payload_hash, payload)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (source, payload_hash) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            collected_at = now(),
            payload = EXCLUDED.payload
        WHERE raw.doctrine_article.payload IS DISTINCT FROM EXCLUDED.payload
           OR raw.doctrine_article.source_url IS DISTINCT FROM EXCLUDED.source_url
        """,
        (source["source"], source_url, hashlib.sha256(identity.encode()).hexdigest(), payload),
    )
    return cursor.rowcount > 0


def _harvest_repository(session, cursor, source, sleep):
    seen_ids = set()
    seen_tokens = set()
    token = None
    found = 0
    changed = 0
    while True:
        params = {"verb": "ListRecords"}
        if token is None:
            params["metadataPrefix"] = "oai_dc"
        else:
            params["resumptionToken"] = token
        content = _get_xml(session, source["oai_url"], params, sleep)
        records, next_token = _parse_page(content, source["oai_url"], token)
        for record in records:
            if record["oai_id"] in seen_ids:
                raise OAIError(f"duplicate OAI-PMH identifier: {record['oai_id']}")
            seen_ids.add(record["oai_id"])
            found += 1
            changed += _insert(cursor, source, record)
        if not next_token:
            return found, changed
        if next_token in seen_tokens:
            raise OAIError(f"repeated OAI-PMH token: {source['name']}")
        seen_tokens.add(next_token)
        token = next_token


def collect(session, cursor, sources=None, repositories=None, sleep=time.sleep,
            on_repository=None):
    sources = load_sources() if sources is None else sources
    if repositories is not None:
        selected = set(repositories)
        unknown = selected - {source["name"] for source in sources}
        if unknown:
            raise OAIError(f"unknown repository: {', '.join(sorted(unknown))}")
        sources = [source for source in sources if source["name"] in selected]

    changed = 0
    for source in sources:
        if not source.get("enabled", True):
            if on_repository is not None:
                on_repository(source["name"], 0, 0, source["disabled_reason"])
            continue
        found, repository_changed = _harvest_repository(session, cursor, source, sleep)
        cursor.connection.commit()
        changed += repository_changed
        if on_repository is not None:
            on_repository(source["name"], found, repository_changed)
    return changed
