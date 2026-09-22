import psycopg2.extras

INSERT = """
    INSERT INTO staging.case_event
        (raw_id, tribunal, case_number, court_level, case_class_code, case_class_name,
         judging_body_code, judging_body_name, filed_at, secrecy_level, subjects,
         movement_code, movement_name, occurred_at, source, source_url, extracted_at)
    VALUES %s
"""


def load(cursor, rows):
    cursor.execute("TRUNCATE staging.case_event")
    if rows:
        psycopg2.extras.execute_values(cursor, INSERT, rows)
