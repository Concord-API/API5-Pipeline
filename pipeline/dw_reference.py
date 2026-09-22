COURTS = [
    ("TJSP", "Tribunal de Justiça de São Paulo", "SP"),
    ("TJRJ", "Tribunal de Justiça do Rio de Janeiro", "RJ"),
    ("TJMG", "Tribunal de Justiça de Minas Gerais", "MG"),
]

OUTCOMES = [
    ("Granted", "Procedente", True),
    ("PartiallyGranted", "Parcialmente procedente", True),
    ("Denied", "Improcedente", True),
    ("Neutral", "Sem resultado conferido", False),
]


def seed_courts(cursor):
    for code, name, uf in COURTS:
        cursor.execute(
            "INSERT INTO dw.dim_court (court_code, court_name, state_uf) VALUES (%s, %s, %s) "
            "ON CONFLICT (court_code) DO NOTHING",
            (code, name, uf),
        )


def seed_outcomes(cursor):
    for code, label, counts in OUTCOMES:
        cursor.execute(
            "INSERT INTO dw.dim_decision_outcome (outcome_code, outcome_label, counts_in_metric) "
            "VALUES (%s, %s, %s) ON CONFLICT (outcome_code) DO NOTHING",
            (code, label, counts),
        )


def load_case_classes(cursor):
    cursor.execute("""
        INSERT INTO dw.dim_case_class (class_name)
        SELECT DISTINCT case_class_name FROM staging.case_event
        WHERE case_class_name IS NOT NULL
        ON CONFLICT (class_name) DO NOTHING
    """)


def load_judging_bodies(cursor):
    cursor.execute("""
        INSERT INTO dw.dim_judging_body (court_sk, body_name)
        SELECT DISTINCT c.court_sk, se.judging_body_name
        FROM staging.case_event se
        JOIN dw.dim_court c ON c.court_code = upper(se.tribunal)
        WHERE se.judging_body_name IS NOT NULL
        ON CONFLICT (court_sk, body_name) DO NOTHING
    """)


def load_movements(cursor):
    cursor.execute("""
        INSERT INTO dw.dim_movement (movement_code, movement_name, outcome_sk, code_verified)
        SELECT DISTINCT ON (movement_code) movement_code, movement_name,
               (SELECT outcome_sk FROM dw.dim_decision_outcome WHERE outcome_code = 'Neutral'),
               false
        FROM staging.case_event
        ON CONFLICT (movement_code) DO NOTHING
    """)
