import os

import psycopg2
import pytest
from testcontainers.postgres import PostgresContainer

from pipeline.staging_schema import ensure as ensure_staging

DW_SCHEMA_SQL = os.path.join(os.path.dirname(__file__), "fixtures", "dw_schema.sql")


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16") as container:
        yield container.get_connection_url().replace("+psycopg2", "")


@pytest.fixture(scope="session")
def dw_ready(postgres_url):
    with open(DW_SCHEMA_SQL, encoding="utf-8") as handle:
        ddl = handle.read()
    with psycopg2.connect(postgres_url) as connection, connection.cursor() as cursor:
        cursor.execute(ddl)
        ensure_staging(cursor)
    return postgres_url
