import json

from pipeline import load_file

FACTS_SQL = """
SELECT
    s.theme_sk,
    ts.judged,
    round(ts.upheld::numeric / ts.judged, 4) AS upheld_ratio,
    ts.claim_polarity_label AS polarity_label,
    s.court_count,
    s.period_start_year,
    s.period_end_year,
    s.last_decision_date,
    s.claim_upheld_count + s.claim_rejected_count AS merit_judged,
    round(
        s.claim_upheld_count::numeric / nullif(s.claim_upheld_count + s.claim_rejected_count, 0), 4
    ) AS merit_ratio,
    s.appeal_upheld_count + s.appeal_rejected_count AS appeal_judged,
    round(
        s.appeal_upheld_count::numeric / nullif(s.appeal_upheld_count + s.appeal_rejected_count, 0),
        4
    ) AS appeal_ratio,
    cfg.methodology_version,
    cfg.min_judged_for_percentage AS percentage_floor
FROM dw.theme_summary s
JOIN dw.theme_strength ts ON ts.theme_sk = s.theme_sk
CROSS JOIN dw.strength_config cfg
WHERE s.judged_case_count > 0 AND ts.judged > 0
ORDER BY s.theme_sk
"""

def _unit(n):
    return "decisão" if n == 1 else "decisões"


def _ratio(value, n):
    return {"ratio": float(value), "n": n, "unit": _unit(n)}


def _count(n):
    return {"count": n, "unit": _unit(n)}


def _judged(n):
    return "julgada" if n == 1 else "julgadas"


def _family(opening, count_opening, ratio, n, floor):
    if n < floor:
        return [{"text": count_opening}, _count(n), {"text": f" {_judged(n)}."}]
    return [{"text": opening}, _ratio(ratio, n), {"text": "."}]


def _courts_and_period(facts):
    courts = facts["court_count"]
    sentence = f"As decisões vêm de {courts} {'tribunal' if courts == 1 else 'tribunais'}"
    start, end = facts["period_start_year"], facts["period_end_year"]
    if start is None or end is None:
        return sentence + "."
    if start == end:
        return f"{sentence}, em {start}."
    return f"{sentence}, entre {start} e {end}."


def compose(facts):
    floor = facts["percentage_floor"]
    judged, label = facts["judged"], facts["polarity_label"]
    if judged < floor:
        lead = [{"text": "Há "}, _count(judged), {"text": f" {_judged(judged)}, com {label}."}]
    else:
        lead = [
            {"text": "Em "},
            _ratio(facts["upheld_ratio"], judged),
            {"text": f" julgadas, houve {label}."},
        ]
    body = [{"text": _courts_and_period(facts)}]
    last_decision = facts["last_decision_date"]
    if last_decision is not None:
        body.append({"text": f" A última decisão é de {last_decision:%d.%m.%Y}."})
    if facts["merit_judged"] > 0 and facts["appeal_judged"] > 0:
        body.extend(
            _family(
                " No mérito, houve acolhimento em ",
                " No mérito, há ",
                facts["merit_ratio"],
                facts["merit_judged"],
                floor,
            )
        )
        body.extend(
            _family(
                " Nos recursos, houve provimento em ",
                " Nos recursos, há ",
                facts["appeal_ratio"],
                facts["appeal_judged"],
                floor,
            )
        )
    return lead, body


def refresh_views(cursor):
    for view in load_file.matview_names(cursor):
        cursor.execute(f"REFRESH MATERIALIZED VIEW dw.{view}")


def fetch_facts(cursor):
    cursor.execute(FACTS_SQL)
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def generate(cursor, generated_at):
    refresh_views(cursor)
    rows = []
    for facts in fetch_facts(cursor):
        lead, body = compose(facts)
        rows.append(
            (
                facts["theme_sk"],
                json.dumps(lead, ensure_ascii=False),
                json.dumps(body, ensure_ascii=False),
                facts["methodology_version"],
                generated_at,
            )
        )
    cursor.execute("TRUNCATE dw.theme_narrative")
    cursor.executemany(
        "INSERT INTO dw.theme_narrative "
        "(theme_sk, lead, body, text_origin, methodology_version, generated_at) "
        "VALUES (%s, %s, %s, 'template', %s, %s)",
        rows,
    )
