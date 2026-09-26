import html
import re

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
YEAR = re.compile(r"\d{4}")


def clean(text):
    if text is None:
        return None
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_doi(value):
    if not value:
        return None
    doi = DOI_PREFIX.sub("", value.strip()).strip().lower()
    return doi if doi.startswith("10.") else None


def _year(value):
    match = YEAR.search(str(value)) if value is not None else None
    return int(match.group()) if match else None


def _join(values):
    return clean("; ".join(value for value in (clean(v) for v in values) if value))


def _row(title, authors, journal_name, publication_year, doi, article_url, subject_area=None):
    title = clean(title)
    if title is None:
        return None
    return {
        "title": title,
        "authors": authors,
        "journal_name": clean(journal_name),
        "publication_year": publication_year,
        "doi": doi,
        "article_url": article_url,
        "subject_area": subject_area,
    }


def _doaj(source_url, payload):
    bib = payload.get("bibjson") or {}
    doi = next(
        (normalize_doi(item.get("id")) for item in bib.get("identifier", [])
         if item.get("type") == "doi"),
        None,
    )
    fulltext = next(
        (link.get("url") for link in bib.get("link", [])
         if link.get("type") == "fulltext" and link.get("url")),
        None,
    )
    return _row(
        bib.get("title"),
        _join(author.get("name") for author in bib.get("author", [])),
        (bib.get("journal") or {}).get("title"),
        _year(bib.get("year")),
        doi,
        fulltext or source_url,
        _join(subject.get("term") for subject in bib.get("subject", [])),
    )


def _first_value(field):
    return next((item.get("_") for item in field or [] if item.get("_")), None)


def _scielo(source_url, payload):
    article = payload.get("article") or {}
    language = _first_value(article.get("v40"))
    titles = [item for item in article.get("v12") or [] if clean(item.get("_"))]
    title = next((item["_"] for item in titles if item.get("l") == language), None)
    if title is None and titles:
        title = titles[0]["_"]
    authors = _join(
        f"{author.get('n', '')} {author.get('s', '')}" for author in article.get("v10") or []
    )
    doi = normalize_doi(payload.get("doi")) or normalize_doi(_first_value(article.get("v237")))
    return _row(
        title,
        authors,
        _first_value((payload.get("title") or {}).get("v100")),
        _year(payload.get("publication_year")),
        doi,
        source_url,
    )


def _oai(source_url, payload):
    identifiers = payload.get("identifiers") or []
    doi = next((d for d in (normalize_doi(value) for value in identifiers) if d), None)
    page = next(
        (value for value in identifiers
         if value.startswith(("http://", "https://")) and normalize_doi(value) is None),
        None,
    )
    journal = payload.get("source")
    return _row(
        payload.get("title"),
        _join(payload.get("creators") or []),
        journal.split(";", 1)[0] if journal else None,
        next((year for year in (_year(value) for value in payload.get("dates") or []) if year),
             None),
        doi,
        page or source_url,
    )


def extract(source, source_url, payload):
    if source == "doaj":
        return _doaj(source_url, payload)
    if source == "scielo":
        return _scielo(source_url, payload)
    if source.startswith("oai_"):
        return _oai(source_url, payload)
    raise ValueError(f"unknown doctrine source: {source}")
