import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

VALID_APP_ENVS = {"local", "prod"}


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def _default_app_env() -> str:
    if os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"):
        return "prod"
    return "local"


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    database_url_local: str | None
    database_url_prod: str | None
    db_pool_size: int
    db_max_overflow: int
    db_pool_timeout: int
    db_pool_recycle: int
    db_echo: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    app_env = (os.getenv("APP_ENV") or _default_app_env()).strip().lower()
    if app_env not in VALID_APP_ENVS:
        raise RuntimeError("APP_ENV must be one of: local, prod.")

    database_url_local = os.getenv("DATABASE_URL_LOCAL")
    database_url_prod = os.getenv("DATABASE_URL_PROD")

    if app_env == "local":
        if not database_url_local:
            raise RuntimeError("DATABASE_URL_LOCAL is required when APP_ENV=local.")
        database_url = database_url_local
    else:
        if not database_url_prod:
            raise RuntimeError("DATABASE_URL_PROD is required when APP_ENV=prod.")
        database_url = database_url_prod

    return Settings(
        app_env=app_env,
        database_url=database_url,
        database_url_local=database_url_local,
        database_url_prod=database_url_prod,
        db_pool_size=_parse_int("DB_POOL_SIZE", 10),
        db_max_overflow=_parse_int("DB_MAX_OVERFLOW", 20),
        db_pool_timeout=_parse_int("DB_POOL_TIMEOUT", 30),
        db_pool_recycle=_parse_int("DB_POOL_RECYCLE", 1800),
        db_echo=_parse_bool(os.getenv("DB_ECHO"), default=False),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
