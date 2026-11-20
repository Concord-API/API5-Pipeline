import argparse
import sys
import time
from collections import Counter

import psycopg2
import requests
from psycopg2.extras import Json

from pipeline import config, esaj_tjsp
from pipeline.raw_schema import ensure

COURT = "TJSP"

PENDING_SQL = """
SELECT DISTINCT s.case_number, s.court_level
FROM dw.theme_case_sample s
WHERE s.court_code = %(court)s
  AND s.secrecy_level = 0
  AND length(s.case_number) = 20
  AND (%(refresh)s OR NOT EXISTS (
      SELECT 1 FROM raw.court_site_case r
      WHERE r.court = s.court_code AND r.case_number = s.case_number
  ))
ORDER BY s.case_number
LIMIT %(limit)s
"""

UPSERT_SQL = """
INSERT INTO raw.court_site_case
    (court, case_number, court_level, source, source_url, status, payload)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (court, case_number) DO UPDATE SET
    court_level = EXCLUDED.court_level,
    source = EXCLUDED.source,
    source_url = EXCLUDED.source_url,
    status = EXCLUDED.status,
    payload = EXCLUDED.payload,
    collected_at = now()
"""

STOPS = (
    esaj_tjsp.BlockedError,
    esaj_tjsp.SiteUnavailableError,
    esaj_tjsp.UnexpectedPageError,
    requests.HTTPError,
)


def pending_cases(cursor, refresh=False, limit=None):
    cursor.execute(PENDING_SQL, {"court": COURT, "refresh": refresh, "limit": limit})
    return cursor.fetchall()


def store(cursor, case_number, court_level, record):
    cursor.execute(
        UPSERT_SQL,
        (
            COURT,
            case_number,
            court_level,
            record["source"],
            record["source_url"],
            record["status"],
            Json(record["payload"]),
        ),
    )


def harvest(cursor, client, refresh=False, limit=None, commit=lambda: None, counts=None):
    counts = Counter() if counts is None else counts
    for case_number, court_level in pending_cases(cursor, refresh, limit):
        record = esaj_tjsp.fetch_case(client, case_number, court_level)
        store(cursor, case_number, court_level, record)
        commit()
        counts[record["status"]] += 1
    return counts


def summary(counts):
    return (
        f"{counts['found']} coletados, {counts['not_found']} não encontrados, "
        f"{counts['sealed']} em sigilo"
    )


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline.harvest_court_sites")
    parser.add_argument("--refresh", action="store_true", help="coleta de novo os já coletados")
    parser.add_argument("--limit", type=int, help="coleta no máximo este número de processos")
    return parser.parse_args(argv)


def main(argv=None, session_factory=esaj_tjsp.new_session, sleep=time.sleep):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config.load_env()
    try:
        dsn = config.database_url()
    except config.ConfigurationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    counts = Counter()
    client = esaj_tjsp.Client(session_factory(), sleep=sleep)
    try:
        connection = psycopg2.connect(dsn)
    except psycopg2.Error as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        with connection.cursor() as cursor:
            ensure(cursor)
            connection.commit()
            harvest(cursor, client, args.refresh, args.limit, connection.commit, counts)
    except STOPS as error:
        connection.rollback()
        print(
            f"error: {error}; {sum(counts.values())} coletados antes da parada "
            f"({summary(counts)}); rode de novo para continuar de onde parou",
            file=sys.stderr,
        )
        return 1
    except psycopg2.Error as error:
        connection.rollback()
        print(f"error: {error}", file=sys.stderr)
        return 1
    finally:
        connection.close()
    print(f"{COURT}: {summary(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
