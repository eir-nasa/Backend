import asyncio
import sqlite3
import uuid

import httpx
import pytest
from pydantic import ValidationError

from eir.auth import provision_account
from eir.config import Settings
from eir.health_records import HealthRecord, store_health_record
from eir.main import create_app
from eir.wellbeing import WellbeingRecord, store_wellbeing_checkin


def record(record_id=None):
    return {"record_id": str(record_id or uuid.uuid4()), "recorded_at": "2026-01-01T00:00:00Z",
            "schema_version": 1, "type": "wellbeing_checkin",
            "payload": {"mood": 1, "connection": 2, "energy": 3, "purpose": 4, "sleep": 5}}


@pytest.mark.parametrize("field,value", [
    ("mood", 0), ("connection", 6), ("energy", True), ("purpose", 1.5),
    ("sleep", "3"), ("note", None), ("note", "x" * 501), ("extra", 1),
])
def test_invalid_payload(field, value):
    data = record()
    data["payload"][field] = value
    with pytest.raises(ValidationError):
        WellbeingRecord.model_validate(data)


def test_required_dimensions_and_record_validation():
    for field in ("mood", "connection", "energy", "purpose", "sleep"):
        data = record()
        del data["payload"][field]
        with pytest.raises(ValidationError):
            WellbeingRecord.model_validate(data)
    for field, value in [("record_id", "bad"), ("recorded_at", "2026-01-01"),
                         ("recorded_at", "2026-01-01T00:00:00"),
                         ("schema_version", True), ("schema_version", 2), ("type", "health_record")]:
        data = record()
        data[field] = value
        with pytest.raises(ValidationError):
            WellbeingRecord.model_validate(data)
    data = record()
    data["payload"]["note"] = "x" * 500
    assert WellbeingRecord.model_validate(data).payload.note == "x" * 500


def test_persistence_pagination_and_isolation(tmp_path):
    path = str(tmp_path / "wellbeing.db")
    app = create_app(Settings(database_path=path))

    async def exercise():
        async with app.router.lifespan_context(app):
            db = app.state.database
            alice = provision_account(db, "alice", "password", "Alice", "mission")
            bob = provision_account(db, "bob", "password", "Bob", "mission")
            ids = [uuid.UUID(int=i) for i in range(1, 7)]
            items = [WellbeingRecord.model_validate(record(i)) for i in ids]
            for item in items[:3]:
                assert store_wellbeing_checkin(db, alice, item) == "accepted"
            assert store_wellbeing_checkin(db, bob, items[3]) == "accepted"
            equivalent = record(ids[0])
            equivalent["recorded_at"] = "2025-12-31T19:00:00-05:00"
            assert store_wellbeing_checkin(db, alice, WellbeingRecord.model_validate(equivalent)) == "duplicate"
            assert store_wellbeing_checkin(db, bob, items[0]) == "conflict"
            changed = record(ids[0])
            changed["payload"]["mood"] = 5
            assert store_wellbeing_checkin(db, alice, WellbeingRecord.model_validate(changed)) == "conflict"
            with pytest.raises(sqlite3.IntegrityError):
                store_wellbeing_checkin(db, "missing", items[4])
            assert not db.in_transaction
            def health(i):
                return HealthRecord.model_validate({
                    "record_id": str(i), "recorded_at": "2026-01-01T00:00:00Z",
                    "schema_version": 1, "type": "health_record",
                    "payload": {"heart_rate_bpm": 1},
                })
            assert store_health_record(db, alice, health(ids[0])) == "conflict"
            assert store_health_record(db, alice, health(ids[4])) == "accepted"
            assert store_wellbeing_checkin(db, alice, items[4]) == "conflict"
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                async def login(name):
                    response = await client.post("/api/v1/auth/login", json={"username": name, "password": "password", "device_id": "device"})
                    return {"Authorization": "Bearer " + response.json()["access_token"]}
                a, b = await login("alice"), await login("bob")
                url = "/api/v1/users/me/wellbeing-checkins"
                assert (await client.get(url)).status_code == 401
                first = await client.get(url, headers=a, params={"limit": 2, "user_id": bob})
                assert first.status_code == 200
                page = first.json()
                assert [x["record_id"] for x in page["items"]] == list(map(str, ids[:2]))
                assert set(page["items"][0]) == {"record_id", "recorded_at", "schema_version", "type", "payload", "received_at"}
                assert page["items"][0]["payload"] == record(ids[0])["payload"]
                second = (await client.get(url, headers=a, params={"limit": 2, "cursor": page["next_cursor"]})).json()
                assert [x["record_id"] for x in second["items"]] == [str(ids[2])]
                assert second["next_cursor"] is None
                other = (await client.get(url, headers=b)).json()
                assert [x["record_id"] for x in other["items"]] == [str(ids[3])]
                assert other["next_cursor"] is None
                assert (await client.get(url, headers=a, params={"cursor": "invalid!"})).status_code == 422
                for limit in [0, 101, "bad"]:
                    assert (await client.get(url, headers=a, params={"limit": limit})).status_code == 422
        reopened = create_app(Settings(database_path=path))
        async with reopened.router.lifespan_context(reopened):
            assert reopened.state.database.execute("SELECT count(*) FROM wellbeing_checkins").fetchone()[0] == 4

    asyncio.run(exercise())
