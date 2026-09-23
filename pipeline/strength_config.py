METHODOLOGY_VERSION = "1.0"


def seed(cursor, reference_year):
    cursor.execute(
        """
        INSERT INTO dw.strength_config (methodology_version, reference_year)
        VALUES (%s, %s)
        ON CONFLICT (id) DO UPDATE SET
            methodology_version = EXCLUDED.methodology_version,
            reference_year = EXCLUDED.reference_year
        """,
        (METHODOLOGY_VERSION, reference_year),
    )
