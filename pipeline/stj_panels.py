import json
import re
import unicodedata
from datetime import date
from functools import cache
from pathlib import Path

PANELS_PATH = Path(__file__).resolve().parent / "data" / "stj_panels.json"
ORDINALS = ("PRIMEIRA", "SEGUNDA", "TERCEIRA", "QUARTA", "QUINTA", "SEXTA")
NAMED_PANEL = re.compile(rf"\b({'|'.join(ORDINALS)}) (TURMA|SECAO)\b")


def load(path=PANELS_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


@cache
def default_panels():
    return load()


def repair(text):
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def normalize(text):
    plain = unicodedata.normalize("NFKD", repair(text)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z ]", " ", plain.upper())


def named_panel(normalized):
    if "CORTE ESPECIAL" in normalized:
        return "Corte Especial"
    match = NAMED_PANEL.search(normalized)
    if not match:
        return None
    ordinal, kind = match.groups()
    return f"{ordinal.capitalize()} {'Turma' if kind == 'TURMA' else 'Seção'}"


def minister_panel(normalized, decided_on, panels):
    words = set(normalized.split())
    for panel in panels["panels"]:
        for member in panel["members"]:
            if not set(member["name"].split()) <= words:
                continue
            joined = date.fromisoformat(member["since"])
            left = date.fromisoformat(member["until"]) if "until" in member else date.max
            if joined <= decided_on < left:
                return panel["panel"]
    return None


def panel_for(body_name, decided_at, panels=None):
    if not body_name:
        return None
    panels = panels or default_panels()
    normalized = normalize(body_name)
    return named_panel(normalized) or minister_panel(normalized, decided_at.date(), panels)
