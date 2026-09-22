import json

from pipeline.tpu import penal_subject_codes


def load_subjects(cursor):
    cursor.execute("""
        INSERT INTO dw.dim_subject (subject_name, subject_code)
        SELECT DISTINCT ON (subj->>'nome')
               subj->>'nome', (subj->>'codigo')::int
        FROM staging.case_event se, jsonb_array_elements(se.subjects) subj
        WHERE subj->>'nome' IS NOT NULL AND subj->>'codigo' IS NOT NULL
        ORDER BY subj->>'nome', (subj->>'codigo')::int
        ON CONFLICT (subject_name) DO UPDATE SET
            subject_code = COALESCE(dw.dim_subject.subject_code, EXCLUDED.subject_code)
    """)


def set_tpu_areas(cursor, tpu):
    cursor.execute(
        "UPDATE dw.dim_subject SET tpu_area = (%s::jsonb) ->> (subject_code::text) "
        "WHERE subject_code IS NOT NULL",
        (json.dumps(tpu["assunto_area"]),),
    )


def assert_no_penal_subjects(cursor, tpu):
    cursor.execute(
        "SELECT subject_code FROM dw.dim_subject WHERE subject_code = ANY(%s)",
        (penal_subject_codes(tpu),),
    )
    codes = [row[0] for row in cursor.fetchall()]
    if codes:
        raise ValueError(f"Penal subjects reached dw.dim_subject: {codes}")


def load_bridge(cursor):
    cursor.execute("""
        INSERT INTO dw.bridge_case_subject (case_sk, subject_sk)
        SELECT DISTINCT dc.case_sk, dt.subject_sk
        FROM staging.case_event se
        JOIN dw.dim_case dc ON dc.case_number = se.case_number
        JOIN jsonb_array_elements(se.subjects) subj ON true
        JOIN dw.dim_subject dt ON dt.subject_name = subj->>'nome'
        ON CONFLICT DO NOTHING
    """)
