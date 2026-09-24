from pathlib import Path

import pytest

from pipeline import config
from pipeline.config import (
    ConfigurationError,
    database_url,
    datajud_api_key,
    load_env,
    load_file_path,
)


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


def test_load_env_reads_the_settings_from_the_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DATAJUD_API_KEY=from-file\nDATABASE_URL=postgresql://file\n")
    monkeypatch.delenv("DATAJUD_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    load_env(env_file)

    assert datajud_api_key() == "from-file"
    assert database_url() == "postgresql://file"


def test_the_environment_wins_over_the_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DATAJUD_API_KEY=from-file\n")
    monkeypatch.setenv("DATAJUD_API_KEY", "from-environment")

    load_env(env_file)

    assert datajud_api_key() == "from-environment"


def test_load_env_without_a_file_keeps_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAJUD_API_KEY", "from-environment")

    load_env(tmp_path / "missing.env")

    assert datajud_api_key() == "from-environment"


def test_the_default_file_is_the_env_in_the_working_directory(monkeypatch):
    monkeypatch.undo()

    assert config.ENV_FILE == Path(".env")


def test_the_example_lists_every_setting_and_the_real_file_is_ignored():
    root = Path(__file__).resolve().parent.parent
    example = (root / ".env.example").read_text(encoding="utf-8")
    ignored = (root / ".gitignore").read_text(encoding="utf-8").splitlines()

    for name in ("DATABASE_URL=", "DATAJUD_API_KEY=", "LOAD_FILE_PATH="):
        assert name in example
    assert ".env" in ignored
