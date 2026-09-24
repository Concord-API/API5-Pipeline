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
    ("Dismissed", "Extinção sem julgamento de mérito", False),
]

VERIFIED_MOVEMENTS = [
    (219, "Procedência", "Granted", "pretensao_autor"),
    (220, "Improcedência", "Denied", "pretensao_autor"),
    (221, "Procedência em Parte", "PartiallyGranted", "pretensao_autor"),
    (237, "Provimento", "Granted", "pretensao_recorrente"),
    (238, "Provimento em Parte", "PartiallyGranted", "pretensao_recorrente"),
    (239, "Não-Provimento", "Denied", "pretensao_recorrente"),
]


def verified_movement_codes():
    return [code for code, *_ in VERIFIED_MOVEMENTS]


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


def seed_verified_movements(cursor):
    for code, name, outcome, polarity in VERIFIED_MOVEMENTS:
        cursor.execute(
            "INSERT INTO dw.dim_movement "
            "(movement_code, movement_name, outcome_sk, code_verified, polarity_reference) "
            "SELECT %s, %s, outcome_sk, true, %s "
            "FROM dw.dim_decision_outcome WHERE outcome_code = %s "
            "ON CONFLICT (movement_code) DO UPDATE SET "
            "outcome_sk = EXCLUDED.outcome_sk, code_verified = true, "
            "polarity_reference = EXCLUDED.polarity_reference",
            (code, name, polarity, outcome),
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
