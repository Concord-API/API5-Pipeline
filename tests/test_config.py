import pytest

from pipeline.config import ConfigurationError, database_url


def test_reads_the_database_url_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/dw")

    assert database_url() == "postgresql://user:pass@localhost:5432/dw"


def test_fails_clearly_when_the_database_url_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        database_url()
