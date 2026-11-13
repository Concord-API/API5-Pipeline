from scripts.check_schema_drift import schema_diff


def test_schema_diff_is_empty_when_schemas_match():
    schema = "CREATE TABLE dw.dim_court (court_code text);\n"

    assert schema_diff(schema, schema) == ""


def test_schema_diff_reports_changed_schema_objects():
    expected = "CREATE TABLE dw.dim_court (court_code text);\n"
    actual = "CREATE TABLE dw.dim_court (court_code text NOT NULL);\n"

    diff = schema_diff(expected, actual)

    assert "court_code text NOT NULL" in diff
    assert "court_code text" in diff


def test_schema_diff_ignores_postgres_storage_metadata():
    expected = "ALTER TABLE ONLY dw.dim_court ALTER COLUMN court_sk SET (pg_attver=123);\n"
    actual = "ALTER TABLE ONLY dw.dim_court ALTER COLUMN court_sk SET (pg_attver=456);\n"

    assert schema_diff(expected, actual) == ""
