import os
from datetime import datetime, timezone

from pipeline.tpu import load
from pipeline.transform import flatten, map_court_level, parse_datetime

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "tpu_sample.json")
COLLECTED_AT = datetime(2026, 1, 2, tzinfo=timezone.utc)


def tpu():
    return load(FIXTURE)


def civil_payload(**overrides):
    payload = {
        "numeroProcesso": "0000001-00.2024.8.26.0100",
        "grau": "G1",
        "classe": {"codigo": 7, "nome": "Procedimento Comum Cível"},
        "orgaoJulgador": {"codigo": 123, "nome": "1ª Vara Cível"},
        "dataAjuizamento": "2024-01-15T10:00:00Z",
        "nivelSigilo": 0,
        "assuntos": [{"codigo": 1127, "nome": "Contratos"}],
        "movimentos": [{"codigo": 219, "nome": "Procedência", "dataHora": "2024-06-01T12:00:00Z"}],
    }
    payload.update(overrides)
    return payload


def test_flattens_a_civil_case_into_one_row_per_movement():
    rows = flatten(1, "tjsp", "https://x", COLLECTED_AT, civil_payload(), tpu())

    assert len(rows) == 1
    row = rows[0]
    assert row[1] == "tjsp"
    assert row[2] == "0000001-00.2024.8.26.0100"
    assert row[3] == "First"
    assert row[4] == 7
    assert row[11] == 219
    assert row[12] == "Procedência"
    assert row[13] == datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_discards_the_whole_case_when_any_subject_is_penal():
    payload = civil_payload(
        assuntos=[{"codigo": 1127, "nome": "Contratos"}, {"codigo": 3568, "nome": "Furto"}]
    )

    assert flatten(1, "tjsp", "https://x", COLLECTED_AT, payload, tpu()) == []


def test_discards_the_whole_case_when_the_class_is_outside_the_civil_scope():
    payload = civil_payload(classe={"codigo": 283, "nome": "Ação Penal"})

    assert flatten(1, "tjsp", "https://x", COLLECTED_AT, payload, tpu()) == []


def test_discards_a_movement_without_occurred_at():
    payload = civil_payload(movimentos=[{"codigo": 219, "nome": "Procedência"}])

    assert flatten(1, "tjsp", "https://x", COLLECTED_AT, payload, tpu()) == []


def test_discards_a_movement_without_a_code():
    payload = civil_payload(
        movimentos=[{"nome": "Procedência", "dataHora": "2024-06-01T12:00:00Z"}]
    )

    assert flatten(1, "tjsp", "https://x", COLLECTED_AT, payload, tpu()) == []


def test_uses_the_fallback_name_when_the_payload_has_no_name():
    payload = civil_payload(movimentos=[{"codigo": 219, "dataHora": "2024-06-01T12:00:00Z"}])

    rows = flatten(
        1, "tjsp", "https://x", COLLECTED_AT, payload, tpu(), movement_names={"219": "Procedência"}
    )

    assert rows[0][12] == "Procedência"


def test_discards_a_movement_without_any_name():
    payload = civil_payload(movimentos=[{"codigo": 219, "dataHora": "2024-06-01T12:00:00Z"}])

    assert flatten(1, "tjsp", "https://x", COLLECTED_AT, payload, tpu()) == []


def test_parse_datetime_accepts_iso_with_z():
    expected = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    assert parse_datetime("2024-06-01T12:00:00Z") == expected


def test_parse_datetime_accepts_datajud_digits():
    assert parse_datetime("20240601120000") == datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_parse_datetime_returns_none_for_garbage():
    assert parse_datetime("not a date") is None
    assert parse_datetime(None) is None


def test_map_court_level_known_values():
    assert map_court_level("G1") == "First"
    assert map_court_level("G2") == "Second"
    assert map_court_level("GRAU_UNICO") == "Superior"
    assert map_court_level("GR") == "Second"


def test_map_court_level_unknown_value_is_kept():
    assert map_court_level("G3") == "G3"
