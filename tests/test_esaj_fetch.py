from pathlib import Path

import pytest
import requests

from pipeline import esaj_tjsp

FIXTURES = Path(__file__).parent / "fixtures" / "esaj"
CASE = "10000012320248260100"


def page(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status_code=200, text="", encoding="utf-8"):
        self.status_code = status_code
        self.text = text
        self.encoding = encoding

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class FakeSession:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def ok(name):
    return FakeResponse(text=page(name))


def client(answers, sleeps=None):
    session = FakeSession(answers)
    pauses = [] if sleeps is None else sleeps
    return esaj_tjsp.Client(session, sleep=pauses.append), session, pauses


def test_fetches_a_first_instance_case_with_every_movement_page():
    esaj, session, _ = client(
        [
            ok("cpopg_show.html"),
            ok("cpopg_movements_1.html"),
            ok("cpopg_movements_2.html"),
            ok("cpopg_movements_3.html"),
        ]
    )

    record = esaj_tjsp.fetch_case(esaj, CASE, "First")

    assert record["status"] == "found"
    assert record["source"] == "esaj_tjsp_cpopg"
    assert record["source_url"] == esaj_tjsp.search_url(CASE, "First")
    payload = record["payload"]
    assert payload["case_number"] == "1000001-23.2024.8.26.0100"
    assert payload["instance"] == "cpopg"
    assert payload["judging_body"] == "2ª Vara Cível"
    assert [movement["date"] for movement in payload["movements"]] == [
        "2025-01-24",
        "2025-01-23",
        "2025-01-20",
        "2024-09-15",
        "2024-08-11",
    ]


def test_asks_each_movement_page_with_the_cursor_of_the_previous_one():
    esaj, session, _ = client(
        [
            ok("cpopg_show.html"),
            ok("cpopg_movements_1.html"),
            ok("cpopg_movements_2.html"),
            ok("cpopg_movements_3.html"),
        ]
    )

    esaj_tjsp.fetch_case(esaj, CASE, "First")

    movement_calls = session.calls[1:]
    assert all(
        url == "https://esaj.tjsp.jus.br/cpopg/carregarMovimentacoesAjax.do"
        for url, _ in movement_calls
    )
    assert [params for _, params in movement_calls] == [
        {"processo.codigo": "B00001AAA0000"},
        {"processo.codigo": "B00001AAA0000", "cursor": "CURSOR-PAGINA-2"},
        {"processo.codigo": "B00001AAA0000", "cursor": "CURSOR-PAGINA-3"},
    ]


def test_fetches_a_second_instance_case_with_its_last_judgment():
    esaj, session, _ = client(
        [ok("cposg_show.html"), ok("cposg_movements_1.html"), ok("cposg_movements_2.html")]
    )

    record = esaj_tjsp.fetch_case(esaj, CASE, "Second")

    assert record["source"] == "esaj_tjsp_cposg"
    assert record["payload"]["judge"] == "RELATOR FICTÍCIO DE TESTE"
    assert record["payload"]["decision_result"] == "Deram provimento ao recurso. V. U."
    assert len(record["payload"]["movements"]) == 3
    assert session.calls[1] == (
        "https://esaj.tjsp.jus.br/cposg/carregarMovimentacoesAjax.do",
        {"cdProcesso": "RI000AAA0000"},
    )
    assert session.calls[2][1] == {"cdProcesso": "RI000AAA0000", "cursor": "CURSOR-SG-2"}


def test_follows_the_first_case_of_a_result_list_and_says_how_many_came():
    esaj, session, _ = client(
        [
            ok("list.html"),
            ok("cposg_show.html"),
            ok("cposg_movements_1.html"),
            ok("cposg_movements_2.html"),
        ]
    )

    record = esaj_tjsp.fetch_case(esaj, CASE, "Second")

    assert session.calls[1][0] == (
        "https://esaj.tjsp.jus.br/cposg/show.do?processo.codigo=RI000AAA0000"
        "&conversationId=&paginaConsulta=0"
    )
    assert record["status"] == "found"
    assert record["payload"]["listed_cases"] == 2


@pytest.mark.parametrize(
    ("name", "status"), [("not_found.html", "not_found"), ("sealed.html", "sealed")]
)
def test_records_a_case_without_data_and_asks_nothing_else(name, status):
    esaj, session, _ = client([ok(name)])

    record = esaj_tjsp.fetch_case(esaj, CASE, "First")

    assert record["status"] == status
    assert record["payload"] == {}
    assert len(session.calls) == 1


def test_refuses_a_page_of_another_case():
    other = page("cpopg_show.html").replace("1000001-23.2024", "1000009-99.2024")
    esaj, _, _ = client([FakeResponse(text=other)])

    with pytest.raises(esaj_tjsp.UnexpectedPageError):
        esaj_tjsp.fetch_case(esaj, CASE, "First")


def test_stops_when_the_movements_cannot_be_loaded():
    failure = "<li>Não foi possível executar esta operação. Tente novamente mais tarde.</li>"
    esaj, _, _ = client([ok("cpopg_show.html"), FakeResponse(text=failure)])

    with pytest.raises(esaj_tjsp.UnexpectedPageError):
        esaj_tjsp.fetch_case(esaj, CASE, "First")


def test_waits_before_every_request():
    esaj, _, pauses = client([ok("not_found.html")])

    esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")

    assert pauses == [esaj_tjsp.DELAY_SECONDS]


def test_retries_while_the_site_is_down():
    esaj, session, _ = client([FakeResponse(503), FakeResponse(429), ok("not_found.html")])

    assert esaj_tjsp.NOT_FOUND in esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")
    assert len(session.calls) == 3


def test_retries_after_a_connection_error():
    esaj, session, _ = client([requests.ConnectionError("reset"), ok("not_found.html")])

    esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")

    assert len(session.calls) == 2


def test_gives_up_when_the_site_never_answers():
    esaj, session, _ = client([FakeResponse(503)] * esaj_tjsp.RETRIES)

    with pytest.raises(esaj_tjsp.SiteUnavailableError):
        esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")
    assert len(session.calls) == esaj_tjsp.RETRIES


def test_stops_at_once_when_the_site_forbids_the_request():
    esaj, session, _ = client([FakeResponse(403)])

    with pytest.raises(esaj_tjsp.BlockedError):
        esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")
    assert len(session.calls) == 1


def test_stops_on_an_anti_bot_challenge_answered_with_200():
    esaj, _, _ = client([ok("blocked.html")])

    with pytest.raises(esaj_tjsp.BlockedError):
        esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")


def test_reports_a_client_error_at_once():
    esaj, session, _ = client([FakeResponse(404)])

    with pytest.raises(requests.HTTPError):
        esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")
    assert len(session.calls) == 1


def test_reads_the_page_as_utf8_when_the_server_does_not_say():
    response = FakeResponse(text=page("not_found.html"), encoding="ISO-8859-1")
    esaj, _, _ = client([response])

    esaj.get("https://esaj.tjsp.jus.br/cpopg/search.do")

    assert response.encoding == "utf-8"


def test_identifies_itself_to_the_site():
    session = esaj_tjsp.new_session()

    assert session.headers["User-Agent"] == "Ratio-DW/1.0 (FATEC API-5)"
