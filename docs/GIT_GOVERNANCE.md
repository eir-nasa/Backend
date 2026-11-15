# Git Governance

- main: stable only; dev: integrated changes; feature/<task>: single implementation unit.
- Feature branches are created from current `origin/dev`.
- Features go through PR to `dev` (required checks), then `dev` through PR to `main` (required checks).
- No direct pushes to protected branches, no force pushes, no deletion of protected branches.
- Orchestrator is sole automation actor for Git integration. Codex works only in feature branch.
- Upstream contract modifications need human/team approval and a separate contract version/lock update; the task agent cannot rewrite baseline.
- No merged feature without actual tests; merge buttons/auto-merge depend on CI, not agent-produced summaries.
- For a repository with required reviewers, fully unattended promotion will block; do not disable requirements to make a broken pipeline appear green.
- When a task fails after three iterations, retain feature work and log the failure; no automatic rollback that could discard useful work.
- No deployment, AWS mutation, Cloudflare mutation or production data handling as part of auto-merge.
