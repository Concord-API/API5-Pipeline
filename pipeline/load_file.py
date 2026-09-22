def table_names(cursor):
    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'dw' ORDER BY tablename"
    )
    return [row[0] for row in cursor.fetchall()]


def matview_names(cursor):
    cursor.execute(
        "SELECT matviewname FROM pg_matviews WHERE schemaname = 'dw' ORDER BY matviewname"
    )
    return [row[0] for row in cursor.fetchall()]


def build(tables, matviews, dump_sql):
    qualified = ", ".join(f"dw.{table}" for table in tables)
    parts = [
        "BEGIN;",
        f"TRUNCATE {qualified} RESTART IDENTITY CASCADE;",
        dump_sql,
    ]
    parts.extend(f"REFRESH MATERIALIZED VIEW dw.{view};" for view in matviews)
    parts.append("COMMIT;")
    return "\n".join(parts) + "\n"
