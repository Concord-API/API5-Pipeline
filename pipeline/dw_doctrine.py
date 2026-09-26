import psycopg2.extras

from pipeline.doctrine_transform import extract

STAGE = """
    INSERT INTO staging.doctrine_article
        (raw_id, title, authors, journal_name, publication_year, doi, article_url,
         subject_area, source, extracted_at)
    VALUES %s
"""


ATTACH_DOI = """
    UPDATE dw.dim_doctrine d
    SET doi = s.doi
    FROM staging.doctrine_article s
    WHERE d.doi IS NULL
      AND s.doi IS NOT NULL
      AND d.source = s.source
      AND d.article_url = s.article_url
      AND NOT EXISTS (SELECT 1 FROM dw.dim_doctrine other WHERE other.doi = s.doi)
"""

UPSERT = """
    INSERT INTO dw.dim_doctrine
        (title, authors, journal_name, publication_year, doi, article_url, subject_area,
         source, extracted_at)
    SELECT title, authors, journal_name, publication_year, doi, article_url, subject_area,
           source, extracted_at
    FROM staging.doctrine_article
    WHERE doi IS {doi}
    ON CONFLICT {key} DO UPDATE SET
        title = EXCLUDED.title,
        authors = EXCLUDED.authors,
        journal_name = EXCLUDED.journal_name,
        publication_year = EXCLUDED.publication_year,
        article_url = EXCLUDED.article_url,
        subject_area = EXCLUDED.subject_area,
        source = EXCLUDED.source,
        extracted_at = EXCLUDED.extracted_at
"""


def read_raw(cursor):
    cursor.execute(
        "SELECT id, source, source_url, collected_at, payload FROM raw.doctrine_article "
        "ORDER BY collected_at DESC, id DESC"
    )
    return cursor.fetchall()


def unique_rows(raw_rows):
    seen_doi = set()
    seen_address = set()
    rows = []
    for raw_id, source, source_url, collected_at, payload in raw_rows:
        article = extract(source, source_url, payload)
        if article is None:
            continue
        address = (source, article["article_url"])
        if article["doi"] in seen_doi or address in seen_address:
            continue
        if article["doi"]:
            seen_doi.add(article["doi"])
        seen_address.add(address)
        rows.append((
            raw_id, article["title"], article["authors"], article["journal_name"],
            article["publication_year"], article["doi"], article["article_url"],
            article["subject_area"], source, collected_at,
        ))
    return rows


def transform(cursor):
    rows = unique_rows(read_raw(cursor))
    cursor.execute("TRUNCATE staging.doctrine_article")
    if rows:
        psycopg2.extras.execute_values(cursor, STAGE, rows)
    return len(rows)


def load(cursor):
    cursor.execute(ATTACH_DOI)
    cursor.execute(UPSERT.format(doi="NOT NULL", key="(doi)"))
    cursor.execute(UPSERT.format(doi="NULL", key="(source, article_url)"))
