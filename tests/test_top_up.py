import os

from pipeline.top_up import TOP_UP_QUOTA, harvest
from pipeline.tpu import load

FIXTURE_TPU = os.path.join(os.path.dirname(__file__), "fixtures", "tpu_sample.json")


class FakeConnection:
    def commit(self):
        pass


class FakeCursor:
    connection = FakeConnection()


class FakeCollect:
    def __init__(self):
        self.calls = []

    def __call__(self, session, cursor, url, tribunal, query, quota):
        self.calls.append({"tribunal": tribunal, "query": query["bool"], "quota": quota})
        return 3


def test_queries_only_the_thin_subjects_in_every_court_with_the_judgment_filter():
    collect = FakeCollect()

    total = harvest(None, FakeCursor(), load(FIXTURE_TPU), [1127], collect=collect)

    assert total == 12
    assert [call["tribunal"] for call in collect.calls] == ["tjsp", "tjrj", "tjmg", "stj"]
    judged = {"terms": {"movimentos.codigo": [219, 220, 221, 237, 238, 239]}}
    for call in collect.calls:
        assert {"terms": {"assuntos.codigo": [1127]}} in call["query"]["filter"]
        assert judged in call["query"]["filter"]
        assert call["query"]["must_not"] == [{"terms": {"assuntos.codigo": [3568, 3593]}}]
        assert call["quota"] == TOP_UP_QUOTA
    by_court = {call["tribunal"]: call["query"]["filter"][0] for call in collect.calls}
    assert by_court["stj"] == {"terms": {"classe.codigo": [1032, 11881, 1137, 11956]}}
    assert by_court["tjsp"] == {"terms": {"classe.codigo": [7, 436]}}


def test_does_not_query_anything_without_thin_subjects():
    collect = FakeCollect()

    assert harvest(None, FakeCursor(), load(FIXTURE_TPU), [], collect=collect) == 0
    assert collect.calls == []
