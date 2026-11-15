# EIR backend autonomous development — decisions and constraints

- Approved: `main` stable; `dev` integration; isolated `feature/*` branches.
- Requested: local autonomous Codex orchestration, automatic integration including `main`, but ONLY after independent gates and GitHub protection. No direct push to protected branches.
- `contracts/openapi.yaml` was approved by the team as v0.1 baseline, despite a *stale in-file note* saying `REVIEW DRAFT — not an implemented or approved API`. Treat that text as obsolete with respect to approval only, not evidence of implemented functionality. Contract change requires a separate review/version; auto-agent must not silently change it.
- Deployment: AWS EC2 Ubuntu, Cloudflare DNS, Caddy HTTPS proposed; FastAPI deployment form unknown, domain unspecified, no deployment permission granted.
- Authentication: synthetic accounts preconfigured on FastAPI, password login online; previously initialized offline password verification for 24 hours is Android-local, not a backend endpoint; one astronaut can use multiple devices; device-sharing requires logout/new login; only own records; bootstrap profile + initial history.
- Logout: delete synchronized client cache, preserve encrypted pending records, lock private data after offline 24h; these are client-side responsibilities. Backend revokes remote session.
- Sync: Level 2 upload-only, per-item results, idempotence, retry, no binary media uploads, no server-side LLM.
- Unresolved: UI language, multimodal model scientific validity, exact HTTPS hostname, device cryptography, domain owner, backend runtime, formal account provisioning after MVP.
- Any auto-main promotion requires GitHub `main` and `dev` branch protection, required `quality` checks and no bypass, and PR based flow. If not verified, fail closed.
