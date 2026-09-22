import json
import os
import unicodedata

RULES_PATH = os.path.join(os.path.dirname(__file__), "data", "theme_area_rules.json")


def _strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


def _load_rules():
    with open(RULES_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    exact = {name.strip(): area for name, area in data["exact_area"].items()}
    return data["area_rules"], exact


AREA_RULES, EXACT_AREA = _load_rules()


def classify_area(name):
    stripped = name.strip()
    if stripped in EXACT_AREA:
        return EXACT_AREA[stripped]
    normalized = _strip_accents(name)
    for area, keywords in AREA_RULES:
        for keyword in keywords:
            if keyword in normalized:
                return area
    return None
