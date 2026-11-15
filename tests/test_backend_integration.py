"""End-to-end exercises against the approved contract using synthetic accounts."""

import asyncio
import copy
from pathlib import Path
from uuid import UUID

import httpx
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from eir.auth import provision_account
from eir.config import Settings
from eir.main import create_app

BASELINE = yaml.safe_load((Path(__file__).resolve().parents[1] / "contracts/openapi.yaml").read_text())


def assert_schema(instance, name):
    schema = {"$ref": f"#/components/schemas/{name}", "components": BASELINE["components"]}
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


def test_generated_openapi_operation_inventory_matches_baseline():
    live = create_app().openapi()
    assert live["openapi"] == BASELINE["openapi"]
    assert set(live["paths"]) == set(BASELINE["paths"])
    for path, methods in BASELINE["paths"].items():
        assert set(live["paths"][path]) == set(methods)
        for method, operation in methods.items():
            assert live["paths"][path][method]["operationId"] == operation["operationId"]


def test_generated_openapi_profile_schema_semantically_matches_baseline():
    live = create_app().openapi()["components"]["schemas"]["AstronautProfile"]
    expected = BASELINE["components"]["schemas"]["AstronautProfile"]
    assert live["type"] == expected["type"]
    assert live["additionalProperties"] == expected["additionalProperties"]
    assert set(live["required"]) == set(expected["required"])
    assert set(live["properties"]) == set(expected["properties"])
    for name, schema in expected["properties"].items():
        assert {key: live["properties"][name].get(key) for key in schema} == schema


def test_synthetic_journey_replay_restart_and_account_isolation(tmp_path):
    path = str(tmp_path / "integration.db")
    app = create_app(Settings(database_path=path))
    health = {"record_id": str(UUID(int=1)), "recorded_at": "2026-01-01T00:00:00Z",
              "schema_version": 1, "type": "health_record", "payload": {"heart_rate_bpm": 70}}
    wellbeing = {"record_id": str(UUID(int=2)), "recorded_at": "2026-01-01T00:00:00Z",
                 "schema_version": 1, "type": "wellbeing_checkin",
                 "payload": {"mood": 1, "connection": 2, "energy": 3, "purpose": 4, "sleep": 5}}
    batch = {"device_id": "synthetic-device", "records": [health, wellbeing]}

    async def exercise():
        async with app.router.lifespan_context(app):
            provision_account(app.state.database, "synthetic-a", "test-password", "Demo A", "demo")
            provision_account(app.state.database, "synthetic-b", "test-password", "Demo B", "demo")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
                response = await c.get("/api/v1/health")
                assert response.status_code == 200
                assert_schema(response.json(), "HealthResponse")
                credentials = {}
                for name in ("synthetic-a", "synthetic-b"):
                    response = await c.post("/api/v1/auth/login", json={
                        "username": name, "password": "test-password", "device_id": "synthetic-device"})
                    assert response.status_code == 200
                    assert_schema(response.json(), "LoginResponse")
                    credentials[name] = response.json()
                a = {"Authorization": "Bearer " + credentials["synthetic-a"]["access_token"]}
                b = {"Authorization": "Bearer " + credentials["synthetic-b"]["access_token"]}
                response = await c.post("/api/v1/sync/records", headers=a, json=batch)
                assert response.status_code == 200
                assert_schema(response.json(), "SyncBatchResponse")
                assert [item["status"] for item in response.json()["results"]] == ["accepted", "accepted"]
                for headers, expected in ((a, [health["record_id"], wellbeing["record_id"]]), (b, [])):
                    response = await c.get("/api/v1/users/me/bootstrap", headers=headers)
                    assert response.status_code == 200
                    assert_schema(response.json(), "BootstrapPage")
                    page = response.json()
                    assert [r["record_id"] for r in page["health_records"] + page["wellbeing_checkins"]] == expected
                    for endpoint, schema in (("health-records", "HealthPage"),
                                             ("wellbeing-checkins", "WellbeingPage")):
                        response = await c.get("/api/v1/users/me/" + endpoint, headers=headers)
                        assert response.status_code == 200
                        assert_schema(response.json(), schema)
                        assert len(response.json()["items"]) == (1 if headers == a else 0)
                    response = await c.get("/api/v1/users/me/alerts", headers=headers)
                    assert response.status_code == 200 and response.json() == {"items": []}
                response = await c.post("/api/v1/sync/records", headers=b, json=batch)
                assert [item["status"] for item in response.json()["results"]] == ["conflict", "conflict"]
                changed = copy.deepcopy(health)
                changed["payload"]["heart_rate_bpm"] = 71
                response = await c.post("/api/v1/sync/records", headers=a, json={
                    "device_id": "synthetic-device", "records": [changed]})
                assert response.json()["results"][0]["status"] == "conflict"
                assert (await c.post("/api/v1/auth/logout", headers=a)).status_code == 204
                for endpoint in ("users/me", "users/me/bootstrap", "users/me/health-records",
                                 "users/me/wellbeing-checkins", "users/me/alerts"):
                    response = await c.get("/api/v1/" + endpoint, headers=a)
                    assert response.status_code == 401
                    assert_schema(response.json(), "ApiError")
                response = await c.post("/api/v1/sync/records", headers=a, json=batch)
                assert response.status_code == 401
                assert_schema(response.json(), "ApiError")
        reopened = create_app(Settings(database_path=path))
        async with reopened.router.lifespan_context(reopened):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=reopened), base_url="http://test") as c:
                response = await c.post("/api/v1/auth/login", json={"username": "synthetic-a",
                    "password": "test-password", "device_id": "synthetic-device"})
                headers = {"Authorization": "Bearer " + response.json()["access_token"]}
                response = await c.post("/api/v1/sync/records", headers=headers, json=batch)
                assert response.status_code == 200
                assert_schema(response.json(), "SyncBatchResponse")
                assert [item["status"] for item in response.json()["results"]] == ["duplicate", "duplicate"]
                response = await c.post("/api/v1/sync/records", headers=headers, json={
                    "device_id": "synthetic-device", "records": [health] * 21})
                assert response.status_code == 422
                assert_schema(response.json(), "ApiError")

    asyncio.run(exercise())
