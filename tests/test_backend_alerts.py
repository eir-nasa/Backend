import asyncio
import json
import uuid

import httpx

from eir.auth import provision_account
from eir.config import Settings
from eir.main import create_app


def test_alert_retrieval_authentication_and_isolation(tmp_path):
    path = str(tmp_path / "alerts.db")
    app = create_app(Settings(database_path=path))
    alert = {
        "alert_id": "synthetic-alert", "severity": "warning", "rule_id": "synthetic-rule",
        "explanation": "Synthetic example for retrieval testing.",
        "created_at": "2026-01-01T00:00:00Z", "evidence_record_ids": [str(uuid.uuid4())],
    }

    async def exercise():
        async with app.router.lifespan_context(app):
            db = app.state.database
            alice = provision_account(db, "alice", "password", "Alice", "mission")
            bob = provision_account(db, "bob", "password", "Bob", "mission")
            with db:
                db.execute("INSERT INTO risk_alerts VALUES (?, ?, ?)",
                           (alert["alert_id"], alice, json.dumps(alert)))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://test") as client:
                async def login(username):
                    result = await client.post("/api/v1/auth/login", json={
                        "username": username, "password": "password", "device_id": "device"})
                    return {"Authorization": "Bearer " + result.json()["access_token"]}

                a, b = await login("alice"), await login("bob")
                url = "/api/v1/users/me/alerts"
                for headers in ({}, {"Authorization": "Bearer invalid"}):
                    response = await client.get(url, headers=headers)
                    assert response.status_code == 401
                    assert set(response.json()) == {"code", "message"}
                response = await client.get(url, headers=a, params={"user_id": bob})
                assert response.status_code == 200
                assert response.json() == {"items": [alert]}
                assert (await client.get(url, headers=b, params={"user_id": alice})).json() == {"items": []}
                assert (await client.post("/api/v1/auth/logout", headers=a)).status_code == 204
                assert (await client.get(url, headers=a)).status_code == 401
        reopened = create_app(Settings(database_path=path))
        async with reopened.router.lifespan_context(reopened):
            assert reopened.state.database.execute("SELECT count(*) FROM risk_alerts").fetchone()[0] == 1

    asyncio.run(exercise())


def test_records_do_not_generate_unapproved_alerts(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "records.db")))

    async def exercise():
        async with app.router.lifespan_context(app):
            provision_account(app.state.database, "alice", "password", "Alice", "mission")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://test") as client:
                login = await client.post("/api/v1/auth/login", json={"username": "alice",
                                          "password": "password", "device_id": "device"})
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                records = [{"record_id": str(uuid.uuid4()), "recorded_at": "2026-01-01T00:00:00Z",
                            "schema_version": 1, "type": "health_record",
                            "payload": {"heart_rate_bpm": 0, "temperature_c": 100}},
                           {"record_id": str(uuid.uuid4()), "recorded_at": "2026-01-01T00:00:00Z",
                            "schema_version": 1, "type": "wellbeing_checkin",
                            "payload": {"mood": 1, "connection": 1, "energy": 1,
                                        "purpose": 1, "sleep": 1}}]
                response = await client.post("/api/v1/sync/records", headers=headers,
                                             json={"device_id": "device", "records": records})
                assert response.status_code == 200
                assert [r["status"] for r in response.json()["results"]] == ["accepted", "accepted"]
                assert (await client.get("/api/v1/users/me/alerts", headers=headers)).json() == {"items": []}

    asyncio.run(exercise())
