from pipeline.tpu import penal_subject_codes


class IntegrityError(Exception):
    pass


SUMMARY_DIVERGING = """
WITH judged AS (
    SELECT bts.theme_sk, count(DISTINCT f.case_sk) AS n
    FROM dw.bridge_theme_subject bts
    JOIN dw.bridge_case_subject bcs ON bcs.subject_sk = bts.subject_sk
    JOIN dw.fact_case_event f ON f.case_sk = bcs.case_sk
    JOIN dw.dim_movement m ON m.movement_sk = f.movement_sk
    JOIN dw.dim_decision_outcome o ON o.outcome_sk = m.outcome_sk
    WHERE o.counts_in_metric AND m.code_verified
    GROUP BY bts.theme_sk
)
SELECT s.theme_sk
FROM dw.theme_summary s
LEFT JOIN judged j ON j.theme_sk = s.theme_sk
WHERE s.judged_case_count <> coalesce(j.n, 0)
"""

PROVENANCE_DIVERGING = """
SELECT coalesce(p.block, r.block), coalesce(p.source, r.source)
FROM dw.data_provenance p
FULL JOIN (
    SELECT 'cases'::text AS block, source, count(DISTINCT case_sk) AS n
    FROM dw.fact_case_event
    GROUP BY source
    UNION ALL
    SELECT 'doctrine'::text, source, count(*)
    FROM dw.dim_doctrine
    GROUP BY source
) r ON r.block = p.block AND r.source = p.source
WHERE p.row_count IS DISTINCT FROM r.n
"""


def checks(tpu):
    return [
        ("fact without date", "SELECT event_sk FROM dw.fact_case_event WHERE date_sk IS NULL", ()),
        (
            "penal subject",
            "SELECT subject_sk FROM dw.dim_subject WHERE subject_code = ANY(%s)",
            (penal_subject_codes(tpu),),
        ),
        (
            "theme without subject",
            "SELECT t.theme_sk FROM dw.dim_theme t WHERE NOT EXISTS "
            "(SELECT 1 FROM dw.bridge_theme_subject b WHERE b.theme_sk = t.theme_sk)",
            (),
        ),
        (
            "theme key outside the registry",
            "SELECT t.theme_sk FROM dw.dim_theme t LEFT JOIN etl.theme_registry r "
            "ON r.theme_key = t.theme_key AND r.theme_name = t.theme_name "
            "WHERE r.theme_key IS NULL",
            (),
        ),
        (
            "decision movement not verified",
            "SELECT m.movement_code FROM dw.dim_movement m "
            "JOIN dw.dim_decision_outcome o ON o.outcome_sk = m.outcome_sk "
            "WHERE o.counts_in_metric AND NOT m.code_verified",
            (),
        ),
        ("theme summary diverging from the facts", SUMMARY_DIVERGING, ()),
        ("provenance diverging from the facts", PROVENANCE_DIVERGING, ()),
        (
            "judged theme without text",
            "SELECT s.theme_sk FROM dw.theme_summary s WHERE s.judged_case_count > 0 "
            "AND NOT EXISTS (SELECT 1 FROM dw.theme_narrative n WHERE n.theme_sk = s.theme_sk)",
            (),
        ),
    ]


def violations(cursor, tpu):
    failed = []
    for name, sql, params in checks(tpu):
        cursor.execute(sql, params)
        if cursor.fetchone() is not None:
            failed.append(name)
    return failed


def assert_clean(cursor, tpu):
    failed = violations(cursor, tpu)
    if failed:
        raise IntegrityError(f"integrity check failed: {', '.join(failed)}")
