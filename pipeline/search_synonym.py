import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "search_synonyms.json")


def load(path=DEFAULT_PATH):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def seed(cursor, entries):
    cursor.execute("TRUNCATE dw.search_synonym")
    cursor.executemany(
        "INSERT INTO dw.search_synonym (term, expands_to, note) VALUES (%s, %s, %s)",
        [(entry["term"], entry["expands_to"], entry["note"]) for entry in entries],
    )
