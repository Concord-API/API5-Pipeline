def _ratio(value, n):
    return {"ratio": float(value), "n": n, "unit": "decisão" if n == 1 else "decisões"}


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
    lead = [
        {"text": "Em "},
        _ratio(facts["upheld_ratio"], facts["judged"]),
        {"text": f" julgadas, houve {facts['polarity_label']}."},
    ]
    body = [{"text": _courts_and_period(facts)}]
    last_decision = facts["last_decision_date"]
    if last_decision is not None:
        body.append({"text": f" A última decisão é de {last_decision:%d.%m.%Y}."})
    if facts["merit_judged"] > 0 and facts["appeal_judged"] > 0:
        body.extend(
            [
                {"text": " No mérito, houve acolhimento em "},
                _ratio(facts["merit_ratio"], facts["merit_judged"]),
                {"text": ". Nos recursos, houve provimento em "},
                _ratio(facts["appeal_ratio"], facts["appeal_judged"]),
                {"text": "."},
            ]
        )
    return lead, body
