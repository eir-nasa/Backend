"""Authenticated account profiles."""

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from eir.auth import _unauthorized, authenticated_session

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
