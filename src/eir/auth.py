"""Synthetic account provisioning and device-bound online sessions."""

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from eir.config import Settings
from eir.database import open_database

ACCESS_SECONDS = 900
REFRESH_SECONDS = 30 * 24 * 60 * 60
router = APIRouter(prefix="/api/v1/auth")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: StrictStr = Field(min_length=1)
    password: StrictStr = Field(min_length=1)
    device_id: StrictStr = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: StrictStr = Field(min_length=1)
    device_id: StrictStr = Field(min_length=1)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt$16384$8$1${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = stored.split("$")
        if (algorithm, n, r, p) != ("scrypt", "16384", "8", "1"):
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(digest, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def provision_account(connection, username, password, display_name, mission_id):
    """Create a synthetic account; caller supplies and protects its credentials."""
    if not all((username, password, display_name, mission_id)):
        raise ValueError("Account fields must not be empty")
    user_id, astronaut_id = str(uuid.uuid4()), str(uuid.uuid4())
    with connection:
        connection.execute(
            "INSERT INTO auth_accounts VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, astronaut_id, username, hash_password(password), display_name, mission_id),
        )
    return user_id


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(data: str) -> bytes:
    return base64.b64decode(data + "=" * (-len(data) % 4), altchars=b"-_", validate=True)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _tokens(connection, session_id, now):
    key = secrets.token_bytes(32)
    header = _encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = _encode(json.dumps({"sid": session_id, "exp": now + ACCESS_SECONDS},
                                 separators=(",", ":")).encode())
    signed = f"{header}.{payload}"
    access = f"{signed}.{_encode(hmac.digest(key, signed.encode(), 'sha256'))}"
    refresh = secrets.token_urlsafe(32)
    connection.execute(
        "UPDATE auth_sessions SET signing_key = ?, refresh_hash = ?, refresh_expires_at = ? "
        "WHERE session_id = ?", (key, _digest(refresh), now + REFRESH_SECONDS, session_id)
    )
    return {"access_token": access, "refresh_token": refresh,
            "token_type": "Bearer", "expires_in": ACCESS_SECONDS}


def _unauthorized():
    return JSONResponse(status_code=401, content={"code": "unauthorized", "message": "Invalid credentials"},
                        headers={"WWW-Authenticate": "Bearer"})


def authenticated_session(connection, authorization):
    """Return the verified session and owner ID, or None for any invalid bearer."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        header, payload, signature = parts[1].split(".")
        if json.loads(_decode(header)) != {"alg": "HS256", "typ": "JWT"}:
            return None
        claims = json.loads(_decode(payload))
        if not isinstance(claims, dict) or not isinstance(claims.get("sid"), str):
            return None
        if type(claims.get("exp")) is not int or claims["exp"] <= int(time.time()):
            return None
        row = connection.execute(
            "SELECT session_id, user_id, signing_key FROM auth_sessions WHERE session_id = ?",
            (claims["sid"],),
        ).fetchone()
        if row is None or not hmac.compare_digest(
            hmac.digest(row[2], f"{header}.{payload}".encode(), "sha256"), _decode(signature)
        ):
            return None
        return row[:2]
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None


@router.post("/login", operation_id="login")
async def login(body: LoginRequest, request: Request):
    connection = request.app.state.database
    account = connection.execute(
        "SELECT user_id, astronaut_id, username, password_hash, display_name, mission_id, "
        "profile_version FROM auth_accounts WHERE username = ?", (body.username,)
    ).fetchone()
    # Perform a password derivation for unknown usernames as well.
    stored = account[3] if account else _DUMMY_HASH
    if not verify_password(body.password, stored) or account is None:
        return _unauthorized()
    now = int(time.time())
    session_id = str(uuid.uuid4())
    with connection:
        connection.execute("INSERT INTO auth_sessions (session_id, user_id, device_id) VALUES (?, ?, ?)",
                           (session_id, account[0], body.device_id))
        tokens = _tokens(connection, session_id, now)
    return {**tokens, "user": dict(zip(
        ("user_id", "astronaut_id", "username", "display_name", "mission_id", "profile_version"),
        (account[0], account[1], account[2], account[4], account[5], account[6]),
    )), "online_authenticated_at": datetime.fromtimestamp(now, UTC).isoformat()}


@router.post("/refresh", operation_id="refreshSession")
async def refresh(body: RefreshRequest, request: Request):
    connection = request.app.state.database
    now = int(time.time())
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT session_id FROM auth_sessions WHERE refresh_hash = ? AND device_id = ? "
            "AND refresh_expires_at > ?", (_digest(body.refresh_token), body.device_id, now)
        ).fetchone()
        if row is None:
            connection.rollback()
            return _unauthorized()
        tokens = _tokens(connection, row[0], now)
        connection.commit()
        return tokens
    except BaseException:
        connection.rollback()
        raise


@router.post("/logout", operation_id="logout")
async def logout(request: Request, authorization: str | None = Header(default=None)):
    connection = request.app.state.database
    session = authenticated_session(connection, authorization)
    if session is None:
        return _unauthorized()
    with connection:
        connection.execute("DELETE FROM auth_sessions WHERE session_id = ?", (session[0],))
    return Response(status_code=204)


# Fixed dummy salt, not an account or a usable credential.
_DUMMY_HASH = "scrypt$16384$8$1$00000000000000000000000000000000$" + "00" * 64


def main():
    parser = argparse.ArgumentParser(description="Provision a synthetic demonstration account")
    parser.add_argument("username")
    parser.add_argument("display_name")
    parser.add_argument("mission_id")
    args = parser.parse_args()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match")
    connection = open_database(Settings.from_environment().database_path)
    try:
        provision_account(connection, args.username, password, args.display_name, args.mission_id)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
