import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "tpu.json")


def load(path: str = DEFAULT_PATH) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def civil_class_codes(tpu: dict) -> list[int]:
    return tpu["classes_civel"]["codigos"]


def penal_subject_codes(tpu: dict) -> list[int]:
    return tpu["assuntos_penal"]["codigos"]


def area(tpu: dict, area_code: str) -> dict:
    try:
        return tpu["areas"][area_code]
    except KeyError:
        raise KeyError(f"Area code {area_code} is not in the TPU areas") from None


def datajud_civil_query(tpu: dict, area_code: str, decision_codes: list[int]) -> dict:
    subjects = area(tpu, area_code)["codigos"]
    return {
        "bool": {
            "filter": [
                {"terms": {"classe.codigo": civil_class_codes(tpu)}},
                {"terms": {"assuntos.codigo": subjects}},
                {"terms": {"movimentos.codigo": decision_codes}},
            ],
            "must_not": [
                {"terms": {"assuntos.codigo": penal_subject_codes(tpu)}},
            ],
        }
    }
