from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def _reset_runtime() -> None:
    config = importlib.import_module("config")
    session = importlib.import_module("database.session")
    config.reset_settings_cache()
    session.reset_engine()


@pytest.fixture(scope="session", autouse=True)
def default_env() -> None:
    os.environ.setdefault("APP_ENV", "local")
    os.environ.setdefault("DATABASE_URL_LOCAL", "postgresql+psycopg://postgres:postgres@localhost:5432/ideagen_test")
    os.environ.setdefault("DB_POOL_SIZE", "5")
    os.environ.setdefault("DB_MAX_OVERFLOW", "5")
    os.environ.setdefault("DB_POOL_TIMEOUT", "30")
    os.environ.setdefault("DB_POOL_RECYCLE", "1800")
    os.environ.setdefault("DB_ECHO", "false")


@pytest.fixture(scope="session")
def alembic_config(default_env) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def postgres_server(default_env):
    url = os.environ["DATABASE_URL_LOCAL"]
    engine = create_engine(url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment failure
        pytest.fail(f"PostgreSQL is not reachable at {url}: {exc}")
    finally:
        engine.dispose()
    yield


@pytest.fixture()
def migrated_db(alembic_config, postgres_server):
    _reset_runtime()
    engine = create_engine(os.environ["DATABASE_URL_LOCAL"], future=True, isolation_level="AUTOCOMMIT")
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    command.upgrade(alembic_config, "head")
    _reset_runtime()
    yield
    _reset_runtime()
