def load(cursor):
    cursor.execute("""
        INSERT INTO dw.dim_case
            (case_number, court_sk, case_class_sk, court_level, secrecy_level, filed_at,
             source, extracted_at)
        SELECT DISTINCT ON (se.case_number)
            se.case_number, c.court_sk, cc.case_class_sk, se.court_level, se.secrecy_level,
            se.filed_at::date, se.source, se.extracted_at
        FROM staging.case_event se
        JOIN dw.dim_court c ON c.court_code = upper(se.tribunal)
        LEFT JOIN dw.dim_case_class cc ON cc.class_name = se.case_class_name
        ORDER BY se.case_number, se.extracted_at DESC
        ON CONFLICT (case_number) DO UPDATE SET
            court_level = EXCLUDED.court_level,
            extracted_at = EXCLUDED.extracted_at
    """)
