import pytest

from pipeline.doctrine_transform import clean, extract, normalize_doi


def doaj_payload(**bibjson):
    base = {
        "title": "Dano moral na relação de trabalho",
        "year": "2025",
        "identifier": [
            {"type": "doi", "id": "10.22481/CCSA.v22i1.16900"},
            {"type": "pissn", "id": "1808-3102"},
        ],
        "journal": {"title": "Cadernos de Ciências Sociais Aplicadas"},
        "author": [{"name": "Kainê Ferreira "}, {"name": "Marcelly Azevedo"}, {}],
        "link": [{"type": "fulltext", "url": "http://periodicos2.uesb.br/ccsa/article/view/16900"}],
        "subject": [{"term": "Social Sciences"}, {"term": "Law"}],
    }
    base.update(bibjson)
    return {"id": "abc", "bibjson": base}


def scielo_payload(**overrides):
    payload = {
        "code": "S2179-89662019000100303",
        "doi": "10.1590/2179-8966/2018/35106",
        "publication_year": "2019",
        "article": {
            "v40": [{"_": "pt"}],
            "v12": [
                {"l": "en", "_": "Sociology of law against legal dogmatics"},
                {"l": "pt", "_": "Sociologia do direito contra dogmática"},
            ],
            "v10": [
                {"n": "Lucas P.", "s": "Konzen", "_": ""},
                {"n": "Henrique S.", "s": "Bordini", "_": ""},
            ],
        },
        "title": {"v100": [{"_": "Revista Direito e Práxis"}]},
    }
    payload.update(overrides)
    return payload


def oai_payload(**overrides):
    payload = {
        "oai_id": "oai:ojs2.emerj.jus.br:article/8",
        "title": "Apresentação",
        "creators": ["Duarte, Antonio Aurelio Abi Ramia"],
        "dates": ["2017-10-18"],
        "identifiers": ["https://ojs.emerj.com.br/index.php/revistadaemerj/article/view/8"],
        "source": "Revista da EMERJ; v. 20 n. 79 (2017): Revista da EMERJ; 9-10",
    }
    payload.update(overrides)
    return payload


def test_extracts_a_doaj_article():
    row = extract("doaj", "https://doaj.org/article/abc", doaj_payload())

    assert row == {
        "title": "Dano moral na relação de trabalho",
        "authors": "Kainê Ferreira; Marcelly Azevedo",
        "journal_name": "Cadernos de Ciências Sociais Aplicadas",
        "publication_year": 2025,
        "doi": "10.22481/ccsa.v22i1.16900",
        "article_url": "http://periodicos2.uesb.br/ccsa/article/view/16900",
        "subject_area": "Social Sciences; Law",
    }


def test_falls_back_to_the_doaj_page_without_a_fulltext_link():
    row = extract("doaj", "https://doaj.org/article/abc", doaj_payload(link=[], year="n/d"))

    assert row["article_url"] == "https://doaj.org/article/abc"
    assert row["publication_year"] is None


def test_extracts_a_scielo_article_in_its_own_language():
    url = "https://www.scielo.br/scielo.php?script=sci_arttext&pid=S2179-89662019000100303"

    row = extract("scielo", url, scielo_payload())

    assert row == {
        "title": "Sociologia do direito contra dogmática",
        "authors": "Lucas P. Konzen; Henrique S. Bordini",
        "journal_name": "Revista Direito e Práxis",
        "publication_year": 2019,
        "doi": "10.1590/2179-8966/2018/35106",
        "article_url": url,
        "subject_area": None,
    }


def test_reads_the_scielo_doi_from_the_article_metadata():
    payload = scielo_payload(doi=None)
    payload["article"]["v237"] = [{"_": "10.1590/ABC"}]

    assert extract("scielo", "https://x", payload)["doi"] == "10.1590/abc"


def test_extracts_an_oai_record():
    row = extract("oai_emerj", "https://ojs.emerj.com.br/article/view/8", oai_payload())

    assert row == {
        "title": "Apresentação",
        "authors": "Duarte, Antonio Aurelio Abi Ramia",
        "journal_name": "Revista da EMERJ",
        "publication_year": 2017,
        "doi": None,
        "article_url": "https://ojs.emerj.com.br/index.php/revistadaemerj/article/view/8",
        "subject_area": None,
    }


def test_reads_the_oai_doi_and_keeps_the_article_page():
    payload = oai_payload(identifiers=[
        "https://doi.org/10.5555/Emerj.8",
        "https://ojs.emerj.com.br/index.php/revistadaemerj/article/view/8",
    ])

    row = extract("oai_emerj", "https://ojs.emerj.com.br/article/view/8", payload)

    assert row["doi"] == "10.5555/emerj.8"
    assert row["article_url"] == "https://ojs.emerj.com.br/index.php/revistadaemerj/article/view/8"


def test_uses_the_harvested_address_when_the_oai_record_has_no_link():
    payload = oai_payload(identifiers=[], dates=[], creators=[], source=None)

    row = extract("oai_ejef_tjmg", "https://ejef/oai?verb=GetRecord", payload)

    assert row["article_url"] == "https://ejef/oai?verb=GetRecord"
    assert row["publication_year"] is None
    assert row["authors"] is None
    assert row["journal_name"] is None


@pytest.mark.parametrize("source, payload", [
    ("doaj", doaj_payload(title="  ")),
    ("scielo", scielo_payload(article={"v12": []})),
    ("oai_indexlaw", oai_payload(title=None)),
])
def test_skips_an_article_without_title(source, payload):
    assert extract(source, "https://x", payload) is None


def test_rejects_an_unknown_source():
    with pytest.raises(ValueError, match="unknown doctrine source: lattes"):
        extract("lattes", "https://x", {})


def test_cleans_nested_html_entities_and_spaces():
    assert clean("  A &amp;#8220;boa-fé&amp;#8221;\n objetiva ") == "A “boa-fé” objetiva"
    assert clean("   ") is None
    assert clean(None) is None


@pytest.mark.parametrize("value, expected", [
    ("10.1590/ABC", "10.1590/abc"),
    ("https://doi.org/10.1590/abc", "10.1590/abc"),
    ("http://dx.doi.org/10.1590/abc", "10.1590/abc"),
    ("doi: 10.1590/abc", "10.1590/abc"),
    ("1808-3102", None),
    ("", None),
    (None, None),
])
def test_normalizes_the_doi(value, expected):
    assert normalize_doi(value) == expected
