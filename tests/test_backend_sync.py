import asyncio
import copy
import uuid

import httpx

from eir.auth import provision_account
from eir.config import Settings
from eir.main import create_app

URL = "/api/v1/sync/records"


def record(kind="health_record"):
    return {"record_id": str(uuid.uuid4()), "recorded_at": "2026-01-01T00:00:00Z",
            "schema_version": 1, "type": kind,
            "payload": ({"heart_rate_bpm": 70} if kind == "health_record" else
                        {"mood": 1, "connection": 2, "energy": 3, "purpose": 4, "sleep": 5})}


def test_sync_batch_replay_conflict_isolation_and_validation(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "sync.db")))

    async def run():
        async with app.router.lifespan_context(app):
            db = app.state.database
            alice = provision_account(db, "alice", "password", "Alice", "mission")
            provision_account(db, "bob", "password", "Bob", "mission")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
                async def login(name):
                    r = await c.post("/api/v1/auth/login", json={"username": name, "password": "password", "device_id": "device"})
                    return {"Authorization": "Bearer " + r.json()["access_token"]}
                a, b = await login("alice"), await login("bob")
                health, wellbeing = record(), record("wellbeing_checkin")
                invalid = record()
                invalid["payload"] = {"sleep_hours": 25}
                batch = {"device_id": "device", "records": [health, wellbeing, invalid]}
                assert (await c.post(URL, json=batch)).status_code == 401
                assert (await c.post(URL, json=batch, headers={"Authorization": "Bearer invalid"})).status_code == 401
                assert db.execute("SELECT count(*) FROM health_records").fetchone()[0] == 0
                response = await c.post(URL, json=batch, headers=a)
                assert response.status_code == 200
                assert [x["status"] for x in response.json()["results"]] == ["accepted", "accepted", "rejected"]
                assert [x["record_id"] for x in response.json()["results"]] == [x["record_id"] for x in batch["records"]]
                replay = copy.deepcopy(health)
                replay["recorded_at"] = "2025-12-31T19:00:00-05:00"
                changed = copy.deepcopy(health)
                changed["payload"]["heart_rate_bpm"] = 71
                other_type = copy.deepcopy(wellbeing)
                other_type["record_id"] = health["record_id"]
                r = await c.post(URL, headers=a, json={"device_id": "other", "records": [replay, changed, other_type, wellbeing]})
                assert [x["status"] for x in r.json()["results"]] == ["duplicate", "conflict", "conflict", "duplicate"]
                r = await c.post(URL, headers=b, json={"device_id": "device", "records": [health]})
                assert r.json()["results"][0]["status"] == "conflict"
                assert db.execute("SELECT owner_id FROM health_records").fetchone()[0] == alice
                assert (await c.get("/api/v1/users/me/health-records", headers=b)).json()["items"] == []
                for bad in [{"device_id": "device", "records": []},
                            {"device_id": "device", "records": [health] * 21},
                            {"device_id": "", "records": [health]},
                            {"device_id": "device", "records": [health, {"record_id": "bad"}]},
                            {"device_id": "device", "records": [health], "owner_id": "bob"}]:
                    assert (await c.post(URL, headers=a, json=bad)).status_code == 422
                assert db.execute("SELECT count(*) FROM health_records").fetchone()[0] == 1
                assert db.execute("SELECT count(*) FROM wellbeing_checkins").fetchone()[0] == 1
        async with app.router.lifespan_context(app):
            assert app.state.database.execute("SELECT count(*) FROM health_records").fetchone()[0] == 1
            assert app.state.database.execute("SELECT count(*) FROM wellbeing_checkins").fetchone()[0] == 1

    asyncio.run(run())


def test_storage_failure_rolls_back_item_and_allows_retry(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "failure.db")))

    async def run():
        async with app.router.lifespan_context(app):
            db = app.state.database
            provision_account(db, "alice", "password", "Alice", "mission")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
                login = await c.post("/api/v1/auth/login", json={"username": "alice", "password": "password", "device_id": "device"})
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                health, wellbeing = record(), record("wellbeing_checkin")
                db.execute("CREATE TRIGGER fail_health AFTER INSERT ON health_records BEGIN SELECT RAISE(ABORT, 'failure'); END")
                db.commit()
                batch = {"device_id": "device", "records": [health, wellbeing]}
                r = await c.post(URL, headers=headers, json=batch)
                assert [x["status"] for x in r.json()["results"]] == ["retryable", "accepted"]
                assert db.execute("SELECT count(*) FROM health_records").fetchone()[0] == 0
                assert not db.in_transaction
                db.execute("DROP TRIGGER fail_health")
                db.commit()
                r = await c.post(URL, headers=headers, json=batch)
                assert [x["status"] for x in r.json()["results"]] == ["accepted", "duplicate"]

    asyncio.run(run())
