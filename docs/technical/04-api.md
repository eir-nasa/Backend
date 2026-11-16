# 04 — REST API

The [approved contract](../../contracts/openapi.yaml) is normative; this page describes observed behavior in the [routers](../../src/eir/). All routes use `/api/v1`. Interactive documentation and the OpenAPI HTTP endpoint are disabled: `docs_url`, `redoc_url`, and `openapi_url` are turned off. Custom error responses use `{"code":"unauthorized","message":"Invalid credentials"}` for 401, with `WWW-Authenticate: Bearer`. FastAPI validation failures return 422 with `detail`, a structure different from `ApiError`.

| Method and route | Auth | Request | Observable response / errors |
|---|---|---|---|
| GET `/health` | No | No body | 200 `{"status":"ok"}` |
| POST `/auth/login` | No | JSON `username`, `password`, `device_id`; non-empty strings, device max 128; no extras | 200 tokens, `user`, and `online_authenticated_at`; 401 invalid credentials; 422 validation |
| POST `/auth/refresh` | No | JSON `refresh_token`, `device_id`, non-empty strings, no extras | 200 rotated tokens; 401 invalid token, device, or expiry; 422 validation |
| POST `/auth/logout` | Bearer | No required body | 204 no body; 401 invalid or already revoked session |
| GET `/users/me` | Bearer | No body | 200 profile; 401 |
| GET `/users/me/bootstrap` | Bearer | Optional `cursor`, `limit` 1–100, default 30 | 200 profile, `health_records`, `wellbeing_checkins`, `next_cursor`; 401; 422 invalid cursor or limit |
| GET `/users/me/health-records` | Bearer | Same cursor/limit | 200 `items`, `next_cursor`; 401; 422 |
| GET `/users/me/wellbeing-checkins` | Bearer | Same cursor/limit | 200 `items`, `next_cursor`; 401; 422 |
| GET `/users/me/alerts` | Bearer | No body | 200 `items`; 401. Returns existing alerts only, with no pagination or generation |
| POST `/sync/records` | Bearer | `device_id` and `records`; see below | 200 `results`, `server_time`; 401; 422 `invalid_batch` for invalid JSON/envelope/UUID |

Profile fields: `user_id`, `astronaut_id`, `username`, `display_name`, `mission_id`, `profile_version`. Login adds `access_token`, `refresh_token`, `token_type: Bearer`, `expires_in: 900`, and UTC `online_authenticated_at`; refresh returns these four session fields. Credentials are not reproduced in examples. To test login, provide a synthetic password interactively without recording it in shell history. Use a client that protects the token when sending `Authorization: Bearer <access_token>`.

Synthetic sync example (the UUID is illustrative):

```json
{"device_id":"demo-device","records":[{"record_id":"550e8400-e29b-41d4-a716-446655440000","recorded_at":"2026-01-01T12:00:00Z","schema_version":1,"type":"health_record","payload":{"heart_rate_bpm":70}}]}
```

Illustrative response: `{"results":[{"record_id":"550e8400-e29b-41d4-a716-446655440000","status":"accepted"}],"server_time":"2026-01-01T12:00:01+00:00"}`. An equivalent replay returns `duplicate`; different data or a collision with another account/type returns `conflict`; an invalid individual record returns `rejected`; a SQLite failure returns `retryable`. An invalid UUID invalidates the entire batch before any write. `device_id` must be 1–128 characters, `records` must contain 1–20 items, and extra envelope keys are not allowed. The batch `device_id` is not checked against the session's device.

Each record requires a UUID, ISO timestamp with timezone, strict integer `schema_version` equal to 1, type, and payload. `health_record`: at least one of `heart_rate_bpm`, `glucose_mg_dl`, `temperature_c`, `sleep_hours`, `systolic_bp_mmhg`, or `diastolic_bp_mmhg`; finite numeric values, non-negative except temperature; sleep 0–24; heart rate and blood pressure values must be integers. `wellbeing_checkin`: `mood`, `connection`, `energy`, `purpose`, and `sleep` integers from 1 to 5, plus an optional string `note` up to 500 characters. Payloads reject extra fields and nulls; the record envelope allows extra fields. Timestamps are stored normalized to UTC, and history responses add `received_at`. Cursors are opaque, records are ordered by textual UUID, and there is no snapshot; bootstrap shares the limit across both types.

Existing alerts have `alert_id`, `severity` (`info`, `warning`, `critical`), `rule_id`, `explanation`, `created_at`, and optional `evidence_record_ids`. An example empty response is `{"items":[]}`; this does not demonstrate that any evaluation occurred.

## Compatibility

Tests compare route inventory and operationId, the profile schema, and some response instances against the baseline, but not all semantics. `app.openapi()` omits the Bearer scheme, sync request, and several schemas and status codes; it describes logout as 200 although the endpoint returns 204. The contract declares 429 for login and sync, but there is no rate limiting; sync 400, 413, and 503 are also not explicitly implemented as application responses. The implementation emits FastAPI 422 validation responses on routes where the contract does not document them, and that format is not `ApiError`. These observations may not be exhaustive; complete conformance tests are missing. The contract text that denies approval is outdated, as explained in [DECISIONS](../DECISIONS.md).
