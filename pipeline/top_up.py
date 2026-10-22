from pipeline.datajud import collect as datajud_collect
from pipeline.dw_reference import verified_movement_codes
from pipeline.harvest import TRIBUNALS, datajud_url
from pipeline.tpu import class_codes, datajud_subjects_query

THRESHOLD = 5
TOP_UP_QUOTA = 300


def thin_subject_codes(cursor, threshold=THRESHOLD):
    cursor.execute(
        """
        SELECT DISTINCT s.subject_code
        FROM dw.theme_summary ts
        JOIN dw.bridge_theme_subject b ON b.theme_sk = ts.theme_sk
        JOIN dw.dim_subject s ON s.subject_sk = b.subject_sk
        WHERE ts.judged_case_count < %s AND s.subject_code IS NOT NULL
        ORDER BY s.subject_code
        """,
        (threshold,),
    )
    return [row[0] for row in cursor.fetchall()]


def themes_with_at_least(cursor, threshold=THRESHOLD):
    cursor.execute(
        "SELECT count(*) FROM dw.theme_summary WHERE judged_case_count >= %s", (threshold,)
    )
    return cursor.fetchone()[0]


def harvest(
    session, cursor, tpu, subjects, tribunals=TRIBUNALS, quota=TOP_UP_QUOTA,
    collect=datajud_collect,
) -> int:
    if not subjects:
        return 0
    total = 0
    for tribunal in tribunals:
        query = datajud_subjects_query(
            tpu, subjects, verified_movement_codes(), class_codes(tpu, tribunal)
        )
        total += collect(session, cursor, datajud_url(tribunal), tribunal, query, quota)
        cursor.connection.commit()
    return total
