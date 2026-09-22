import json
import os

from pipeline.theme_area import classify_area

DEFAULT_GROUPS_PATH = os.path.join(os.path.dirname(__file__), "data", "theme_merge_groups.json")


def load_groups(path=DEFAULT_GROUPS_PATH):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def build(subjects, groups):
    name_to_sk = dict(subjects)
    consumed = set()
    themes = []

    for group in groups:
        sks = [name_to_sk[name] for name in group["aliases"] if name in name_to_sk]
        consumed.update(name for name in group["aliases"] if name in name_to_sk)
        if sks:
            themes.append({
                "theme_name": group["theme_name"],
                "subject_area": group["subject_area"],
                "subject_sks": sks,
            })

    for name, sk in subjects:
        if name in consumed:
            continue
        clean = name.strip()
        themes.append({
            "theme_name": clean,
            "subject_area": classify_area(clean),
            "subject_sks": [sk],
        })

    seen = {}
    for theme in themes:
        base = theme["theme_name"]
        if base in seen:
            seen[base] += 1
            theme["theme_name"] = f"{base} ({seen[base]})"
        else:
            seen[base] = 1

    return themes
