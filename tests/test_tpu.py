import os

import pytest

from pipeline.tpu import area, civil_class_codes, datajud_civil_query, load, penal_subject_codes

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "tpu_sample.json")


@pytest.fixture
def tpu():
    return load(FIXTURE)


def test_civil_class_codes(tpu):
    assert civil_class_codes(tpu) == [7, 436]


def test_penal_subject_codes(tpu):
    assert penal_subject_codes(tpu) == [3568, 3593]


def test_area_returns_name_and_codes(tpu):
    result = area(tpu, "899")

    assert result == {"nome": "DIREITO CIVIL", "codigos": [1127, 1128]}


def test_area_raises_a_clear_error_for_an_unknown_code(tpu):
    with pytest.raises(KeyError, match="9999"):
        area(tpu, "9999")


def test_datajud_civil_query_includes_civil_classes_and_the_area_subjects(tpu):
    query = datajud_civil_query(tpu, "899")

    filters = query["bool"]["filter"]
    assert {"terms": {"classe.codigo": [7, 436]}} in filters
    assert {"terms": {"assuntos.codigo": [1127, 1128]}} in filters


def test_datajud_civil_query_excludes_every_penal_subject(tpu):
    query = datajud_civil_query(tpu, "899")

    assert query["bool"]["must_not"] == [{"terms": {"assuntos.codigo": [3568, 3593]}}]
