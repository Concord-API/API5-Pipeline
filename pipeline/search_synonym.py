import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "search_synonyms.json")


def load(path=DEFAULT_PATH):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
