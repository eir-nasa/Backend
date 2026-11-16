# 08 — Tests and Validation

The project uses pytest, FastAPI TestClient/httpx, PyYAML, jsonschema, and openapi-spec-validator; Ruff checks selected rules E4, E7, E9, F, and I. Dependencies are declared in [pyproject.toml](../../pyproject.toml). The `test_backend_*` tests cover the application; `test_orchestrator`, `test_pr_recovery`, and `test_ruleset_validation` cover governance infrastructure without executing the roadmap.

Commands run from the repository root on November 15, 2026, using the existing virtual environment and disabling the pytest/Ruff caches:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check --no-cache src tests orchestration
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m orchestration.validate_contract
docker compose config --quiet
```

Actual results: **79 passed in 2.70 s**; Ruff reported `All checks passed!`; the validator reported `OpenAPI validated and lock verified`; Compose config exited with code 0. The system Python lacks pytest, Ruff, and PyYAML, but the existing virtual environment supported the commands above. `docker info` failed because of socket permissions; no image build or real container test was performed. `mmdc` was not found, so the diagrams were not checked with a Mermaid renderer.

Functional behavior exercised by tests: authentication, expiration, rotation, sessions, and isolation; configuration, lifecycle, and migration rollback; validation and pagination for both record types, bootstrap, existing alerts, and absence of alert generation; sync, replay, conflict, and storage failure; synthetic end-to-end flow with restart. Deployment tests inspect files and run the app command locally; they do not build an image. Integration tests compare OpenAPI route inventory and operationId, profile schema, and some responses against JSON Schema; the validator checks the specification and hash, not full equivalence with FastAPI. See [test_backend_integration.py](../../tests/test_backend_integration.py).

No coverage percentage was measured here. Tests do not verify Android, real concurrent access, exhaustive security, performance, external connectivity, TLS, or AWS deployment. Passing tests also do not establish clinical validation.
