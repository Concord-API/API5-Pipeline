def load(cursor):
    cursor.execute("""
        INSERT INTO dw.fact_case_event
            (case_sk, court_sk, judging_body_sk, movement_sk, date_sk,
             occurred_at, source, source_url, extracted_at, natural_key)
        SELECT
            dc.case_sk, c.court_sk, jb.judging_body_sk, dm.movement_sk,
            dd.date_sk,
            se.occurred_at, se.source, se.source_url, se.extracted_at,
            se.case_number || '|' || se.movement_code || '|' || se.occurred_at::text
        FROM staging.case_event se
        JOIN dw.dim_case dc ON dc.case_number = se.case_number
        JOIN dw.dim_court c ON c.court_code = upper(se.tribunal)
        JOIN dw.dim_movement dm ON dm.movement_code = se.movement_code
        LEFT JOIN dw.dim_judging_body jb
            ON jb.court_sk = c.court_sk AND jb.body_name = se.judging_body_name
        LEFT JOIN dw.dim_date dd ON dd.full_date = se.occurred_at::date
        ON CONFLICT (natural_key) DO NOTHING
    """)
