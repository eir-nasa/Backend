import asyncio
import sqlite3

import httpx

from eir import auth
from eir.config import Settings
from eir.main import create_app


def test_login_rotation_logout_and_device_isolation(tmp_path):
    path = str(tmp_path / "auth.db")
    app = create_app(Settings(database_path=path))

    async def exercise():
        async with app.router.lifespan_context(app):
            db = app.state.database
            user_id = auth.provision_account(db, "demo", "synthetic password", "Demo", "mission")
            stored = db.execute("SELECT password_hash FROM auth_accounts").fetchone()[0]
            assert "synthetic password" not in stored
            assert auth.verify_password("synthetic password", stored)
            assert not auth.verify_password("wrong", stored)
            assert auth.hash_password("synthetic password") != stored
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                async def login(device):
                    return await client.post("/api/v1/auth/login", json={
                        "username": "demo", "password": "synthetic password", "device_id": device
                    })

                for username, password in [("demo", "wrong"), ("missing", "synthetic password")]:
                    response = await client.post("/api/v1/auth/login", json={
                        "username": username, "password": password, "device_id": "a"
                    })
                    assert response.status_code == 401
                    assert set(response.json()) == {"code", "message"}
                for body in [{}, {"username": "demo", "password": "x", "device_id": ""},
                             {"username": "demo", "password": "x", "device_id": "a", "x": 1},
                             {"username": "demo", "password": "x", "device_id": "a" * 129}]:
                    assert (await client.post("/api/v1/auth/login", json=body)).status_code == 422
                first = (await login("a")).json()
                second = (await login("b")).json()
                assert set(first) == {"access_token", "refresh_token", "token_type", "expires_in",
                                      "user", "online_authenticated_at"}
                assert first["token_type"] == "Bearer" and first["expires_in"] > 0
                assert first["user"]["user_id"] == user_id
                assert set(first["user"]) == {"user_id", "astronaut_id", "username", "display_name",
                                              "mission_id", "profile_version"}
                assert auth.authenticated_session(db, "Bearer " + first["access_token"])[1] == user_id
                for value in [None, "Basic abc", "Bearer invalid", "Bearer " + first["access_token"] + "x"]:
                    assert auth.authenticated_session(db, value) is None
                wrong_device = await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": first["refresh_token"], "device_id": "b"})
                assert wrong_device.status_code == 401
                rotated = await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": first["refresh_token"], "device_id": "a"})
                assert rotated.status_code == 200
                tokens = rotated.json()
                assert set(tokens) == {"access_token", "refresh_token", "token_type", "expires_in"}
                assert tokens["refresh_token"] != first["refresh_token"]
                assert auth.authenticated_session(db, "Bearer " + first["access_token"]) is None
                assert auth.authenticated_session(db, "Bearer " + tokens["access_token"])
                assert (await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": first["refresh_token"], "device_id": "a"})).status_code == 401
                assert (await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": tokens["refresh_token"], "device_id": "a", "extra": 1
                })).status_code == 422
                headers = {"Authorization": "Bearer " + tokens["access_token"]}
                response = await client.post("/api/v1/auth/logout", headers=headers)
                assert response.status_code == 204 and response.content == b""
                assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 401
                assert (await client.post("/api/v1/auth/logout")).status_code == 401
                assert (await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": tokens["refresh_token"], "device_id": "a"})).status_code == 401
                assert auth.authenticated_session(db, "Bearer " + second["access_token"])
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count(*) FROM auth_sessions").fetchone() == (1,)
            assert db.execute("SELECT refresh_hash FROM auth_sessions").fetchone()[0] != second["refresh_token"]
        app2 = create_app(Settings(database_path=path))
        async with app2.router.lifespan_context(app2):
            assert auth.authenticated_session(app2.state.database, "Bearer " + second["access_token"])

    asyncio.run(exercise())


def test_expired_access_and_refresh(monkeypatch, tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "auth.db")))

    async def exercise():
        async with app.router.lifespan_context(app):
            auth.provision_account(app.state.database, "demo", "password", "Demo", "mission")
            monkeypatch.setattr(auth.time, "time", lambda: 1000000)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                login = (await client.post("/api/v1/auth/login", json={
                    "username": "demo", "password": "password", "device_id": "a"})).json()
                monkeypatch.setattr(auth.time, "time", lambda: 1000000 + auth.ACCESS_SECONDS)
                assert (await client.post("/api/v1/auth/logout", headers={
                    "Authorization": "Bearer " + login["access_token"]})).status_code == 401
                monkeypatch.setattr(auth.time, "time", lambda: 1000000 + auth.REFRESH_SECONDS)
                assert (await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": login["refresh_token"], "device_id": "a"})).status_code == 401

    asyncio.run(exercise())
