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

## Deployment preparation

The included Dockerfile packages the backend for Python 3.12 and runs one
Uvicorn process as an unprivileged user. Compose publishes the container port
only at `127.0.0.1:8000` and stores SQLite at `/data/eir.sqlite3` in the
`eir-data` named volume. Keep one backend instance: SQLite and the current
single-process application are not a multi-host deployment design. The volume
contains account, session and synthetic record data; protect it and its
backups. Do not remove it when recreating the container. Back up SQLite using
its online backup API or while the backend is stopped; include a tested restore
procedure. The image contains no preconfigured accounts.

On an Ubuntu host with Docker Engine and the Compose plugin installed, from a
checkout of this project run:

```sh
docker compose up -d --build
docker compose exec backend python -m eir.auth demo "Synthetic Demo" demo-mission
curl --fail http://127.0.0.1:8000/api/v1/health
```

The interactive provisioning command prompts twice for a password; use only
synthetic accounts and do not put passwords in command arguments or logs.
Account provisioning is needed once per account, not on every restart. Check
`docker compose ps` and the health response `{"status":"ok"}`; health means
API availability, not a clinical assessment.

For the planned EC2 deployment, configure the host firewall and security group
to allow public TCP 80 and 443, restrict SSH to authorized sources, and do not
open 8000. Point the chosen API DNS name at the host's public IP using Cloudflare
DNS only initially. Install Caddy on the host and replace its site configuration
with the actual DNS name, for example:

```caddyfile
api.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

Use the real domain, validate the Caddy configuration and reload Caddy. Verify
public DNS, inbound 80/443 and Caddy's certificate issuance, then request
`https://<actual-api-domain>/api/v1/health` from an external client with normal
TLS verification. Android should use the corresponding HTTPS base URL and
verify certificates normally. If Cloudflare proxying is enabled later, use Full
(strict). DNS, EC2, Caddy, certificates and external HTTPS have not been
configured or verified by this change; LAN certificate provisioning remains
future work. The image and Compose setup require an actual Docker build and
runtime check on a host with a working Docker daemon.
