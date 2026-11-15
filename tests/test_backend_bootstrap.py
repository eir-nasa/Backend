import asyncio
from uuid import UUID

import httpx

from eir.auth import provision_account
from eir.config import Settings
from eir.health_records import HealthRecord, store_health_record
from eir.main import create_app
from eir.wellbeing import WellbeingRecord, store_wellbeing_checkin


def test_bootstrap_combines_owned_history_with_stable_pagination(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "bootstrap.db")))

    async def exercise():
        async with app.router.lifespan_context(app):
            db = app.state.database
            alice = provision_account(db, "alice", "password", "Alice", "mission")
            bob = provision_account(db, "bob", "password", "Bob", "mission")

            def record(number, kind):
                return {
                    "record_id": str(UUID(int=number)), "recorded_at": "2026-01-01T00:00:00Z",
                    "schema_version": 1, "type": kind,
                    "payload": {"heart_rate_bpm": 70} if kind == "health_record" else {
                        "mood": 1, "connection": 2, "energy": 3, "purpose": 4, "sleep": 5
                    },
                }

            for number, kind in [(1, "health_record"), (2, "wellbeing_checkin"),
                                 (3, "health_record"), (4, "wellbeing_checkin")]:
                data = record(number, kind)
                if kind == "health_record":
                    assert store_health_record(db, alice, HealthRecord.model_validate(data)) == "accepted"
                else:
                    assert store_wellbeing_checkin(db, alice, WellbeingRecord.model_validate(data)) == "accepted"
            assert store_health_record(db, bob, HealthRecord.model_validate(record(5, "health_record"))) == "accepted"

            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                async def login(name):
                    response = await client.post("/api/v1/auth/login", json={
                        "username": name, "password": "password", "device_id": "device"
                    })
                    assert response.status_code == 200
                    return response.json()

                a, b = await login("alice"), await login("bob")
                headers = {"Authorization": "Bearer " + a["access_token"]}
                url = "/api/v1/users/me/bootstrap"
                assert (await client.get(url)).status_code == 401
                assert (await client.get(url, headers={"Authorization": "Bearer invalid"})).status_code == 401
                first = (await client.get(url, headers=headers, params={"limit": 2, "user_id": bob})).json()
                assert set(first) == {"profile", "health_records", "wellbeing_checkins", "next_cursor"}
                assert first["profile"] == a["user"]
                assert [r["record_id"] for r in first["health_records"]] == [str(UUID(int=1))]
                assert [r["record_id"] for r in first["wellbeing_checkins"]] == [str(UUID(int=2))]
                assert set(first["health_records"][0]) == {"record_id", "recorded_at", "schema_version", "type", "payload", "received_at"}
                cursor = first["next_cursor"]
                assert cursor
                second_response = await client.get(url, headers=headers, params={"limit": 2, "cursor": cursor})
                second = second_response.json()
                assert second["profile"] == a["user"]
                assert [r["record_id"] for r in second["health_records"]] == [str(UUID(int=3))]
                assert [r["record_id"] for r in second["wellbeing_checkins"]] == [str(UUID(int=4))]
                assert second["next_cursor"] is None
                assert (await client.get(url, headers=headers, params={"limit": 2, "cursor": cursor})).json() == second
                other = (await client.get(url, headers={"Authorization": "Bearer " + b["access_token"]}, params={"cursor": cursor})).json()
                assert other["profile"] == b["user"]
                assert [r["record_id"] for r in other["health_records"]] == [str(UUID(int=5))]
                assert other["wellbeing_checkins"] == []
                empty = (await client.get(url, headers=headers, params={"cursor": other_cursor()})).json()
                assert empty["health_records"] == empty["wellbeing_checkins"] == []
                assert empty["next_cursor"] is None
                for params in [{"cursor": "invalid!"}, {"cursor": ""}, {"limit": 0}, {"limit": 101}, {"limit": "bad"}]:
                    assert (await client.get(url, headers=headers, params=params)).status_code == 422
                assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
                assert (await client.get(url, headers=headers, params={"cursor": cursor})).status_code == 401

    asyncio.run(exercise())


def other_cursor():
    from eir.health_records import _cursor_encode
    return _cursor_encode(str(UUID(int=10)))
