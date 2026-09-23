from pipeline.dump import dump_data


def table_names(cursor):
    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'dw' ORDER BY tablename"
    )
    return [row[0] for row in cursor.fetchall()]


def matview_dependencies(cursor):
    cursor.execute(
        """
        SELECT DISTINCT dependent.relname, source.relname
        FROM pg_depend d
        JOIN pg_rewrite r ON r.oid = d.objid
        JOIN pg_class dependent ON dependent.oid = r.ev_class
        JOIN pg_class source ON source.oid = d.refobjid
        JOIN pg_namespace n ON n.oid = dependent.relnamespace
        WHERE n.nspname = 'dw'
          AND dependent.relkind = 'm'
          AND source.relkind = 'm'
          AND dependent.oid <> source.oid
        """
    )
    return cursor.fetchall()


def matview_names(cursor):
    cursor.execute("SELECT matviewname FROM pg_matviews WHERE schemaname = 'dw'")
    names = [row[0] for row in cursor.fetchall()]
    return refresh_order(names, matview_dependencies(cursor))



def refresh_order(names, dependencies):
    pending = {name: set() for name in names}
    for dependent, source in dependencies:
        if dependent in pending and source in pending:
            pending[dependent].add(source)
    order = []
    while pending:
        ready = sorted(name for name, sources in pending.items() if not sources)
        order.extend(ready)
        for name in ready:
            del pending[name]
        for sources in pending.values():
            sources.difference_update(ready)
    return order

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


def generate(cursor, dsn, output_path, runner=None):
    tables = table_names(cursor)
    matviews = matview_names(cursor)
    dump_sql = dump_data(dsn, schema="dw", **({"runner": runner} if runner else {}))
    script = build(tables, matviews, dump_sql)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    return output_path
