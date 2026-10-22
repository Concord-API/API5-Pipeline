from datetime import datetime, timezone

import pytest

from pipeline.stj_panels import load, panel_for

PANELS = load()


def on(year, month, day):
    return datetime(year, month, day, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("body", "decided_at", "panel"),
    [
        ("GABINETE DA MINISTRA NANCY ANDRIGHI", on(2025, 3, 10), "Terceira Turma"),
        ("GABINETE DO MINISTRO RICARDO VILLAS BÔAS CUEVA", on(2022, 5, 2), "Terceira Turma"),
        ("GABINETE DO MINISTRO SÉRGIO LUIZ KUKINA", on(2024, 1, 15), "Primeira Turma"),
        ("GABINETE DO MINISTRO RAUL ARAÚJO FILHO", on(2023, 7, 1), "Quarta Turma"),
        ("GABINETE DO MINISTRO MARCO AURÉLIO BELLIZZE", on(2024, 12, 2), "Segunda Turma"),
    ],
)
def test_maps_a_minister_office_to_the_panel_the_minister_sat_on_at_the_decision(
    body, decided_at, panel
):
    assert panel_for(body, decided_at, PANELS) == panel


def test_leaves_unmapped_a_decision_before_the_minister_joined_the_current_panel():
    assert panel_for("GABINETE DO MINISTRO MARCO AURÉLIO BELLIZZE", on(2023, 5, 2), PANELS) is None


@pytest.mark.parametrize(
    ("body", "panel"),
    [
        ("TERCEIRA TURMA", "Terceira Turma"),
        ("Quarta Turma", "Quarta Turma"),
        ("SEGUNDA SEÇÃO", "Segunda Seção"),
        ("CORTE ESPECIAL", "Corte Especial"),
    ],
)
def test_normalizes_a_body_that_already_names_its_panel(body, panel):
    assert panel_for(body, on(2025, 1, 1), PANELS) == panel


@pytest.mark.parametrize("body", ["VICE-PRESIDÊNCIA", "Superior Tribunal de Justiça", None])
def test_leaves_unmapped_a_body_that_is_not_a_panel(body):
    assert panel_for(body, on(2025, 1, 1), PANELS) is None


def test_the_composition_names_its_official_source():
    assert "13/10/2026" in PANELS["source"]


def test_reads_a_minister_office_with_a_double_encoded_accent():
    garbled = "GABINETE DO MINISTRO RAUL ARAÚJO FILHO".encode("utf-8").decode("latin-1")

    assert panel_for(garbled, on(2026, 3, 2), PANELS) == "Quarta Turma"


def test_maps_a_minister_who_left_the_panel_only_while_he_sat_on_it():
    office = "GABINETE DO MINISTRO MARCO BUZZI"

    assert panel_for(office, on(2025, 6, 2), PANELS) == "Quarta Turma"
    assert panel_for(office, on(2026, 3, 2), PANELS) is None
