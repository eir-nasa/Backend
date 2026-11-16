# 01 — Overview

EIR aims to support health and wellbeing tracking in an environment with intermittent connectivity. This backend provides a remote demonstration repository for synthetic accounts: online authentication, profiles, idempotent record uploads, history queries, and retrieval of already stored alerts. It does not provide diagnoses; measurements and self-reports are experimental and are not clinically validated.

The implementation is a modular monolith using Python 3.11+, FastAPI, Pydantic, SQLite, and Uvicorn; the Dockerfile uses Python 3.12. Android communicates over HTTP and is responsible for Room, a durable outbox, and offline mechanisms. Apollo and Google AI Edge are planned for Android; this backend does not perform LLM inference. The Android implementation and its integration are not in this repository and have not been verified.

The code contains all ten contract operations, with OpenAPI compatibility limitations described in [API](04-api.md). Alerts can be read, but there is no alert generation or Risk Engine. There is no public registration or default account. The HTTPS deployment plan does not establish that a service has been deployed. Local tests and their limitations are described in [tests](08-testing.md).

Sources: [handoff](../EIR_HANDOFF.md), [decisions](../DECISIONS.md), [application](../../src/eir/main.py), [configuration](../../pyproject.toml).
