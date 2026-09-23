import re

import psycopg2
import pytest

from pipeline.search_synonym import load, seed

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


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.search_synonym")
        yield cur
        connection.commit()


def rows(cursor):
    cursor.execute("SELECT term, expands_to, note FROM dw.search_synonym ORDER BY term")
    return cursor.fetchall()


SERASA = {"term": "serasa", "expands_to": "cadastro inadimplentes", "note": "bureau"}
SPC = {"term": "spc", "expands_to": "cadastro inadimplentes", "note": "bureau"}


def test_seeds_every_entry(cursor):
    seed(cursor, [SERASA, SPC])

    assert rows(cursor) == [
        ("serasa", "cadastro inadimplentes", "bureau"),
        ("spc", "cadastro inadimplentes", "bureau"),
    ]


def test_seeding_twice_keeps_one_row_per_term(cursor):
    seed(cursor, [SERASA, SPC])
    seed(cursor, [SERASA, SPC])

    assert len(rows(cursor)) == 2


def test_seeding_again_drops_a_term_removed_from_the_list(cursor):
    seed(cursor, [SERASA, SPC])
    seed(cursor, [SERASA])

    assert [row[0] for row in rows(cursor)] == ["serasa"]


def test_seeds_the_curated_list(cursor):
    seed(cursor, load())

    assert len(rows(cursor)) == len(load())
