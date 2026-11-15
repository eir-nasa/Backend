# EIR backend — permanent instructions for Codex

## Sources of truth
- `contracts/openapi.yaml` is the team-approved contract **baseline**. Its legacy description incorrectly says unapproved; see `docs/DECISIONS.md`. Do NOT modify this file automatically.
- `docs/EIR_HANDOFF.md` contains functional decisions. Existing code is not a substitute for either source.
- Android runs Google AI Edge on-device. Do NOT add Ollama or server-side LLM inference.
- Synthetic demonstration accounts only. Never include actual astronaut or patient information.

## Technical boundaries
- Python + FastAPI + SQLite, modular monolith. Tests are required for each behavior.
- Offline-first Level 2: Android owns Room and durable outbox; backend owns authorization, idempotent bulk ingest, per-record acknowledgements, stable record IDs, atomic persistence.
- Check-ins, physical readings and rules are not clinically validated. No diagnoses.
- Server must resolve account ownership from verified authentication, never trust supplied owner identity.
- Do not introduce undocumented endpoints or alter agreed request/response schemas.
- Do not place passwords, access tokens or personal records into logs or commits.

## Execution and Git
- Work only on the feature branch prepared by the external orchestrator.
- The orchestrator owns merges, PRs, promotion and branch changes; do not issue `git switch`, `git merge`, `git push`, `gh`, or force operations.
- Do not edit `.github/`, `orchestration/`, `contracts/`, `AGENTS.md`, `.gitignore`, `docs/EIR_HANDOFF.md`, or `docs/DECISIONS.md`.
- Implement only the assigned task. You may update `src/`, `tests/`, `docs/IMPLEMENTATION_STATUS.md`, and dependency/configuration files when necessary.
- Add actual pytest tests; do not mark missing or skipped tests as passed. No disabling security or contract tests.
- Keep instructions, documentation of results and code comments in English where sensible; app UI language remains undecided.
- If requirements are ambiguous, record the limitation without inventing clinical rules or new contract fields.
