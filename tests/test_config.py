import pytest

from pipeline.config import ConfigurationError, database_url, datajud_api_key, load_file_path


def test_reads_the_database_url_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/dw")

    assert database_url() == "postgresql://user:pass@localhost:5432/dw"


def test_fails_clearly_when_the_database_url_is_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        database_url()


def test_reads_the_datajud_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("DATAJUD_API_KEY", "public-key")

    assert datajud_api_key() == "public-key"


def test_fails_clearly_when_the_datajud_key_is_missing(monkeypatch):
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="DATAJUD_API_KEY"):
        datajud_api_key()


def test_reads_the_load_file_path_from_the_environment(monkeypatch):
    monkeypatch.setenv("LOAD_FILE_PATH", "out/load.sql")

    assert load_file_path() == "out/load.sql"


def test_uses_the_default_load_file_path_when_not_set(monkeypatch):
    monkeypatch.delenv("LOAD_FILE_PATH", raising=False)

    assert load_file_path() == "ratio-load.sql"
