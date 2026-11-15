"""Autonomous local Codex + GitHub-PR runner. Deliberately fail-closed.

Usage: python -m orchestration.runner --dry-run
       python -m orchestration.runner --execute

Never writes to protected main/dev directly. Requires verified GitHub branch protection.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from orchestration.gates import quality_gate

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".orchestrator/state.json"
LOG = ROOT / ".orchestrator/executions.jsonl"
TASKS = ROOT / "orchestration/tasks.json"
RETRIES = 3
TIMEOUT_CODEX = 2400
POLL_SECONDS = 15
MAX_WAIT_SECONDS = 1800
PROTECTED = (
    "contracts/", ".github/", "orchestration/", "AGENTS.md", ".gitignore",
    "docs/EIR_HANDOFF.md", "docs/DECISIONS.md",
)


def command(args: list[str], *, timeout: int = 120, capture: bool = True) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=capture,
                            timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr[-1500:] if capture else ''}")
    return result.stdout.strip() if capture else ""


def log(event: dict) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **event}) + "\n")


def tasks() -> list[dict]:
    return json.loads(TASKS.read_text(encoding="utf-8"))


def state_load(items: list[dict]) -> dict:
    if STATE.exists():
        data = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        data = {"tasks": {}}
    for item in items:
        data["tasks"].setdefault(item["id"], {"status": "PENDING", "attempts": 0})
    return data


def state_save(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temp.replace(STATE)


def git_clean() -> None:
    if command(["git", "status", "--porcelain"]):
        raise RuntimeError("Uncommitted repository changes. Refusing to overwrite work.")


def branch() -> str:
    return command(["git", "branch", "--show-current"])


def verify_remote_protections() -> None:
    """Check GitHub protections, required CI and PR path before autonomous promotion."""
    if not shutil.which("gh") or not shutil.which("codex"):
        raise RuntimeError("Both gh CLI and Codex CLI are required for --execute")
    command(["gh", "auth", "status"])
    for target in ("dev", "main"):
        payload = json.loads(command(["gh", "api", f"repos/{{owner}}/{{repo}}/branches/{target}/protection"]))
        if not payload.get("required_pull_request_reviews"):
            # GitHub may allow protected branches with no review count but PR requirement.
            raise RuntimeError(f"{target}: pull-request requirement not verified; fail closed")
        review = payload["required_pull_request_reviews"]
        if review.get("required_approving_review_count", 0) != 0 or review.get("require_code_owner_reviews", False):
            raise RuntimeError(f"{target}: human PR review requirement incompatible with unattended promotion")
        checks = payload.get("required_status_checks") or {}
        contexts = set(checks.get("contexts") or []) | {
            entry.get("context", "") for entry in checks.get("checks", [])
        }
        if "quality" not in contexts:
            raise RuntimeError(f"{target}: missing required 'quality' status check")
        if not payload.get("enforce_admins", {}).get("enabled"):
            raise RuntimeError(f"{target}: administrator bypass not disabled")
        if payload.get("allow_force_pushes", {}).get("enabled", False):
            raise RuntimeError(f"{target}: force push is enabled")
        if payload.get("allow_deletions", {}).get("enabled", False):
            raise RuntimeError(f"{target}: branch deletions enabled")


def select_task(items: list[dict], state: dict) -> dict | None:
    for item in items:
        entry = state["tasks"][item["id"]]
        if entry["status"] == "COMPLETED" or entry["status"] == "BLOCKED":
            continue
        if all(state["tasks"][dep]["status"] == "COMPLETED" for dep in item["dependencies"]):
            return item
    return None


def inspect_changes() -> None:
    files = command(["git", "diff", "--name-only", "dev...HEAD"]).splitlines()
    files.extend(command(["git", "diff", "--name-only"]).splitlines())
    files.extend(command(["git", "diff", "--cached", "--name-only"]).splitlines())
    files.extend(command(["git", "ls-files", "--others", "--exclude-standard"]).splitlines())
    for name in files:
        if name in PROTECTED or any(name.startswith(p) for p in PROTECTED if p.endswith("/")):
            raise RuntimeError(f"Codex changed protected harness/contract path: {name}")
    if not files:
        raise RuntimeError("No implementation changes produced")


def codex_task(item: dict, attempt: int) -> None:
    prompt = f"""Implement ONLY EIR backend task {item['id']}: {item['description']}
Read AGENTS.md, docs/EIR_HANDOFF.md, and contracts/openapi.yaml.
Do not modify orchestrator, contract, Git, CI or governance files; do not merge or commit.
Add real backend tests in tests/test_backend_*.py, with positive and negative cases.
Focus on the smallest change satisfying the approved contract; do not invent new clinical rules.
This is attempt {attempt}/{RETRIES}. Finish without prompting the operator."""
    command(["codex", "exec", "--sandbox", "workspace-write", prompt], timeout=TIMEOUT_CODEX,
            capture=False)


def pr_and_wait(base: str, head: str, title: str) -> None:
    # Push feature and create PR; GitHub protection + required CI alone gates auto merge.
    command(["git", "push", "-u", "origin", head])
    try:
        command(["gh", "pr", "view", head, "--json", "number", "--jq", ".number"])
    except RuntimeError:
        command(["gh", "pr", "create", "--base", base, "--head", head,
                "--title", title, "--body", "Autonomous EIR implementation. Must pass all required CI status checks."])
    command(["gh", "pr", "merge", head, "--auto", "--squash", "--delete-branch"])
    start = time.monotonic()
    while time.monotonic() - start < MAX_WAIT_SECONDS:
        status = command(["gh", "pr", "view", head, "--json", "state", "--jq", ".state"])
        if status == "MERGED":
            return
        if status == "CLOSED":
            raise RuntimeError(f"PR {head} was closed without merge")
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for GitHub CI/merge of PR {head} to {base}")


def run_one(item: dict, data: dict) -> None:
    name = item["id"]
    feature = f"feature/{name}"
    entry = data["tasks"][name]
    git_clean()
    command(["git", "fetch", "origin", "dev", "main"])
    command(["git", "switch", "dev"])
    command(["git", "pull", "--ff-only", "origin", "dev"])
    # No reusing stale branches automatically.
    if command(["git", "branch", "--list", feature]):
        raise RuntimeError(f"Stale feature branch {feature} exists; manual reconciliation required")
    command(["git", "switch", "-c", feature])
    success = False
    for attempt in range(1, RETRIES + 1):
        entry.update(status="IN_PROGRESS", attempts=attempt)
        state_save(data)
        try:
            codex_task(item, attempt)
            if branch() != feature:
                raise RuntimeError("Codex changed Git branch; fail closed")
            inspect_changes()
            quality_gate(ROOT)
            success = True
            break
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            log({"task": name, "attempt": attempt, "error": str(error)})
    if not success:
        entry["status"] = "BLOCKED"
        state_save(data)
        # Keep uncommitted changes in feature branch for inspection; halt safely.
        raise RuntimeError(f"Task {name} failed {RETRIES} attempts; worktree retained for inspection")
    command(["git", "add", "-A"])
    command(["git", "commit", "-m", f"feat({name}): implement EIR backend task"])
    pr_and_wait("dev", feature, f"EIR: {name}")
    command(["git", "switch", "dev"])
    command(["git", "pull", "--ff-only", "origin", "dev"])
    # Validate integrated dev independently before making release PR.
    quality_gate(ROOT)
    # main promotion only via protected GitHub PR, no direct local or remote main push.
    try:
        command(["gh", "pr", "view", "dev", "--json", "number", "--jq", ".number"])
    except RuntimeError:
        command(["gh", "pr", "create", "--base", "main", "--head", "dev",
                 "--title", f"EIR stable promotion after {name}",
                 "--body", "Promote integration branch after required CI and branch protections."])
    command(["gh", "pr", "merge", "dev", "--auto", "--merge"])
    start = time.monotonic()
    while time.monotonic() - start < MAX_WAIT_SECONDS:
        status = command(["gh", "pr", "view", "dev", "--json", "state", "--jq", ".state"])
        if status == "MERGED":
            entry.update(status="COMPLETED", commit=command(["git", "rev-parse", "HEAD"]))
            state_save(data)
            log({"task": name, "status": "COMPLETED", "promoted_to_main": True})
            return
        if status == "CLOSED":
            raise RuntimeError("dev -> main PR closed without merge")
        time.sleep(POLL_SECONDS)
    raise RuntimeError("Timed out waiting for dev -> main protected PR")


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    items = tasks()
    data = state_load(items)
    if args.dry_run:
        for item in items:
            print(f"{item['id']}: depends on {', '.join(item['dependencies']) or '(none)'}")
        print("DRY RUN ONLY. No Codex, commits, pushes or merges invoked.")
        return 0
    if not (ROOT / ".git").exists():
        raise RuntimeError("Initialize Git with committed main/dev first; run bootstrap.sh")
    git_clean()
    verify_remote_protections()
    while item := select_task(items, data):
        try:
            run_one(item, data)
        except Exception as error:
            log({"task": item["id"], "status": "BLOCKED", "error": str(error)})
            data["tasks"][item["id"]]["status"] = "BLOCKED"
            state_save(data)
            raise
    print("No runnable tasks remain. Review .orchestrator/state.json")
    if any(d["status"] != "COMPLETED" for d in data["tasks"].values()):
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FAIL CLOSED: {exc}", file=sys.stderr)
        sys.exit(1)
