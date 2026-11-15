"""Upload-only synchronization of immutable records."""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from eir.auth import _unauthorized, authenticated_session
from eir.health_records import HealthRecord, store_health_record
from eir.wellbeing import WellbeingRecord, store_wellbeing_checkin

router = APIRouter(prefix="/api/v1/sync")


def _invalid_batch():
    return JSONResponse(status_code=422, content={"code": "invalid_batch", "message": "Invalid sync batch"})


@router.post("/records", operation_id="pushRecords")
async def push_records(request: Request, authorization: str | None = Header(default=None)):
    connection = request.app.state.database
    session = authenticated_session(connection, authorization)
    if session is None:
        return _unauthorized()
    try:
        batch = await request.json()
    except (ValueError, UnicodeDecodeError):
        return _invalid_batch()
    if (not isinstance(batch, dict) or set(batch) != {"device_id", "records"}
            or not isinstance(batch["device_id"], str) or not 1 <= len(batch["device_id"]) <= 128
            or not isinstance(batch["records"], list) or not 1 <= len(batch["records"]) <= 20):
        return _invalid_batch()

    # Every response item requires a UUID, so check all identifiers before writes.
    ids = []
    for item in batch["records"]:
        try:
            if not isinstance(item, dict) or not isinstance(item.get("record_id"), str):
                return _invalid_batch()
            ids.append(str(UUID(item["record_id"])))
        except ValueError:
            return _invalid_batch()

    results = []
    for item, record_id in zip(batch["records"], ids):
        try:
            if item.get("type") == "health_record":
                record = HealthRecord.model_validate(item)
                store = store_health_record
            elif item.get("type") == "wellbeing_checkin":
                record = WellbeingRecord.model_validate(item)
                store = store_wellbeing_checkin
            else:
                raise ValueError("Unknown record type")
        except (ValidationError, ValueError):
            results.append({"record_id": record_id, "status": "rejected",
                            "error": {"code": "invalid_record", "message": "Invalid record"}})
            continue
        try:
            status = store(connection, session[1], record)
            results.append({"record_id": record_id, "status": status})
        except sqlite3.Error:
            results.append({"record_id": record_id, "status": "retryable",
                            "error": {"code": "storage_unavailable", "message": "Storage unavailable",
                                      "retryable": True}})
    return {"results": results, "server_time": datetime.now(UTC).isoformat()}
