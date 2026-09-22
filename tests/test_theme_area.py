from pipeline.theme_area import classify_area


def test_an_exact_match_wins_over_any_keyword_rule():
    assert classify_area("Atraso de vôo") == "CONSUMIDOR"


def test_a_keyword_match_returns_the_right_area():
    assert classify_area("Execução Fiscal") == "TRIBUTARIO"
    assert classify_area("Aposentadoria por invalidez") == "PREVIDENCIARIO"


def test_a_name_matching_no_rule_returns_none():
    assert classify_area("Um Nome Que Não Existe Em Lugar Nenhum") is None


def test_the_first_matching_rule_wins():
    assert classify_area("Execução Fiscal") == "TRIBUTARIO"


def test_accents_and_case_do_not_matter():
    assert classify_area("execucao fiscal") == "TRIBUTARIO"
    assert classify_area("EXECUÇÃO FISCAL") == "TRIBUTARIO"
