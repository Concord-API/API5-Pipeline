import html
import re
from datetime import datetime
from urllib.parse import urlencode, urljoin

BASE_URL = "https://esaj.tjsp.jus.br"
FIRST_INSTANCE_LEVELS = ("First", "SpecialCourt")

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
