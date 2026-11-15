# EIR backend implementation status

The FastAPI foundation implements `GET /api/v1/health` and the contract's
`POST /api/v1/auth/login`, `/refresh`, and `/logout` operations. Run it with
`uvicorn eir.main:app`; `EIR_DATABASE_PATH` selects the SQLite file (default:
`eir.sqlite3`). Startup applies ordered transactional SQLite schema migrations
and fails if the database cannot be opened or has a newer schema.

There is no public registration or default account. Provision synthetic demo
accounts locally with `python -m eir.auth USERNAME DISPLAY_NAME MISSION_ID`;
the command prompts for a password without echoing it. Account passwords use
salted scrypt hashes. Each login creates a separate device-bound session. Access
JWTs expire after 15 minutes; refresh tokens expire after 30 days and rotate on
use, invalidating the previous access and refresh tokens. Logout revokes that
session. Only refresh-token hashes are stored; session signing keys and account
information remain in the SQLite database, which requires appropriate filesystem
protection. These token lifetimes are implementation choices pending policy
validation; refresh does not issue a new online authentication timestamp or
extend the Android offline window.

Focused tests exercise authentication, revocation, expiry, device isolation,
health, configuration, database lifecycle, migration rollback and startup
failures. Login rate limiting is not implemented. Offline unlock and Android
cache/outbox handling remain Android responsibilities and are not implemented
here. Authenticated profile, physical-health history and wellbeing history are
implemented. Both record types have validated SQLite storage, immutable IDs and
owner-scoped pagination, connected to the upload-only sync endpoint. Wellbeing dimensions are experimental self-reports,
not clinically validated scores. Bootstrap returns the authenticated profile and
a combined page of both history types, ordered by record ID, with the limit
applied across both arrays. The authenticated alerts endpoint returns stored
alerts belonging to the current account. **BLOCKED:** alert generation and
rule thresholds are not specified or approved; no risk rules are implemented.
The endpoint can therefore return an empty list and does not imply that records
have been assessed.
History and bootstrap use record-ID ordering and opaque cursors; pages are not a
consistent snapshot when records are added between requests. Records inserted
before a continuation cursor will not appear in later pages.

Integration tests exercise synthetic login, sync, isolation, history, logout,
restart and replay, and validate observed response bodies against baseline JSON
schemas. Generated OpenAPI operation paths and IDs match the baseline, as does
the profile schema. **OpenAPI compatibility remains incomplete:** FastAPI's
generated document omits the bearer security scheme, the sync request schema,
several response schemas and documented status codes, and describes logout as
200 instead of 204. The OpenAPI HTTP endpoint is disabled; the inspection uses
`app.openapi()`. Matching operation inventory and tested response instances do
not establish full semantic compatibility. Login rate limiting is not implemented.
