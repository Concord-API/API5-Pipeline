from pathlib import Path

import pytest

from pipeline import esaj_tjsp

FIXTURES = Path(__file__).parent / "fixtures" / "esaj"


def page(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_formats_the_twenty_digit_case_number():
    assert esaj_tjsp.format_case_number("10000012320248260100") == "1000001-23.2024.8.26.0100"


@pytest.mark.parametrize(
    ("court_level", "instance"),
    [("First", "cpopg"), ("SpecialCourt", "cpopg"), ("Second", "cposg"), ("AppealPanel", "cposg")],
)
def test_picks_the_instance_by_the_court_level(court_level, instance):
    assert esaj_tjsp.instance_for(court_level) == instance


def test_searches_the_first_instance_by_the_unified_number():
    url = esaj_tjsp.search_url("10000012320248260100", "First")

    assert url.startswith("https://esaj.tjsp.jus.br/cpopg/search.do?")
    assert "cbPesquisa=NUMPROC" in url
    assert "numeroDigitoAnoUnificado=1000001-23.2024" in url
    assert "foroNumeroUnificado=0100" in url
    assert "dadosConsulta.valorConsultaNuUnificado=1000001-23.2024.8.26.0100" in url


def test_searches_the_second_instance_by_the_unified_number():
    url = esaj_tjsp.search_url("10000012320248260100", "Second")

    assert url.startswith("https://esaj.tjsp.jus.br/cposg/search.do?")
    assert "dePesquisaNuUnificado=1000001-23.2024.8.26.0100" in url
    assert "foroNumeroUnificado=0100" in url


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("cpopg_show.html", "case"),
        ("cposg_show.html", "case"),
        ("not_found.html", "not_found"),
        ("sealed.html", "sealed"),
        ("list.html", "list"),
    ],
)
def test_tells_what_kind_of_page_came_back(name, kind):
    assert esaj_tjsp.page_kind(page(name)) == kind


def test_stops_on_an_anti_bot_challenge():
    with pytest.raises(esaj_tjsp.BlockedError):
        esaj_tjsp.page_kind(page("blocked.html"))


def test_stops_on_a_page_it_does_not_know():
    with pytest.raises(esaj_tjsp.UnexpectedPageError):
        esaj_tjsp.page_kind("<html><body><p>Manutenção programada</p></body></html>")


def test_reads_the_case_number_shown_on_the_page():
    assert esaj_tjsp.page_case_number(page("cpopg_show.html")) == "10000012320248260100"


def test_reads_every_field_of_a_first_instance_case():
    case = esaj_tjsp.read_case(page("cpopg_show.html"), "cpopg")

    assert case == {
        "case_class": "Procedimento Comum Cível",
        "subjects": ["Inclusão Indevida em Cadastro de Inadimplentes"],
        "forum": "Foro Central Cível",
        "section": None,
        "judging_body": "2ª Vara Cível",
        "judge": "MAGISTRADA FICTÍCIA DE TESTE",
        "filed_at": "2024-08-11",
        "situation": "Em andamento",
        "decision_date": None,
        "decision_result": None,
    }


def test_reads_every_field_of_a_second_instance_case():
    case = esaj_tjsp.read_case(page("cposg_show.html"), "cposg")

    assert case == {
        "case_class": "Apelação Cível",
        "subjects": [
            "DIREITO DO CONSUMIDOR - Responsabilidade do Fornecedor - Indenização por Dano Moral"
        ],
        "forum": None,
        "section": "Direito Privado 2",
        "judging_body": "15ª Câmara de Direito Privado",
        "judge": "RELATOR FICTÍCIO DE TESTE",
        "filed_at": None,
        "situation": "Encerrado",
        "decision_date": "2024-10-03",
        "decision_result": "Deram provimento ao recurso. V. U.",
    }


def test_leaves_empty_a_field_the_page_does_not_publish():
    judge = '<span id="juizProcesso" title="MAGISTRADA FICTÍCIA DE TESTE">'
    text = page("cpopg_show.html").replace(judge + "MAGISTRADA FICTÍCIA DE TESTE</span>", "")

    assert esaj_tjsp.read_case(text, "cpopg")["judge"] is None


def test_never_reads_the_parties_or_their_lawyers():
    for name, instance in (("cpopg_show.html", "cpopg"), ("cposg_show.html", "cposg")):
        values = str(esaj_tjsp.read_case(page(name), instance))

        assert "PARTE AUTORA" not in values
        assert "EMPRESA RÉ" not in values
        assert "ADVOGAD" not in values


def test_reads_the_code_that_loads_the_movements():
    assert esaj_tjsp.case_code(page("cpopg_show.html"), "cpopg") == "B00001AAA0000"
    assert esaj_tjsp.case_code(page("cposg_show.html"), "cposg") == "RI000AAA0000"


def test_reads_the_date_and_title_of_each_first_instance_movement():
    movements = esaj_tjsp.read_movements(page("cpopg_movements_1.html"))

    assert movements == [
        {"date": "2025-01-24", "description": "Arquivado Definitivamente"},
        {"date": "2025-01-23", "description": "Remetido ao DJE"},
        {"date": "2025-01-20", "description": "Julgada Procedente a Ação"},
    ]


def test_reads_the_date_and_title_of_each_second_instance_movement():
    movements = esaj_tjsp.read_movements(page("cposg_movements_1.html"))

    assert movements == [
        {"date": "2024-11-04", "description": "Expedido Certidão de Baixa de Recurso"},
        {"date": "2024-10-03", "description": "Expedido Termo"},
    ]


def test_drops_the_movement_complement_with_lawyers_and_parties():
    values = str(
        esaj_tjsp.read_movements(page("cpopg_movements_1.html"))
        + esaj_tjsp.read_movements(page("cposg_movements_1.html"))
    )

    assert "OAB" not in values
    assert "ADVOGAD" not in values
    assert "PARTE AUTORA" not in values
    assert "Teor do ato" not in values


@pytest.mark.parametrize(
    ("name", "cursor"),
    [
        ("cpopg_movements_1.html", "CURSOR-PAGINA-2"),
        ("cpopg_movements_2.html", "CURSOR-PAGINA-3"),
        ("cpopg_movements_3.html", None),
        ("cposg_movements_1.html", "CURSOR-SG-2"),
        ("cposg_movements_2.html", None),
    ],
)
def test_reads_the_cursor_of_the_next_movement_page(name, cursor):
    assert esaj_tjsp.next_cursor(page(name)) == cursor


def test_lists_the_cases_of_a_result_list_in_order():
    show = "https://esaj.tjsp.jus.br/cposg/show.do?processo.codigo="
    assert esaj_tjsp.listed_cases(page("list.html")) == [
        show + "RI000AAA0000&conversationId=&paginaConsulta=0",
        show + "RI000BBB0000&conversationId=&paginaConsulta=0",
    ]
