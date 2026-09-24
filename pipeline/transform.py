import json
from datetime import datetime, timezone

from pipeline.tpu import civil_class_codes, penal_subject_codes

COURT_LEVEL_MAP = {
    "G1": "First",
    "G2": "Second",
    "JE": "SpecialCourt",
    "TR": "AppealPanel",
    "GRAU_UNICO": "Superior",
    "GR": "Second",
}


def map_court_level(grau):
    return COURT_LEVEL_MAP.get(grau, grau)


def parse_datetime(value):
    if not value:
        return None
    value = str(value)
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.isdigit() and len(value) >= 8:
            fmt = "%Y%m%d%H%M%S" if len(value) >= 14 else "%Y%m%d"
            return datetime.strptime(value[:14].ljust(14, "0"), fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return None


def flatten(raw_id, tribunal, source_url, collected_at, payload, tpu, movement_names=None):
    movement_names = movement_names or {}
    case_number = payload.get("numeroProcesso")
    if not case_number:
        return []

    classe = payload.get("classe") or {}
    subjects = [s for s in (payload.get("assuntos") or []) if isinstance(s, dict)]
    subject_codes = {s.get("codigo") for s in subjects if s.get("codigo") is not None}

    if subject_codes & set(penal_subject_codes(tpu)):
        return []
    if classe.get("codigo") is not None and classe.get("codigo") not in civil_class_codes(tpu):
        return []

    court_level = map_court_level(payload.get("grau"))
    orgao = payload.get("orgaoJulgador") or {}
    filed_at = parse_datetime(payload.get("dataAjuizamento"))
    secrecy = payload.get("nivelSigilo")

    rows = []
    for mov in payload.get("movimentos") or []:
        occurred_at = parse_datetime(mov.get("dataHora"))
        code = mov.get("codigo")
        if not occurred_at or code is None:
            continue
        name = mov.get("nome") or movement_names.get(str(code))
        if not name:
            continue
        orgao_code = orgao.get("codigo")
        rows.append((
            raw_id, tribunal, case_number, court_level,
            classe.get("codigo"), classe.get("nome"),
            str(orgao_code) if orgao_code is not None else None, orgao.get("nome"),
            filed_at, secrecy, json.dumps(subjects),
            code, name, occurred_at,
            "datajud", source_url, collected_at,
        ))
    return rows
