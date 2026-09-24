import os
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(".env")


class ConfigurationError(Exception):
    pass


def load_env(path=None):
    load_dotenv(ENV_FILE if path is None else path, override=False)


def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise ConfigurationError("DATABASE_URL is not set")
    return value


def datajud_api_key() -> str:
    value = os.environ.get("DATAJUD_API_KEY")
    if not value:
        raise ConfigurationError("DATAJUD_API_KEY is not set")
    return value


def load_file_path() -> str:
    return os.environ.get("LOAD_FILE_PATH") or "ratio-load.sql"
