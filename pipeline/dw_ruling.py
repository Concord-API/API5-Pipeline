from datetime import datetime

SOURCE = "stj_espelhos"
COURT = "STJ"
DATASET_PAGE = "https://dadosabertos.web.stj.jus.br/dataset/{dataset}"


def _text(payload, field):
    value = payload.get(field)
    return value if isinstance(value, str) and value.strip() else None


def judged_at(payload):
    value = _text(payload, "dataDecisao")
    try:
        return datetime.strptime(value, "%Y%m%d").date() if value else None
    except ValueError:
        return None


def case_number(payload):
    number = _text(payload, "numeroProcesso")
    if number is None:
        return None
    case_class = _text(payload, "siglaClasse")
    return f"{case_class.strip()} {number.strip()}" if case_class else number.strip()


def from_raw(dataset, collected_at, payload):
    summary = _text(payload, "ementa")
    if summary is None:
        return None
    return (
        SOURCE,
        payload["id"],
        case_number(payload),
        COURT,
        _text(payload, "nomeOrgaoJulgador"),
        judged_at(payload),
        summary,
        DATASET_PAGE.format(dataset=dataset),
        collected_at,
    )


def load(cursor):
    cursor.execute("SELECT dataset, collected_at, payload FROM raw.stj_ruling")
    rows = [from_raw(*row) for row in cursor.fetchall()]
    rows = [row for row in rows if row is not None]

    cursor.execute(
        "DELETE FROM dw.dim_ruling WHERE source = %s AND NOT (source_id = ANY(%s))",
        (SOURCE, [row[1] for row in rows]),
    )
    for row in rows:
        cursor.execute(
            """
            INSERT INTO dw.dim_ruling
                (source, source_id, case_number, court_code, judging_body, judged_at, summary,
                 source_url, extracted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, source_id) DO UPDATE
            SET case_number = EXCLUDED.case_number, court_code = EXCLUDED.court_code,
                judging_body = EXCLUDED.judging_body, judged_at = EXCLUDED.judged_at,
                summary = EXCLUDED.summary, source_url = EXCLUDED.source_url,
                extracted_at = EXCLUDED.extracted_at
            """,
            row,
        )
    return len(rows)

