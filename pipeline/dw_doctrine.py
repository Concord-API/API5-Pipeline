import psycopg2.extras

from pipeline.doctrine_transform import extract

STAGE = """
    INSERT INTO staging.doctrine_article
        (raw_id, title, authors, journal_name, publication_year, doi, article_url,
         subject_area, source, extracted_at)
    VALUES %s
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
