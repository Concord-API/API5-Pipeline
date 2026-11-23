import json
import os
import unicodedata

from pipeline.theme_area import classify_area

DEFAULT_GROUPS_PATH = os.path.join(os.path.dirname(__file__), "data", "theme_merge_groups.json")


def load_groups(path=DEFAULT_GROUPS_PATH):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def same_name(name):
    folded = unicodedata.normalize("NFD", " ".join(name.split()).casefold())
    return "".join(char for char in folded if unicodedata.category(char) != "Mn")


def build(subjects, groups):
    by_name = {}
    for name, sk in subjects:
        clean = name.strip()
        entry = by_name.setdefault(same_name(clean), {"name": clean, "sks": []})
        entry["sks"].append(sk)

    themes = {}
    for group in groups:
        sks = []
        for alias in group["aliases"]:
            entry = by_name.pop(same_name(alias), None)
            if entry is not None:
                sks.extend(entry["sks"])
        if sks:
            themes[same_name(group["theme_name"])] = {
                "theme_name": group["theme_name"],
                "subject_area": group["subject_area"],
                "subject_sks": sks,
            }

    for key, entry in by_name.items():
        if key in themes:
            themes[key]["subject_sks"].extend(entry["sks"])
            continue
        themes[key] = {
            "theme_name": entry["name"],
            "subject_area": classify_area(entry["name"]),
            "subject_sks": entry["sks"],
        }

    return list(themes.values())
