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
    """Verify effective rules and visible bypass settings for each protected branch."""
    if not shutil.which("gh") or not shutil.which("codex"):
        raise RuntimeError("Both gh CLI and Codex CLI are required for --execute")
    command(["gh", "auth", "status"])
    repo = json.loads(command(["gh", "api", "repos/{owner}/{repo}"]))
    if (repo.get("allow_auto_merge") is not True
            or repo.get("allow_squash_merge") is not True
            or repo.get("allow_merge_commit") is not True):
        raise RuntimeError("Repository auto-merge or required merge methods are not enabled")
    for target in ("dev", "main"):
        pages = json.loads(command([
            "gh", "api", "--paginate", "--slurp",
            f"repos/{{owner}}/{{repo}}/rules/branches/{target}?per_page=100",
        ]))
        if not isinstance(pages, list) or not pages or any(
            not isinstance(page, list) for page in pages
        ):
            raise RuntimeError(f"{target}: incomplete effective rules response")
        rules = [rule for page in pages for rule in page]
        if not rules or any(not isinstance(rule, dict) or not isinstance(
            rule.get("ruleset_id"), int
        ) for rule in rules):
            raise RuntimeError(f"{target}: effective rules lack ruleset provenance")
        for ruleset_id in {rule["ruleset_id"] for rule in rules}:
            detail = json.loads(command([
                "gh", "api", f"repos/{{owner}}/{{repo}}/rulesets/{ruleset_id}",
            ]))
            if (detail.get("id") != ruleset_id or detail.get("enforcement") != "active"
                    or detail.get("target") != "branch"
                    or not isinstance(detail.get("bypass_actors"), list)):
                raise RuntimeError(f"{target}: ruleset {ruleset_id} is incomplete or inactive")
            # Conservatively reject all bypass actors: membership and token identity can change.
            if detail["bypass_actors"]:
                raise RuntimeError(f"{target}: ruleset {ruleset_id} has possible bypass actors")
        types = {rule.get("type") for rule in rules}
        if not {"pull_request", "required_status_checks", "non_fast_forward", "deletion"} <= types:
            raise RuntimeError(f"{target}: missing required effective rules")
        for rule in rules:
            if rule.get("type") == "pull_request":
                params = rule.get("parameters")
                if (not isinstance(params, dict)
                        or type(params.get("required_approving_review_count")) is not int
                        or params["required_approving_review_count"] != 0
                        or params.get("require_code_owner_review") is not False
                        or params.get("require_last_push_approval") is not False):
                    raise RuntimeError(f"{target}: human review requirements not compatible")
        checks = [rule.get("parameters", {}).get("required_status_checks")
                  for rule in rules if rule.get("type") == "required_status_checks"]
        if any(not isinstance(entries, list) or any(
            not isinstance(entry, dict) or not isinstance(entry.get("context"), str)
            for entry in entries
        ) for entries in checks) or not any(
            entry["context"] == "quality" for entries in checks for entry in entries
        ):
            raise RuntimeError(f"{target}: missing or incomplete required quality check")


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


def confirmed_merge(head: str, base: str, expected_sha: str) -> str:
    """Return PR state only after verifying the exact head and destination."""
    pr = json.loads(command(["gh", "pr", "view", head, "--json",
                             "state,baseRefName,headRefOid,mergedAt"]))
    if pr.get("baseRefName") != base or pr.get("headRefOid") != expected_sha:
        raise RuntimeError(f"PR {head} does not match expected head and base")
    state = pr.get("state")
    if state not in {"OPEN", "CLOSED", "MERGED"}:
        raise RuntimeError(f"PR {head} has an unknown state")
    if state == "MERGED" and not pr.get("mergedAt"):
        raise RuntimeError(f"PR {head} merge is not confirmed")
    return state


def pr_and_wait(base: str, head: str, title: str) -> None:
    # Push feature and create PR; GitHub protection + required CI alone gates auto merge.
    expected_sha = command(["git", "rev-parse", "HEAD"])
    command(["git", "push", "-u", "origin", head])
    try:
        command(["gh", "pr", "view", head, "--json", "number", "--jq", ".number"])
    except RuntimeError:
        command(["gh", "pr", "create", "--base", base, "--head", head,
                "--title", title, "--body", "Autonomous EIR implementation. Must pass all required CI status checks."])
    if confirmed_merge(head, base, expected_sha) != "OPEN":
        raise RuntimeError(f"PR {head} is not open for promotion")
    command(["gh", "pr", "merge", head, "--auto", "--squash", "--delete-branch"])
    start = time.monotonic()
    while time.monotonic() - start < MAX_WAIT_SECONDS:
        status = confirmed_merge(head, base, expected_sha)
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
    expected_sha = command(["git", "rev-parse", "HEAD"])
    # main promotion only via protected GitHub PR, no direct local or remote main push.
    try:
        command(["gh", "pr", "view", "dev", "--json", "number", "--jq", ".number"])
    except RuntimeError:
        command(["gh", "pr", "create", "--base", "main", "--head", "dev",
                 "--title", f"EIR stable promotion after {name}",
                 "--body", "Promote integration branch after required CI and branch protections."])
    if confirmed_merge("dev", "main", expected_sha) != "OPEN":
        raise RuntimeError("dev -> main PR is not open for promotion")
    command(["gh", "pr", "merge", "dev", "--auto", "--merge"])
    start = time.monotonic()
    while time.monotonic() - start < MAX_WAIT_SECONDS:
        status = confirmed_merge("dev", "main", expected_sha)
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
    if any(entry.get("status") == "IN_PROGRESS" for entry in data["tasks"].values()):
        raise RuntimeError("Interrupted task requires manual merge and state reconciliation")
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
