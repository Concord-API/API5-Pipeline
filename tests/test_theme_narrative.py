from datetime import date

from pipeline.theme_narrative import compose

FACTS = {
    "judged": 144,
    "upheld_ratio": 0.9861,
    "polarity_label": "acolhimento da pretensão do autor",
    "court_count": 3,
    "period_start_year": 2021,
    "period_end_year": 2026,
    "last_decision_date": date(2026, 8, 30),
    "merit_judged": 144,
    "merit_ratio": 0.9861,
    "appeal_judged": 0,
    "appeal_ratio": None,
}


def test_the_lead_opens_with_the_upheld_ratio_and_its_judged_count():
    lead, _ = compose(FACTS)

    assert lead == [
        {"text": "Em "},
        {"ratio": 0.9861, "n": 144, "unit": "decisões"},
        {"text": " julgadas, houve acolhimento da pretensão do autor."},
    ]


def test_the_body_states_courts_period_and_last_decision():
    _, body = compose(FACTS)

    assert body == [
        {"text": "As decisões vêm de 3 tribunais, entre 2021 e 2026."},
        {"text": " A última decisão é de 30.08.2026."},
    ]


def test_the_body_uses_a_single_court_and_a_single_year():
    facts = {**FACTS, "court_count": 1, "period_start_year": 2026}

    _, body = compose(facts)

    assert body[0] == {"text": "As decisões vêm de 1 tribunal, em 2026."}


def test_the_body_leaves_out_what_the_aggregates_do_not_have():
    facts = {
        **FACTS,
        "period_start_year": None,
        "period_end_year": None,
        "last_decision_date": None,
    }

    _, body = compose(facts)

    assert body == [{"text": "As decisões vêm de 3 tribunais."}]


def test_the_body_separates_merit_and_appeal_when_both_exist():
    facts = {**FACTS, "appeal_judged": 12, "appeal_ratio": 0.25}

    _, body = compose(facts)

    assert body[2:] == [
        {"text": " No mérito, houve acolhimento em "},
        {"ratio": 0.9861, "n": 144, "unit": "decisões"},
        {"text": ". Nos recursos, houve provimento em "},
        {"ratio": 0.25, "n": 12, "unit": "decisões"},
        {"text": "."},
    ]
