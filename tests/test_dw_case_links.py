import psycopg2
import pytest

from pipeline.dw_case_links import format_case_numbers, set_source_links
from pipeline.dw_reference import seed_courts


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.dim_case, dw.dim_court RESTART IDENTITY CASCADE")
        seed_courts(cur)
        yield cur
        connection.commit()


def insert_case(cursor, court_code, case_number, court_level="First"):
    cursor.execute(
        "INSERT INTO dw.dim_case (case_number, court_sk, court_level, source, extracted_at) "
        "SELECT %s, court_sk, %s, 'datajud', now() FROM dw.dim_court WHERE court_code = %s "
        "RETURNING case_sk",
        (case_number, court_level, court_code),
    )
    return cursor.fetchone()[0]


def fetch(cursor, case_sk):
    cursor.execute(
        "SELECT case_number_formatted, source_link, source_link_type "
        "FROM dw.dim_case WHERE case_sk = %s",
        (case_sk,),
    )
    return cursor.fetchone()


def test_formats_a_twenty_digit_case_number(cursor):
    case_sk = insert_case(cursor, "TJSP", "00000010020248260100")

    format_case_numbers(cursor)

    formatted, _, _ = fetch(cursor, case_sk)
    assert formatted == "0000001-00.2024.8.26.0100"


def test_does_not_format_a_number_with_a_different_length(cursor):
    case_sk = insert_case(cursor, "TJSP", "123")

    format_case_numbers(cursor)

    formatted, _, _ = fetch(cursor, case_sk)
    assert formatted is None


def test_tjsp_first_degree_gets_a_direct_search_link(cursor):
    case_sk = insert_case(cursor, "TJSP", "00000010020248260100", court_level="First")
    format_case_numbers(cursor)

    set_source_links(cursor)

    _, link, link_type = fetch(cursor, case_sk)
    assert link_type == "direto"
    assert "cpopg" in link


def test_tjsp_second_degree_gets_the_appeal_search_link(cursor):
    case_sk = insert_case(cursor, "TJSP", "00000010020248260100", court_level="Second")
    format_case_numbers(cursor)

    set_source_links(cursor)

    _, link, link_type = fetch(cursor, case_sk)
    assert link_type == "direto"
    assert "cposg" in link


def test_tjrj_gets_the_fixed_portal_link(cursor):
    case_sk = insert_case(cursor, "TJRJ", "00000010020248190100")

    set_source_links(cursor)

    _, link, link_type = fetch(cursor, case_sk)
    assert link_type == "portal"
    assert link == "https://www3.tjrj.jus.br/consultaprocessual/"


def test_tjmg_gets_the_fixed_portal_link(cursor):
    case_sk = insert_case(cursor, "TJMG", "00000010020248130100")

    set_source_links(cursor)

    _, link, link_type = fetch(cursor, case_sk)
    assert link_type == "portal"
    assert link == "https://www4.tjmg.jus.br/juridico/sf/proc_resultado.jsp"


def test_tjsp_without_a_formatted_number_gets_no_link(cursor):
    case_sk = insert_case(cursor, "TJSP", "123")

    set_source_links(cursor)

    _, link, link_type = fetch(cursor, case_sk)
    assert link is None
    assert link_type is None
