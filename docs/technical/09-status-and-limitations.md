# 09 — Implementation Status and Limitations

This classification is based on code and local tests described in [tests](08-testing.md); “verified” means for the tested scenarios, not certified for production.

| Status | Functionality and evidence |
|---|---|
| Implemented and verified | Health, configuration, and transactional migrations: [foundation](../../tests/test_backend_foundation.py). Login, rotation, expiration, logout, and session separation: [auth](../../tests/test_backend_auth.py). Account-scoped profile and history, bootstrap, sync replay/conflict, and persistence/restart: [integration](../../tests/test_backend_integration.py), plus sync and history tests. |
| Implemented and verified | Account-scoped retrieval of existing alerts and no alert generation when saving records: [alerts tests](../../tests/test_backend_alerts.py). |
| Partial | OpenAPI compatibility: routes and IDs match and examples are validated; the generated document lacks a security scheme, schemas, and status codes, and describes logout as 200 instead of 204. Rate limiting and some contract errors are not implemented. See [API](04-api.md). |
| Partial | Dockerfile and Compose are defined; static configuration is verified, but build/runtime are not. External HTTPS and deployment are unverified. |
| Partial | UUID pagination has no snapshot; records inserted before the cursor may be omitted. Sync `device_id` is validated but not linked to the session. General concurrency guarantees have not been tested. |
| Pending | Rate limiting, security review, load/concurrency tests, and full conformance; tested backups and recovery; HTTPS infrastructure. Android Room/outbox, encryption, and offline behavior cannot be verified in this repository. |
| Blocked by design | Alert generation/Risk Engine: rules, evidence, and thresholds are unspecified and unapproved. An empty list does not indicate evaluation. Post-MVP provisioning, expiration policy, and offline cryptographic design require decisions. |
| Pending and external | Verification of the model, device, and Apollo/Google AI Edge inference on Android. There is no backend inference. |

Proposed priorities:

1. **Security risk:** define and apply brute-force controls; review token implementation, key handling, and volume access; verify TLS and logging policy before any exposure. Use synthetic data only.
2. **Functional/contract issues:** agree on and fix differences in generated OpenAPI, status codes, and error formats; add complete semantic contract tests. Decide whether sync `device_id` should be compared with the session before changing behavior. Review SQLite concurrency and page semantics.
3. **Operations:** build and run the image on an authorized host; test persistence, backup/restore, and recovery; validate the domain, DNS, Caddy, and external certificate.
4. **Functional blockers:** agree on Risk Engine rules, evidence, and limits before implementation; resolve offline design and session policy with Android owners. Do not present experimental rules as diagnoses.
5. **Optional:** improve observability without sensitive data and document performance and operational decisions after requirements are available.

The [root README](../../README.md) documents the implemented endpoints. The contract's note stating that it is unapproved is also historical, as explained in [DECISIONS](../DECISIONS.md). No real deployment or frontend was verified.
