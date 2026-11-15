"""Owner-scoped retrieval of existing risk alerts."""

import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict

from eir.auth import _unauthorized, authenticated_session

router = APIRouter(prefix="/api/v1/users")


class RiskAlert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_id: str
    severity: Literal["info", "warning", "critical"]
    rule_id: str
    explanation: str
    created_at: datetime
    evidence_record_ids: list[UUID] = []


@router.get("/me/alerts", operation_id="getMyAlerts")
async def get_alerts(request: Request, authorization: str | None = Header(default=None)):
    connection = request.app.state.database
    session = authenticated_session(connection, authorization)
    if session is None:
        return _unauthorized()
    rows = connection.execute(
        "SELECT alert_json FROM risk_alerts WHERE owner_id = ? ORDER BY alert_id", (session[1],)
    ).fetchall()
    items = [RiskAlert.model_validate(json.loads(row[0])).model_dump(mode="json", exclude_unset=True)
             for row in rows]
    return {"items": items}
