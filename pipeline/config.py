import os


class ConfigurationError(Exception):
    pass


def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise ConfigurationError("DATABASE_URL is not set")
    return value
