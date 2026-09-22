import psycopg2.extras

from pipeline.theme_registry import get_or_create_key


def load(cursor, themes):
    for theme in themes:
        theme_key = get_or_create_key(cursor, theme["theme_name"])
        cursor.execute(
            "INSERT INTO dw.dim_theme (theme_key, theme_name, subject_area) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (theme_name) DO UPDATE SET subject_area = EXCLUDED.subject_area "
            "RETURNING theme_sk",
            (theme_key, theme["theme_name"], theme["subject_area"]),
        )
        theme_sk = cursor.fetchone()[0]

        subject_sks = theme.get("subject_sks") or []
        if subject_sks:
            psycopg2.extras.execute_values(
                cursor,
                "INSERT INTO dw.bridge_theme_subject (theme_sk, subject_sk) VALUES %s "
                "ON CONFLICT DO NOTHING",
                [(theme_sk, sk) for sk in subject_sks],
            )


def set_official_areas(cursor):
    cursor.execute("""
        UPDATE dw.dim_theme th
        SET tpu_area = origem.area
        FROM (
            SELECT bts.theme_sk, mode() WITHIN GROUP (ORDER BY s.tpu_area) AS area
            FROM dw.bridge_theme_subject bts
            JOIN dw.dim_subject s ON s.subject_sk = bts.subject_sk
            WHERE s.tpu_area IS NOT NULL
            GROUP BY bts.theme_sk
        ) origem
        WHERE origem.theme_sk = th.theme_sk
    """)


def assert_no_orphan_themes(cursor):
    cursor.execute("""
        SELECT t.theme_name
        FROM dw.dim_theme t
        LEFT JOIN dw.bridge_theme_subject b ON b.theme_sk = t.theme_sk
        WHERE b.theme_sk IS NULL
    """)
    orphans = [row[0] for row in cursor.fetchall()]
    if orphans:
        raise ValueError(f"Themes without a source subject: {orphans}")
