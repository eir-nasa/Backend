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


def record(record_id=None, payload=None):
    return {
        "record_id": str(record_id or uuid.uuid4()),
        "recorded_at": "2026-01-01T00:00:00Z",
        "schema_version": 1,
        "type": "health_record",
        "payload": payload if payload is not None else {"heart_rate_bpm": 0},
    }


@pytest.mark.parametrize("payload", [
    {}, {"heart_rate_bpm": -1}, {"glucose_mg_dl": -0.1}, {"sleep_hours": 24.1},
    {"sleep_hours": -1}, {"systolic_bp_mmhg": -1}, {"diastolic_bp_mmhg": -1},
    {"heart_rate_bpm": 1.5}, {"heart_rate_bpm": True}, {"temperature_c": "37"},
    {"temperature_c": None}, {"unknown": 1}, {"temperature_c": float("nan")},
])
def test_invalid_health_payloads(payload):
    with pytest.raises(ValidationError):
        HealthRecord.model_validate(record(payload=payload))


@pytest.mark.parametrize("field,value", [
    ("record_id", "not-a-uuid"), ("recorded_at", "2026-01-01"),
    ("recorded_at", "2026-01-01T00:00:00"), ("schema_version", 2),
    ("schema_version", True), ("type", "wellbeing_checkin"),
])
def test_invalid_record_envelope(field, value):
    data = record()
    data[field] = value
    with pytest.raises(ValidationError):
        HealthRecord.model_validate(data)


def test_persistence_pagination_and_account_isolation(tmp_path):
    path = str(tmp_path / "health.db")
    app = create_app(Settings(database_path=path))

    async def exercise():
        async with app.router.lifespan_context(app):
            db = app.state.database
            alice = provision_account(db, "alice", "password", "Alice", "mission")
            bob = provision_account(db, "bob", "password", "Bob", "mission")
            ids = [uuid.UUID(int=i) for i in range(1, 5)]
            records = [HealthRecord.model_validate(record(i, {"sleep_hours": 24, "temperature_c": -5}))
                       for i in ids]
            for item in records[:3]:
                assert store_health_record(db, alice, item) == "accepted"
            assert store_health_record(db, bob, records[3]) == "accepted"
            assert store_health_record(db, alice, records[0]) == "duplicate"
            equivalent = record(ids[0], {"temperature_c": -5, "sleep_hours": 24})
            equivalent["recorded_at"] = "2025-12-31T19:00:00-05:00"
            assert store_health_record(db, alice, HealthRecord.model_validate(equivalent)) == "duplicate"
            with pytest.raises(sqlite3.IntegrityError):
                store_health_record(db, "missing-owner", HealthRecord.model_validate(record()))
            assert not db.in_transaction
            assert store_health_record(db, bob, records[0]) == "conflict"
            changed = record(ids[0], {"sleep_hours": 2})
            assert store_health_record(db, alice, HealthRecord.model_validate(changed)) == "conflict"
            assert db.execute("SELECT count(*) FROM health_records").fetchone()[0] == 4
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://test") as client:
                async def login(username):
                    result = await client.post("/api/v1/auth/login", json={
                        "username": username, "password": "password", "device_id": "device"})
                    return {"Authorization": "Bearer " + result.json()["access_token"]}

                a, b = await login("alice"), await login("bob")
                assert (await client.get("/api/v1/users/me/health-records")).status_code == 401
                url = "/api/v1/users/me/health-records"
                first = await client.get(url, headers=a, params={"limit": 2, "user_id": bob})
                assert first.status_code == 200
                page = first.json()
                assert [x["record_id"] for x in page["items"]] == list(map(str, ids[:2]))
                assert set(page["items"][0]) == {"record_id", "recorded_at", "schema_version", "type", "payload", "received_at"}
                assert page["items"][0]["payload"] == {"sleep_hours": 24.0, "temperature_c": -5.0}
                second = (await client.get(url, headers=a, params={"limit": 2, "cursor": page["next_cursor"]})).json()
                assert [x["record_id"] for x in second["items"]] == [str(ids[2])]
                assert second["next_cursor"] is None
                other = (await client.get(url, headers=b)).json()
                assert [x["record_id"] for x in other["items"]] == [str(ids[3])]
                assert (await client.get(url, headers=a, params={"cursor": "invalid!"})).status_code == 422
                for limit in [0, 101, "bad"]:
                    assert (await client.get(url, headers=a, params={"limit": limit})).status_code == 422
        reopened = create_app(Settings(database_path=path))
        async with reopened.router.lifespan_context(reopened):
            assert reopened.state.database.execute("SELECT count(*) FROM health_records").fetchone()[0] == 4

    asyncio.run(exercise())
