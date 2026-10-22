METHODOLOGY_VERSION = "1.0"
COVERAGE_COURTS = 5
MIN_JUDGED_FOR_GRADE = 10
DIVERGENCE_POINTS = 20
MIN_JUDGED_FOR_DIVERGENCE = 5


def seed(cursor, reference_year):
    cursor.execute(
        """
        INSERT INTO dw.strength_config (
            methodology_version, reference_year, coverage_courts,
            min_judged_for_grade, divergence_points, min_judged_for_divergence
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            methodology_version = EXCLUDED.methodology_version,
            reference_year = EXCLUDED.reference_year,
            coverage_courts = EXCLUDED.coverage_courts,
            min_judged_for_grade = EXCLUDED.min_judged_for_grade,
            divergence_points = EXCLUDED.divergence_points,
            min_judged_for_divergence = EXCLUDED.min_judged_for_divergence
        """,
        (
            METHODOLOGY_VERSION, reference_year, COVERAGE_COURTS,
            MIN_JUDGED_FOR_GRADE, DIVERGENCE_POINTS, MIN_JUDGED_FOR_DIVERGENCE,
        ),
    )
