from collections import Counter

COLLECTED_SQL = """
SELECT dc.case_sk, r.status, r.source, r.source_url, r.collected_at, r.payload
FROM raw.court_site_case r
JOIN dw.dim_court c ON c.court_code = r.court
JOIN dw.dim_case dc ON dc.case_number = r.case_number AND dc.court_sk = c.court_sk
ORDER BY dc.case_sk
"""

DETAIL_SQL = """
INSERT INTO dw.case_site_detail
    (case_sk, status, case_class, subjects, judging_body, judge, filed_at, decision_date,
     decision_result, situation, source, source_url, extracted_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

STATUSES = ("found", "not_found", "sealed")


def _detail(case_sk, status, source, source_url, collected_at, payload):
    return (
        case_sk,
        status,
        payload.get("case_class"),
        payload.get("subjects") or [],
        payload.get("judging_body"),
        payload.get("judge"),
        payload.get("filed_at"),
        payload.get("decision_date"),
        payload.get("decision_result"),
        payload.get("situation"),
        source,
        source_url,
        collected_at,
    )


def load(cursor):
    cursor.execute(COLLECTED_SQL)
    collected = cursor.fetchall()
    counts = Counter({status: 0 for status in STATUSES})
    for case_sk, status, source, source_url, collected_at, payload in collected:
        cursor.execute("DELETE FROM dw.case_site_detail WHERE case_sk = %s", (case_sk,))
        cursor.execute(DETAIL_SQL, _detail(case_sk, status, source, source_url, collected_at, payload))
        counts[status] += 1
    return dict(counts)
