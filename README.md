# EIR Backend — autonomous Codex starter

This package is **orchestration and governance scaffolding**, not a completed FastAPI backend. Contract is approved v0.1 baseline; no app endpoints are implemented here. Do not point production applications at it yet.

## What it does

- Runs independent Codex CLI implementation turns in a deterministic order from `orchestration/tasks.json`.
- Checks real source changes, protects the contract/harness, runs local quality gates, retries up to three times, and persists state in `.orchestrator/`.
- Pushes feature branches and merges with **protected GitHub PRs**: `feature/* → dev → main` after required CI. Never pushes to `dev` or `main` directly.
- Blocks if prerequisites or branch protection are missing. Never deploys to EC2 automatically.
- Promotes to main automatically only when PR protections require CI checks and zero human reviews. This requires appropriate GitHub plan, rights and repo settings; it is not configured for you.

## Prerequisites on your NixOS development machine

- `git`, `python >=3.11`, `codex` CLI, `gh` CLI, and network/auth access to Codex and GitHub.
- On NixOS, place those tools in a development shell (`nix develop` or `nix-shell`) or install them through your Nix configuration. You need a working Python venv with packages available.
- GitHub repository access with the permissions to create PRs and configure protections. **No direct agent access to AWS or Cloudflare**.

## First-time setup

```bash
unzip EIR_Backend_Autonomy.zip
cd EIR_Backend_Autonomy
./scripts_bootstrap.sh
# Set your actual repository URL:
git remote add origin git@github.com:YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
git push -u origin dev
# Complete protection configuration in the GitHub settings as described below.
gh auth login
codex login
python -m orchestration.runner --dry-run
python -m orchestration.runner --execute
```

`--execute` **actually invokes Codex and can create/push/merge pull requests without further prompts** after preflight. Use only after repository rights and checks are verified. It may incur model usage costs. You can interrupt it locally. It has bounded attempts and timeouts.

## Mandatory GitHub protections (both `dev` and `main`)

Repo Settings → Branches / Rulesets (or equivalent GitHub UI):

1. Require PR before merging; approvals **0** if using fully unattended auto-promotions.
2. Require status check **`quality`** from `.github/workflows/ci.yml`, with branch up-to-date/strict checking enabled.
3. Apply rules to administrators, disable bypass; disallow force pushes and deletions.
4. Repository Settings → General → Pull Requests: enable **Allow auto-merge** and merge commits for `dev → main`; enable squash merges for feature PRs.
5. Configure the branch rules to prevent direct push to main/dev and ensure required checks are from the expected GitHub Actions app. Verify `gh api repos/{owner}/{repo}/branches/main/protection` works.

**Safety trade-off:** zero human reviews means autonomous code can reach `main` as soon as CI passes. Automated testing cannot prove the implementation is clinically safe or fully correct. Keep this as a synthetic-data hackathon environment with no real patient records. Consider scheduled manual audits of main.

**Compatibility note:** `gh` CLI permissions, policies, rate limits, and auto-merge availability differ across repositories. The runner fails closed rather than bypassing GitHub settings. As written, it uses the GitHub branch-protection endpoint; a repository secured only through rulesets may require extending preflight verification before running.

## Gates

- OpenAPI 3.1 structure + immutable SHA-256 lock.
- Ruff lint checks on `src`, `tests`, `orchestration`.
- pytest tests, plus `tests/test_backend_*.py` requirement after backend code exists.
- Protected file/path guard before commit.
- GitHub required `quality` check on protected PRs.

Run locally:

```bash
python -m orchestration.validate_contract
python -m ruff check src tests orchestration
python -m pytest -q tests
```

Note: The CI `quality` gate validates the OpenAPI schema and lock, but does not independently check that generated FastAPI schema is semantically identical unless a Codex task adds that test. The `integration` task is responsible for such an executable contract conformance suite; until then the automatic main promotion validates only the currently implemented tests. **This is a material limitation of auto-promotion.**

## Known design limits

- The `runner.py` task engine is sequential. “Agents” are roles within Codex tasks, not independent concurrent processes; no unmanaged background Codex sessions.
- Works with remote GitHub PR auto-merge and polls status while local machine is running. No work continues when your computer is off.
- `dev` and `main` are never modified directly by the runner, only via GitHub merge operations.
- A blocked task remains documented; the runner stops rather than silently skipping contractual dependencies.
- On exception after Codex changes, partial code remains on the feature branch to examine manually. No destructive reset is attempted.
- The initial AGENTS.md/contract/harness are protected from Codex edits by both instruction and deterministic diff inspection. This is not an OS-level sandbox security boundary; Codex CLI sandboxing is still required.
- Does not set up remote GitHub settings automatically. Admin approvals, domain, AWS deployment and model authorization remain outside this harness.
