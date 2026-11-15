"""Authenticated account profiles."""

import json

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from eir.auth import _unauthorized, authenticated_session
from eir.health_records import _cursor_decode, _cursor_encode

router = APIRouter(prefix="/api/v1/users")


class AstronautProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    astronaut_id: str
    username: str
    display_name: str
    mission_id: str
    profile_version: int = Field(ge=1)


@router.get("/me", response_model=AstronautProfile, operation_id="getMe")
async def get_me(request: Request, authorization: str | None = Header(default=None)):
    connection = request.app.state.database
    session = authenticated_session(connection, authorization)
    if session is None:
        return _unauthorized()
    account = connection.execute(
        "SELECT user_id, astronaut_id, username, display_name, mission_id, profile_version "
        "FROM auth_accounts WHERE user_id = ?", (session[1],)
    ).fetchone()
    if account is None:
        return _unauthorized()
    return AstronautProfile(**dict(zip(AstronautProfile.model_fields, account)))


@router.get("/me/bootstrap", operation_id="getBootstrapPage")
async def get_bootstrap(
    request: Request,
    authorization: str | None = Header(default=None),
    cursor: str | None = None,
    limit: int = Query(default=30, ge=1, le=100),
):
    connection = request.app.state.database
    session = authenticated_session(connection, authorization)
    if session is None:
        return _unauthorized()
    account = connection.execute(
        "SELECT user_id, astronaut_id, username, display_name, mission_id, profile_version "
        "FROM auth_accounts WHERE user_id = ?", (session[1],)
    ).fetchone()
    if account is None:
        return _unauthorized()
    try:
        after = _cursor_decode(cursor) if cursor is not None else ""
    except ValueError:
        return JSONResponse(status_code=422, content={"code": "invalid_cursor", "message": "Invalid cursor"})
    rows = connection.execute(
        "SELECT record_id, record_json, received_at, 'health' AS kind FROM health_records "
        "WHERE owner_id = ? AND record_id > ? UNION ALL "
        "SELECT record_id, record_json, received_at, 'wellbeing' AS kind FROM wellbeing_checkins "
        "WHERE owner_id = ? AND record_id > ? ORDER BY record_id LIMIT ?",
        (session[1], after, session[1], after, limit + 1),
    ).fetchall()
    health, wellbeing = [], []
    for _, record_json, received_at, kind in rows[:limit]:
        item = {**json.loads(record_json), "received_at": received_at}
        (health if kind == "health" else wellbeing).append(item)
    return {
        "profile": AstronautProfile(**dict(zip(AstronautProfile.model_fields, account))),
        "health_records": health,
        "wellbeing_checkins": wellbeing,
        "next_cursor": _cursor_encode(rows[limit - 1][0]) if len(rows) > limit else None,
    }
