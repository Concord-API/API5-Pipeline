import re

from pipeline.search_synonym import load

SINGLE_NORMALIZED_WORD = re.compile(r"^[a-z0-9]+$")
NORMALIZED_WORDS = re.compile(r"^[a-z0-9]+( [a-z0-9]+)*$")


def test_starts_from_the_discovery_synonyms():
    terms = {entry["term"] for entry in load()}

    assert {"negativacao", "negativado", "serasa", "spc"} <= terms


def test_every_term_is_a_single_lowercase_word_without_accents():
    assert [
        entry["term"] for entry in load() if not SINGLE_NORMALIZED_WORD.match(entry["term"])
    ] == []


def test_every_expansion_is_lowercase_words_without_accents():
    assert [
        entry["expands_to"] for entry in load() if not NORMALIZED_WORDS.match(entry["expands_to"])
    ] == []


def test_no_term_repeats():
    terms = [entry["term"] for entry in load()]

    assert len(terms) == len(set(terms))


def test_every_entry_says_where_the_term_came_from():
    assert [entry["term"] for entry in load() if not entry.get("note", "").strip()] == []
