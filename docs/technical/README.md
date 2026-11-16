# EIR Backend Technical Documentation

This guide describes the repository code reviewed on November 15, 2026. It covers the backend only and uses synthetic data. The approved contract is [OpenAPI](../../contracts/openapi.yaml); functional decisions are in [EIR_HANDOFF](../EIR_HANDOFF.md) and [DECISIONS](../DECISIONS.md). Contract approval does not mean that all its capabilities are implemented. The root README provides a project overview; this guide describes current backend behavior in more detail.

Recommended reading order:

1. [Overview](01-overview.md): purpose, scope, and limitations.
2. [Architecture](02-architecture.md): components, dependencies, and flows.
3. [Database](03-database.md): actual schema, migrations, and integrity.
4. [REST API](04-api.md): operations, examples, and differences from the contract.
5. [Security](05-security.md): authentication, sessions, and risks.
6. [Synchronization](06-synchronization.md): idempotency and Android responsibilities.
7. [Deployment](07-deployment.md): Docker, configuration, and infrastructure plan.
8. [Tests](08-testing.md): commands, results, and functional coverage.
9. [Status and limitations](09-status-and-limitations.md): classification and priorities.

Primary evidence linked in each document takes precedence over historical descriptions. Tests do not prove complete security or clinical validity.
