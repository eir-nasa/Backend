"""Experimental self-reported wellbeing storage and authorized history."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from eir.auth import _unauthorized, authenticated_session
from eir.health_records import _cursor_decode, _cursor_encode

router = APIRouter(prefix="/api/v1/users")


class WellbeingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mood: int = Field(ge=1, le=5)
    connection: int = Field(ge=1, le=5)
    energy: int = Field(ge=1, le=5)
    purpose: int = Field(ge=1, le=5)
    sleep: int = Field(ge=1, le=5)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def note_must_be_string(cls, value):
        if not isinstance(value, str):
            raise ValueError("note must be a string")
        return value


class WellbeingRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_id: UUID
    recorded_at: datetime
    schema_version: StrictInt = Field(ge=1, le=1)
    type: Literal["wellbeing_checkin"]
    payload: WellbeingPayload

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


def store_wellbeing_checkin(connection: sqlite3.Connection, owner_id: str, record: WellbeingRecord) -> str:
    """Persist a validated immutable check-in for an authenticated owner."""
    data = record.model_dump(mode="json", exclude_unset=True)
    data["recorded_at"] = record.recorded_at.astimezone(UTC).isoformat()
    data["payload"] = record.payload.model_dump(mode="json", exclude_unset=True)
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)
    record_id = str(record.record_id)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT owner_id, record_json FROM wellbeing_checkins WHERE record_id = ?", (record_id,)
        ).fetchone()
        if existing:
            status = "duplicate" if existing == (owner_id, encoded) else "conflict"
        elif connection.execute(
            "SELECT 1 FROM health_records WHERE record_id = ?", (record_id,)
        ).fetchone():
            status = "conflict"
        else:
            connection.execute(
                "INSERT INTO wellbeing_checkins (record_id, owner_id, record_json, received_at) "
                "VALUES (?, ?, ?, ?)",
                (record_id, owner_id, encoded, datetime.now(UTC).isoformat()),
            )
            status = "accepted"
        connection.commit()
        return status
    except BaseException:
        connection.rollback()
        raise


@router.get("/me/wellbeing-checkins", operation_id="getMyWellbeingCheckins")
async def get_wellbeing_checkins(
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
        "SELECT record_id, record_json, received_at FROM wellbeing_checkins "
        "WHERE owner_id = ? AND record_id > ? ORDER BY record_id LIMIT ?",
        (session[1], after, limit + 1),
    ).fetchall()
    items = [{**json.loads(row[1]), "received_at": row[2]} for row in rows[:limit]]
    return {"items": items, "next_cursor": _cursor_encode(rows[limit - 1][0]) if len(rows) > limit else None}
