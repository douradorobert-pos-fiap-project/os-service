import runpy
from contextlib import nullcontext
from pathlib import Path

import alembic.context
import pytest
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT / "migrations" / "env.py"


class FakeConfig:
    config_file_name = None
    config_ini_section = "alembic"

    def __init__(self) -> None:
        self.options = {"sqlalchemy.url": "postgresql://development"}

    def set_main_option(self, name: str, value: str) -> None:
        self.options[name] = value

    def get_main_option(self, name: str) -> str:
        return self.options[name]

    def get_section(self, name: str) -> dict[str, str]:
        return dict(self.options)


def _prepare_offline_context(monkeypatch: pytest.MonkeyPatch) -> FakeConfig:
    config = FakeConfig()
    monkeypatch.setattr(alembic.context, "config", config, raising=False)
    monkeypatch.setattr(alembic.context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(alembic.context, "configure", lambda **kwargs: None)
    monkeypatch.setattr(alembic.context, "begin_transaction", nullcontext)
    monkeypatch.setattr(alembic.context, "run_migrations", lambda: None)
    return config


def test_database_url_overrides_development_alembic_url(monkeypatch) -> None:
    config = _prepare_offline_context(monkeypatch)
    database_url = "postgresql+psycopg://os_service:secret@postgres/os_service_db"
    monkeypatch.setenv("APP_ENV", "sandbox")
    monkeypatch.setenv("DATABASE_URL", database_url)

    runpy.run_path(str(ENV_FILE))

    assert config.options["sqlalchemy.url"] == database_url


def test_database_url_with_percent_is_accepted_by_real_alembic_config(
    monkeypatch,
) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    monkeypatch.setattr(alembic.context, "config", config, raising=False)
    monkeypatch.setattr(alembic.context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(alembic.context, "configure", lambda **kwargs: None)
    monkeypatch.setattr(alembic.context, "begin_transaction", nullcontext)
    monkeypatch.setattr(alembic.context, "run_migrations", lambda: None)
    database_url = "postgresql+psycopg://os_service:secret%21@postgres/os_service_db"
    monkeypatch.setenv("APP_ENV", "sandbox")
    monkeypatch.setenv("DATABASE_URL", database_url)

    runpy.run_path(str(ENV_FILE))

    assert config.get_main_option("sqlalchemy.url") == database_url


def test_sandbox_migration_rejects_missing_database_url(monkeypatch) -> None:
    _prepare_offline_context(monkeypatch)
    monkeypatch.setenv("APP_ENV", "sandbox")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        runpy.run_path(str(ENV_FILE))
