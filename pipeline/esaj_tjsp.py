import html
import re
import time
from datetime import datetime
from urllib.parse import urlencode, urljoin

import requests

BASE_URL = "https://esaj.tjsp.jus.br"
FIRST_INSTANCE_LEVELS = ("First", "SpecialCourt")
USER_AGENT = "Ratio-DW/1.0 (FATEC API-5)"
DELAY_SECONDS = 2
RETRIES = 5
TIMEOUT_SECONDS = 60
MAX_MOVEMENT_PAGES = 500
MOVEMENT_PARAMETER = {"cpopg": "processo.codigo", "cposg": "cdProcesso"}
OPERATION_FAILED = "Não foi possível executar esta operação"

NOT_FOUND = "Não existem informações disponíveis para os parâmetros informados"
BLOCK_MARKERS = (
    "Verificação automática em andamento",
    "/cdn-cgi/challenge-platform",
    "g-recaptcha",
)
SEALED = re.compile(r"mostrar:\s*'true'\s*==\s*'true'")

FIELD_IDS = {
    "cpopg": {
        "case_class": "classeProcesso",
        "subject": "assuntoProcesso",
        "forum": "foroProcesso",
        "section": None,
        "judging_body": "varaProcesso",
        "judge": "juizProcesso",
        "filed_at": "dataHoraDistribuicaoProcesso",
        "situation": "labelSituacaoProcesso",
    },
    "cposg": {
        "case_class": "classeProcesso",
        "subject": "assuntoProcesso",
        "forum": None,
        "section": "secaoProcesso",
        "judging_body": "orgaoJulgadorProcesso",
        "judge": "relatorProcesso",
        "filed_at": None,
        "situation": "situacaoProcesso",
    },
}

CASE_CODE = {
    "cpopg": re.compile(r"codigoProcesso:\s*'([^']+)'"),
    "cposg": re.compile(r"var cdProcessoMovimentacoes\s*=\s*'([^']+)'"),
}

DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
TAG = re.compile(r"<[^>]+>")
SPACES = re.compile(r"\s+")
MOVEMENT = re.compile(
    r'<td[^>]*class="dataMovimentacao(?:Processo)?"[^>]*>(.*?)</td>'
    r'.*?<td[^>]*class="descricaoMovimentacao(?:Processo)?"[^>]*>(.*?)</td>',
    re.DOTALL,
)
COMPLEMENT = re.compile(r"<br\s*/?>|<span", re.IGNORECASE)
JUDGMENTS_HEADING = '<h2 class="subtitle">Julgamentos</h2>'
JUDGMENTS_END = re.compile(r"esajTabelaRodape|<h2", re.IGNORECASE)
JUDGMENT_ROW = re.compile(
    r"<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>",
    re.DOTALL,
)
CURSORS = (
    re.compile(r'id="cursorMovimentacoesPaginado"\s+value="([^"]+)"'),
    re.compile(r'\bdata-cursor="([^"]+)"'),
)
LISTED_CASE = re.compile(r'<a[^>]*class="linkProcesso"[^>]*href="([^"]+)"')
CASE_NUMBER = re.compile(r'id="numeroProcesso"[^>]*>(.*?)</span>', re.DOTALL)


class BlockedError(Exception):
    pass


class UnexpectedPageError(Exception):
    pass


class SiteUnavailableError(Exception):
    pass


def new_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


class Client:
    def __init__(self, session, sleep=time.sleep, delay=DELAY_SECONDS, retries=RETRIES):
        self.session = session
        self.sleep = sleep
        self.delay = delay
        self.retries = retries

    def get(self, url, params=None):
        for attempt in range(self.retries):
            self.sleep(self.delay)
            try:
                response = self.session.get(url, params=params, timeout=TIMEOUT_SECONDS)
            except requests.RequestException:
                self.sleep(min(30, 3 * (attempt + 1)))
                continue
            if response.status_code == 403:
                raise BlockedError("o e-SAJ recusou a requisição (403)")
            if response.status_code == 429 or response.status_code >= 500:
                self.sleep(min(30, 3 * (attempt + 1)))
                continue
            response.raise_for_status()
            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = "utf-8"
            text = response.text
            if any(marker in text for marker in BLOCK_MARKERS):
                raise BlockedError("o e-SAJ respondeu com uma verificação anti-robô")
            return text
        raise SiteUnavailableError(f"o e-SAJ não respondeu depois de {self.retries} tentativas")


def format_case_number(digits):
    return (
        f"{digits[0:7]}-{digits[7:9]}.{digits[9:13]}."
        f"{digits[13]}.{digits[14:16]}.{digits[16:20]}"
    )


def instance_for(court_level):
    return "cpopg" if court_level in FIRST_INSTANCE_LEVELS else "cposg"


def search_url(case_number, court_level):
    formatted = format_case_number(case_number)
    instance = instance_for(court_level)
    if instance == "cpopg":
        params = [
            ("conversationId", ""),
            ("cbPesquisa", "NUMPROC"),
            ("numeroDigitoAnoUnificado", formatted[:15]),
            ("foroNumeroUnificado", formatted[-4:]),
            ("dadosConsulta.valorConsultaNuUnificado", formatted),
            ("dadosConsulta.valorConsultaNuUnificado", "UNIFICADO"),
            ("dadosConsulta.valorConsulta", ""),
            ("dadosConsulta.tipoNuProcesso", "UNIFICADO"),
        ]
    else:
        params = [
            ("conversationId", ""),
            ("paginaConsulta", "0"),
            ("cbPesquisa", "NUMPROC"),
            ("numeroDigitoAnoUnificado", formatted[:15]),
            ("foroNumeroUnificado", formatted[-4:]),
            ("dePesquisaNuUnificado", formatted),
            ("dePesquisaNuUnificado", "UNIFICADO"),
            ("dePesquisa", ""),
            ("tipoNuProcesso", "UNIFICADO"),
        ]
    return f"{BASE_URL}/{instance}/search.do?{urlencode(params, safe='')}"


def _text(fragment):
    value = SPACES.sub(" ", html.unescape(TAG.sub(" ", fragment))).strip()
    return value or None


def _date(value):
    match = DATE.search(value or "")
    if match is None:
        return None
    day, month, year = match.groups()
    return datetime(int(year), int(month), int(day)).date().isoformat()


def _by_id(text, element_id):
    if element_id is None:
        return None
    match = re.search(
        rf'id="{element_id}"[^>]*>(.*?)</(?:span|div)>', text, re.DOTALL | re.IGNORECASE
    )
    return _text(match.group(1)) if match else None


def page_case_number(text):
    match = CASE_NUMBER.search(text)
    if match is None:
        return None
    digits = re.sub(r"\D", "", _text(match.group(1)) or "")
    return digits or None


def page_kind(text):
    if any(marker in text for marker in BLOCK_MARKERS):
        raise BlockedError("o e-SAJ respondeu com uma verificação anti-robô")
    if page_case_number(text):
        return "case"
    if NOT_FOUND in html.unescape(text):
        return "not_found"
    if SEALED.search(text):
        return "sealed"
    if LISTED_CASE.search(text):
        return "list"
    raise UnexpectedPageError("o e-SAJ devolveu uma página que a coleta não reconhece")


def _last_judgment(text):
    start = text.find(JUDGMENTS_HEADING)
    if start < 0:
        return None, None
    section = text[start:]
    end = JUDGMENTS_END.search(section, len(JUDGMENTS_HEADING))
    if end:
        section = section[: end.start()]
    judgments = [
        (_date(_text(day)), _text(result))
        for day, _situation, result in JUDGMENT_ROW.findall(section)
    ]
    judgments = [judgment for judgment in judgments if judgment[0] and judgment[1]]
    if not judgments:
        return None, None
    return max(judgments, key=lambda judgment: judgment[0])


def read_case(text, instance):
    ids = FIELD_IDS[instance]
    subject = _by_id(text, ids["subject"])
    decision_date, decision_result = _last_judgment(text)
    return {
        "case_class": _by_id(text, ids["case_class"]),
        "subjects": [subject] if subject else [],
        "forum": _by_id(text, ids["forum"]),
        "section": _by_id(text, ids["section"]),
        "judging_body": _by_id(text, ids["judging_body"]),
        "judge": _by_id(text, ids["judge"]),
        "filed_at": _date(_by_id(text, ids["filed_at"])),
        "situation": _by_id(text, ids["situation"]),
        "decision_date": decision_date,
        "decision_result": decision_result,
    }


def case_code(text, instance):
    match = CASE_CODE[instance].search(text)
    if match is None:
        raise UnexpectedPageError("a página do processo não traz o código das movimentações")
    return match.group(1)


def read_movements(text):
    movements = []
    for day, description in MOVEMENT.findall(text):
        title = _text(COMPLEMENT.split(description, maxsplit=1)[0])
        date = _date(_text(day))
        if date and title:
            movements.append({"date": date, "description": title})
    return movements


def next_cursor(text):
    for pattern in CURSORS:
        match = pattern.search(text)
        if match:
            return html.unescape(match.group(1))
    return None


def listed_cases(text):
    return [urljoin(BASE_URL, html.unescape(href)) for href in LISTED_CASE.findall(text)]


def fetch_movements(client, instance, code):
    url = f"{BASE_URL}/{instance}/carregarMovimentacoesAjax.do"
    movements = []
    cursor = None
    for _ in range(MAX_MOVEMENT_PAGES):
        params = {MOVEMENT_PARAMETER[instance]: code}
        if cursor:
            params["cursor"] = cursor
        text = client.get(url, params)
        if OPERATION_FAILED in html.unescape(text):
            raise UnexpectedPageError("o e-SAJ não carregou as movimentações do processo")
        page = read_movements(text)
        movements.extend(page)
        cursor = next_cursor(text)
        if not cursor or not page:
            return movements
    raise UnexpectedPageError("as movimentações do processo não terminaram")


def fetch_case(client, case_number, court_level):
    instance = instance_for(court_level)
    url = search_url(case_number, court_level)
    record = {"source": f"esaj_tjsp_{instance}", "source_url": url}
    text = client.get(url)
    kind = page_kind(text)
    listed = None
    if kind == "list":
        links = listed_cases(text)
        listed = len(links)
        text = client.get(links[0])
        kind = page_kind(text)
    if kind in ("not_found", "sealed"):
        return {**record, "status": kind, "payload": {}}
    if kind != "case" or page_case_number(text) != case_number:
        raise UnexpectedPageError("o e-SAJ devolveu a página de outro processo")
    payload = {
        "case_number": format_case_number(case_number),
        "instance": instance,
        **read_case(text, instance),
        "movements": fetch_movements(client, instance, case_code(text, instance)),
    }
    if listed:
        payload["listed_cases"] = listed
    return {**record, "status": "found", "payload": payload}
