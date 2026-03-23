from __future__ import annotations

import importlib

import pytest


def _load_config():
    config = importlib.import_module("config")
    config.reset_settings_cache()
    return config


def test_resolves_local_database_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL_LOCAL", "postgresql+psycopg://postgres:postgres@localhost:5432/local_db")
    monkeypatch.delenv("DATABASE_URL_PROD", raising=False)
    config = _load_config()

    settings = config.get_settings()

    assert settings.app_env == "local"
    assert settings.database_url == "postgresql+psycopg://postgres:postgres@localhost:5432/local_db"


def test_resolves_prod_database_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+psycopg://app:secret@db.example.com:5432/prod_db")
    monkeypatch.delenv("DATABASE_URL_LOCAL", raising=False)
    config = _load_config()

    settings = config.get_settings()

    assert settings.app_env == "prod"
    assert settings.database_url == "postgresql+psycopg://app:secret@db.example.com:5432/prod_db"


def test_invalid_app_env_raises(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL_LOCAL", "postgresql+psycopg://postgres:postgres@localhost:5432/local_db")
    config = _load_config()

    with pytest.raises(RuntimeError, match="APP_ENV"):
        config.get_settings()


def test_missing_local_url_raises(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("DATABASE_URL_LOCAL", raising=False)
    config = _load_config()

    with pytest.raises(RuntimeError, match="DATABASE_URL_LOCAL"):
        config.get_settings()


def test_missing_prod_url_raises(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("DATABASE_URL_PROD", raising=False)
    config = _load_config()

    with pytest.raises(RuntimeError, match="DATABASE_URL_PROD"):
        config.get_settings()
