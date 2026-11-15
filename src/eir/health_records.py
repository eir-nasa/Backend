"""Physical-health validation, persistence, and authorized history."""

import base64
import binascii
import json
import sqlite3
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from eir.auth import _unauthorized, authenticated_session

router = APIRouter(prefix="/api/v1/users")


class HealthPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    heart_rate_bpm: int | None = Field(default=None, ge=0)
    glucose_mg_dl: float | None = Field(default=None, ge=0)
    temperature_c: float | None = None
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    systolic_bp_mmhg: int | None = Field(default=None, ge=0)
    diastolic_bp_mmhg: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def nonempty_and_nonnull(cls, value):
        if not isinstance(value, dict) or not value or any(v is None for v in value.values()):
            raise ValueError("Health payload must contain at least one non-null field")
        return value


class HealthRecord(BaseModel):
    # RecordBase and HealthSyncRecord permit additional properties in the contract.
    model_config = ConfigDict(extra="allow")

    record_id: UUID
    recorded_at: datetime
    schema_version: StrictInt = Field(ge=1, le=1)
    type: Literal["health_record"]
    payload: HealthPayload

    @field_validator("recorded_at", mode="before")
    @classmethod
    def datetime_string(cls, value):
        if not isinstance(value, str) or "T" not in value.upper():
            raise ValueError("recorded_at must be a date-time string")
        return value

    @field_validator("recorded_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must include a timezone")
        return value


def store_health_record(connection: sqlite3.Connection, owner_id: str, record: HealthRecord) -> str:
    """Atomically insert a validated immutable record or identify its replay/conflict.

    The caller must derive owner_id from a verified session and provide a validated
    HealthRecord. The global primary key is also the deduplication marker.
    """
    data = record.model_dump(mode="json", exclude_unset=True)
    data["recorded_at"] = record.recorded_at.astimezone(UTC).isoformat()
    data["payload"] = record.payload.model_dump(mode="json", exclude_unset=True)
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    record_id = str(record.record_id)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT owner_id, record_json FROM health_records WHERE record_id = ?", (record_id,)
        ).fetchone()
        if existing:
            status = "duplicate" if existing == (owner_id, encoded) else "conflict"
        elif connection.execute(
            "SELECT 1 FROM wellbeing_checkins WHERE record_id = ?", (record_id,)
        ).fetchone():
            status = "conflict"
        else:
            connection.execute(
                "INSERT INTO health_records (record_id, owner_id, record_json, received_at) "
                "VALUES (?, ?, ?, ?)",
                (record_id, owner_id, encoded, datetime.now(UTC).isoformat()),
            )
            status = "accepted"
        connection.commit()
        return status
    except BaseException:
        connection.rollback()
        raise


def _cursor_encode(record_id: str) -> str:
    return base64.urlsafe_b64encode(record_id.encode("ascii")).decode("ascii").rstrip("=")


def _cursor_decode(cursor: str) -> str:
    try:
        decoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        value = decoded.decode("ascii")
        if str(UUID(value)) != value or _cursor_encode(value) != cursor:
            raise ValueError("invalid cursor")
        return value
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("invalid cursor") from exc


@router.get("/me/health-records", operation_id="getMyHealthRecords")
async def get_health_records(
    request: Request,
    authorization: str | None = Header(default=None),
    cursor: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    connection = request.app.state.database
    session = authenticated_session(connection, authorization)
    if session is None:
        return _unauthorized()
    try:
        after = _cursor_decode(cursor) if cursor is not None else ""
    except ValueError:
        return JSONResponse(status_code=422, content={"code": "invalid_cursor", "message": "Invalid cursor"})
    rows = connection.execute(
        "SELECT record_id, record_json, received_at FROM health_records "
        "WHERE owner_id = ? AND record_id > ? ORDER BY record_id LIMIT ?",
        (session[1], after, limit + 1),
    ).fetchall()
    items = [{**json.loads(row[1]), "received_at": row[2]} for row in rows[:limit]]
    return {"items": items, "next_cursor": _cursor_encode(rows[limit - 1][0]) if len(rows) > limit else None}
