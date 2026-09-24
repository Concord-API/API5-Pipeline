import os

from pipeline.harvest import AREA_QUOTAS, TRIBUNALS, datajud_url, harvest, new_session
from pipeline.tpu import load

FIXTURE_TPU = os.path.join(os.path.dirname(__file__), "fixtures", "tpu_sample.json")


class FakeConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class FakeCursor:
    def __init__(self):
        self.connection = FakeConnection()


class FakeCollect:
    def __init__(self, inserted=2):
        self.calls = []
        self.inserted = inserted

    def __call__(self, session, cursor, url, tribunal, query, quota):
        self.calls.append({"url": url, "tribunal": tribunal, "query": query, "quota": quota})
        return self.inserted


def test_datajud_url_points_to_the_court_index():
    assert datajud_url("tjsp") == "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"


def test_collects_every_court_and_area_with_its_quota():
    tpu = load(FIXTURE_TPU)
    collect = FakeCollect()

    harvest(
        None, FakeCursor(), tpu,
        tribunals=("tjsp", "tjrj"), area_quotas={"899": 700, "9985": 250}, collect=collect,
    )

    assert [(c["tribunal"], c["quota"]) for c in collect.calls] == [
        ("tjsp", 700), ("tjsp", 250), ("tjrj", 700), ("tjrj", 250),
    ]
    assert collect.calls[2]["url"] == datajud_url("tjrj")


def test_queries_the_area_subjects_and_excludes_penal_subjects():
    tpu = load(FIXTURE_TPU)
    collect = FakeCollect()

    harvest(None, FakeCursor(), tpu, tribunals=("tjsp",), area_quotas={"899": 700}, collect=collect)

    query = collect.calls[0]["query"]["bool"]
    assert {"terms": {"assuntos.codigo": [1127, 1128]}} in query["filter"]
    assert query["must_not"] == [{"terms": {"assuntos.codigo": [3568, 3593]}}]


def test_commits_after_each_area_and_returns_the_total():
    tpu = load(FIXTURE_TPU)
    cursor = FakeCursor()

    total = harvest(
        None, cursor, tpu,
        tribunals=("tjsp", "tjrj"), area_quotas={"899": 700, "9985": 250},
        collect=FakeCollect(inserted=3),
    )

    assert total == 12
    assert cursor.connection.commits == 4


def test_the_default_plan_covers_the_three_courts_and_only_known_areas():
    tpu = load()

    assert TRIBUNALS == ("tjsp", "tjrj", "tjmg")
    assert set(AREA_QUOTAS) <= set(tpu["areas"])


def test_new_session_sends_the_datajud_key():
    session = new_session("public-key")

    assert session.headers["Authorization"] == "APIKey public-key"
    assert session.headers["Content-Type"] == "application/json"


def test_queries_only_cases_with_a_verified_decision_movement():
    tpu = load(FIXTURE_TPU)
    collect = FakeCollect()

    harvest(None, FakeCursor(), tpu, tribunals=("tjsp",), area_quotas={"899": 700}, collect=collect)

    query = collect.calls[0]["query"]["bool"]
    assert {"terms": {"movimentos.codigo": [219, 220, 221, 237, 238, 239]}} in query["filter"]
