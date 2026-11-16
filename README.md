# EIR Backend

Demonstration backend for **EIR**, a health and wellbeing monitoring application for astronauts developed in the context of NASA Space Apps Challenge 2026. It provides a REST API for synthetic accounts, health and wellbeing records, synchronization, and retrieval of existing alerts.

Measurements and self-reports are experimental; they are not diagnoses or clinically validated capabilities. This repository is intended for synthetic demonstration data and must not contain real astronaut or patient information.

## Scope

The backend implements online device authentication, session rotation and revocation, profile and history queries, and record uploads with stable identifiers and per-record results. Existing alerts can be read, but **alerts are not generated and there is no Risk Engine**: rules and thresholds are pending approval.

Android is responsible for Room, the durable outbox, and offline mechanisms. Apollo is intended to run locally on Android through Google AI Edge; this backend does not run model inference. The Android implementation and its integration are outside this repository.

The API contains the ten operations in the [approved OpenAPI contract](contracts/openapi.yaml). FastAPI's generated OpenAPI document differs from the contract in schemas, security, and response codes; see [REST API](docs/technical/04-api.md) before generating clients. The contract's note questioning its approval is outdated, as explained in [DECISIONS.md](docs/DECISIONS.md).

## Technologies and structure

- Python 3.11+, FastAPI, Pydantic, and Uvicorn.
- SQLite with migrations applied at application startup.
- Docker and Docker Compose for prepared local execution.
- pytest, Ruff, and OpenAPI validation for development checks.

| Path | Contents |
|---|---|
| `src/eir/` | Application, authentication, profiles, records, synchronization, alerts, and database. |
| `contracts/` | Approved OpenAPI contract and integrity file. |
| `tests/` | Backend and automation infrastructure tests. |
| `docs/` | Decisions, handoff, status, and technical documentation. |
| `orchestration/` | Repository automation infrastructure and governance. |
| `Dockerfile`, `compose.yaml` | Service build and run definitions. |

## Local execution

Create a virtual environment and install the package with its development dependencies:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Start the server and check its availability:

```sh
uvicorn eir.main:app
```

```sh
curl --fail http://127.0.0.1:8000/api/v1/health
```

The expected response is `{"status":"ok"}`. This endpoint checks API availability, not a person's health. The `EIR_DATABASE_PATH` setting selects the SQLite file; its default is `eir.sqlite3` in the working directory. Pending migrations are applied at startup.

There are no default accounts or public registration. To create a synthetic demonstration account, run:

```sh
python -m eir.auth demo "Synthetic Demo" demo-mission
```

The command prompts for and confirms the password without displaying it. Do not put passwords or tokens in command arguments, version-controlled files, or logs. The SQLite file contains account, session, and record information and must be protected along with its backups.

## Docker Compose

With Docker Engine and the Compose plugin installed:

```sh
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8000/api/v1/health
```

Compose publishes the service at `127.0.0.1:8000` and stores the database in the `eir-data` volume mounted at `/data`. To provision an account inside the container:

```sh
docker compose exec backend python -m eir.auth demo "Synthetic Demo" demo-mission
```

The EC2, Cloudflare DNS, and Caddy plan is documented, but external deployment and HTTPS have not been verified. See [Docker and deployment](docs/technical/07-deployment.md) for persistence, backups, and outstanding requirements.

## Tests

With development dependencies installed:

```sh
python -m pytest -q tests
python -m ruff check src tests orchestration
python -m orchestration.validate_contract
```

Contract validation checks its structure and lock; it does not by itself prove full implementation compatibility. Test results and limitations are described in [tests and validation](docs/technical/08-testing.md).

## Documentation

The [technical documentation](docs/technical/README.md) covers architecture, database, API, security, synchronization, deployment, tests, and implementation status. Functional decisions are in [EIR_HANDOFF.md](docs/EIR_HANDOFF.md) and [DECISIONS.md](docs/DECISIONS.md); the [implementation status](docs/IMPLEMENTATION_STATUS.md) records additional limitations.
