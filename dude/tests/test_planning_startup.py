"""Startup must not need embeddings or historical RAG packages."""

import asyncio
import builtins
import importlib
from types import SimpleNamespace

import pytest
from psycopg.conninfo import conninfo_to_dict

from services.database import build_connection_string


def test_connection_settings_quote_special_characters():
    config = SimpleNamespace(pg_host="localhost", pg_port=5432, pg_database="test",
                             pg_user="user", pg_password="test password ' \\")
    info = conninfo_to_dict(build_connection_string(config))
    assert info["password"] == config.pg_password
    assert info["dbname"] == "test"
    assert info["connect_timeout"] == "10"


def test_db_env_precedence_and_legacy_memory_cannot_be_enabled(monkeypatch):
    from config import Config

    for key, value in {"DB_HOST": "new-host", "DB_PORT": "5544", "DB_NAME": "new-db",
                       "DB_USER": "new-user", "PG_HOST": "old-host", "PG_PORT": "5433",
                       "PG_DATABASE": "old-db", "PG_USER": "old-user", "MEMORY_ENABLED": "true"}.items():
        monkeypatch.setenv(key, value)
    config = Config.from_env()
    assert (config.pg_host, config.pg_port, config.pg_database, config.pg_user) == (
        "new-host", 5544, "new-db", "new-user")
    assert config.memory_enabled is False
    for key in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"):
        monkeypatch.delenv(key)
    config = Config.from_env()
    assert (config.pg_host, config.pg_port, config.pg_database, config.pg_user) == (
        "old-host", 5433, "old-db", "old-user")


def test_renamed_wiki_environment_preserves_legacy_and_prefers_dude(monkeypatch, tmp_path):
    from config import Config
    for key in ("DUDE_WIKI_PUBLISHED_DIR", "DUDE_WIKI_ALLOW_SEED"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ALFRED_WIKI_PUBLISHED_DIR", str(tmp_path / "legacy"))
    monkeypatch.setenv("ALFRED_WIKI_ALLOW_SEED", "false")
    legacy = Config.from_env()
    assert legacy.wiki_published_dir == tmp_path / "legacy"
    assert legacy.wiki_allow_seed is False
    monkeypatch.setenv("DUDE_WIKI_PUBLISHED_DIR", str(tmp_path / "new"))
    monkeypatch.setenv("DUDE_WIKI_ALLOW_SEED", "true")
    renamed = Config.from_env()
    assert renamed.wiki_published_dir == tmp_path / "new"
    assert renamed.wiki_allow_seed is True


@pytest.mark.parametrize("broken", [False, True])
def test_lifespan_without_rag_imports_and_with_failure_health(monkeypatch, broken):
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("services.rag_service", "services.vector_store", "memory.")):
            raise AssertionError(f"Forbidden active import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    app = importlib.import_module("app")
    stores = []

    class Store:
        def __init__(self, connection):
            self.closed = False
            self.conn = SimpleNamespace(cursor=lambda: SimpleNamespace(execute=lambda q: None, close=lambda: None))
            stores.append(self)

        def close(self):
            self.closed = True

    def model(config):
        if broken:
            raise RuntimeError("offline model initialization failed")
        return object()

    monkeypatch.setattr(app, "SessionStore", Store)
    monkeypatch.setattr(app, "ContractStore", Store)
    monkeypatch.setattr(app, "create_model", model)

    async def run():
        async with app.lifespan(app.app):
            response = await app.health()
            assert response.status_code == (503 if broken else 200)
            if not broken:
                assert app.agent.knowledge.stats()["vector_required"] is False
                assert app.agent.session_memory is app.agent.user_profile is None
                assert app.agent.context_engine.vector_store is None
                assert "rag" not in app.agent.graph.nodes
            else:
                assert app.chat._agent is None
    asyncio.run(run())
    assert len(stores) == 2
    assert all(store.closed for store in stores)
