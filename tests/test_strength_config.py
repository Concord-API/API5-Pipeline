import psycopg2
import pytest

from pipeline.strength_config import seed


@pytest.fixture
def cursor(dw_ready):
    with psycopg2.connect(dw_ready) as connection, connection.cursor() as cur:
        cur.execute("TRUNCATE dw.strength_config")
        yield cur
        connection.commit()


def rows(cursor):
    cursor.execute(
        "SELECT methodology_version, reference_year, weight_agreement, weight_volume, "
        "weight_coverage, weight_recency, volume_saturation, coverage_courts, "
        "min_judged_for_percentage FROM dw.strength_config"
    )
    return cursor.fetchall()


def test_seeds_the_version_the_year_and_the_table_defaults(cursor):
    seed(cursor, 2026)

    assert rows(cursor) == [
        ("1.0", 2026, pytest.approx(0.45), pytest.approx(0.25), pytest.approx(0.20),
         pytest.approx(0.10), 300, 5, 2)
    ]


def test_seeding_twice_keeps_a_single_row(cursor):
    seed(cursor, 2026)
    seed(cursor, 2026)

    assert len(rows(cursor)) == 1


def test_seeding_again_updates_the_reference_year(cursor):
    seed(cursor, 2026)
    seed(cursor, 2027)

    assert [row[1] for row in rows(cursor)] == [2027]


def decided_settings(cursor):
    cursor.execute(
        "SELECT coverage_courts, min_judged_for_grade, divergence_points, "
        "min_judged_for_divergence FROM dw.strength_config"
    )
    return cursor.fetchall()


def test_seeds_the_settings_decided_for_the_grade_divergence_and_coverage(cursor):
    seed(cursor, 2026)

    assert decided_settings(cursor) == [(5, 10, 20, 5)]


def test_seeding_corrects_a_row_left_with_the_old_settings(cursor):
    cursor.execute(
        "INSERT INTO dw.strength_config (methodology_version, reference_year, coverage_courts, "
        "min_judged_for_grade, divergence_points, min_judged_for_divergence) "
        "VALUES ('1.0', 2025, 3, 1, 99, 1)"
    )

    seed(cursor, 2026)

    assert decided_settings(cursor) == [(5, 10, 20, 5)]
