import asyncio
import sqlite3

import httpx
import pytest

from eir import database
from eir.config import Settings
from eir.main import create_app


def test_health_is_public_and_matches_contract(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "eir.db")))

    async def exercise():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/health")
                assert response.status_code == 200
                assert response.headers["content-type"] == "application/json"
                assert response.json() == {"status": "ok"}
                assert (await client.post("/api/v1/health")).status_code == 405
                assert (await client.get("/health")).status_code == 404
                assert (await client.get("/docs")).status_code == 404

    asyncio.run(exercise())


def test_lifecycle_migrates_persists_and_closes(tmp_path):
    path = str(tmp_path / "eir.db")
    app = create_app(Settings(database_path=path))

    async def exercise():
        async with app.router.lifespan_context(app):
            connection = app.state.database
            assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
            assert connection.execute("PRAGMA user_version").fetchone() == (len(database.MIGRATIONS),)
            connection.execute("INSERT INTO eir_metadata VALUES ('example', 'value')")
            connection.commit()
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        second_app = create_app(Settings(database_path=path))
        async with second_app.router.lifespan_context(second_app):
            assert second_app.state.database.execute("SELECT * FROM eir_metadata").fetchall() == [
                ("example", "value")
            ]

    asyncio.run(exercise())


def test_configuration_from_environment(monkeypatch, tmp_path):
    path = str(tmp_path / "configured.db")
    monkeypatch.setenv("EIR_DATABASE_PATH", path)

    async def exercise():
        app = create_app()
        async with app.router.lifespan_context(app):
            assert app.state.settings.database_path == path

    asyncio.run(exercise())
    assert (tmp_path / "configured.db").is_file()
    monkeypatch.setenv("EIR_DATABASE_PATH", " ")
    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(exercise())


def test_startup_rejects_unopenable_database(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "missing" / "eir.db")))

    async def exercise():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(sqlite3.OperationalError):
        asyncio.run(exercise())


def test_future_schema_rejected_without_modification(tmp_path):
    path = str(tmp_path / "future.db")
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 99")
    app = create_app(Settings(database_path=path))

    async def exercise():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(RuntimeError, match="Unsupported database schema version"):
        asyncio.run(exercise())
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (99,)


def test_failed_migration_rolls_back_all_changes(monkeypatch, tmp_path):
    path = str(tmp_path / "failure.db")

    def fail(connection):
        connection.execute("CREATE TABLE partial (id INTEGER)")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(database, "MIGRATIONS", (*database.MIGRATIONS, fail))
    with pytest.raises(RuntimeError, match="migration failed"):
        database.open_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (0,)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall() == []
