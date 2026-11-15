import asyncio

import httpx

from eir import auth
from eir.config import Settings
from eir.main import create_app


def test_profile_is_owned_by_authenticated_session(monkeypatch, tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "profiles.db")))

    async def exercise():
        async with app.router.lifespan_context(app):
            db = app.state.database
            first_id = auth.provision_account(db, "first", "password", "First", "mission-a")
            second_id = auth.provision_account(db, "second", "password", "Second", "mission-b")
            monkeypatch.setattr(auth.time, "time", lambda: 1000000)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                async def login(username):
                    response = await client.post("/api/v1/auth/login", json={
                        "username": username, "password": "password", "device_id": "device"
                    })
                    assert response.status_code == 200
                    return response.json()

                first, second = await login("first"), await login("second")
                first_headers = {"Authorization": "Bearer " + first["access_token"]}
                second_headers = {"Authorization": "Bearer " + second["access_token"]}
                first_profile = (await client.get("/api/v1/users/me", headers=first_headers)).json()
                second_profile = (await client.get("/api/v1/users/me", headers=second_headers)).json()
                assert first_profile == first["user"]
                assert second_profile == second["user"]
                assert first_profile["user_id"] == first_id
                assert second_profile["user_id"] == second_id
                assert set(first_profile) == {
                    "user_id", "astronaut_id", "username", "display_name", "mission_id",
                    "profile_version",
                }
                assert first_profile["profile_version"] >= 1
                # Caller-provided identifiers cannot select a different account.
                response = await client.get("/api/v1/users/me", headers=first_headers, params={
                    "user_id": second_id, "astronaut_id": second_profile["astronaut_id"],
                    "username": "second",
                })
                assert response.status_code == 200 and response.json() == first_profile

                for headers in [None, {"Authorization": "Basic invalid"},
                                {"Authorization": "Bearer invalid"},
                                {"Authorization": "Bearer " + first["access_token"] + "x"},
                                {"Authorization": "Bearer " + first["refresh_token"]}]:
                    response = await client.get("/api/v1/users/me", headers=headers)
                    assert response.status_code == 401
                    assert set(response.json()) == {"code", "message"}

                rotated = await client.post("/api/v1/auth/refresh", json={
                    "refresh_token": first["refresh_token"], "device_id": "device"
                })
                assert rotated.status_code == 200
                assert (await client.get("/api/v1/users/me", headers=first_headers)).status_code == 401
                rotated_headers = {"Authorization": "Bearer " + rotated.json()["access_token"]}
                assert (await client.get("/api/v1/users/me", headers=rotated_headers)).json() == first_profile
                assert (await client.post("/api/v1/auth/logout", headers=rotated_headers)).status_code == 204
                assert (await client.get("/api/v1/users/me", headers=rotated_headers)).status_code == 401
                assert (await client.get("/api/v1/users/me", headers=second_headers)).json() == second_profile
                monkeypatch.setattr(auth.time, "time", lambda: 1000000 + auth.ACCESS_SECONDS)
                assert (await client.get("/api/v1/users/me", headers=second_headers)).status_code == 401

    asyncio.run(exercise())
