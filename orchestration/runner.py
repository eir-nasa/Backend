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
from urllib.parse import urlencode

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


def repository_name() -> str:
    repo = json.loads(command(["gh", "api", "repos/{owner}/{repo}"]))
    name = repo.get("full_name")
    if not isinstance(name, str) or name.count("/") != 1:
        raise RuntimeError("Repository identity unavailable")
    return name


def pull_requests(head: str, base: str, state: str) -> list[dict]:
    """List all matching PRs, including every API page, with repository identity."""
    repo = repository_name()
    query = urlencode({"state": state, "head": f"{repo.split('/')[0]}:{head}",
                       "base": base, "per_page": 100})
    pages = json.loads(command(["gh", "api", "--paginate", "--slurp",
                                f"repos/{{owner}}/{{repo}}/pulls?{query}"]))
    if not isinstance(pages, list) or not pages or any(
        not isinstance(page, list) for page in pages
    ):
        raise RuntimeError("Incomplete PR list")
    prs = [pr for page in pages for pr in page]
    for pr in prs:
        if (not isinstance(pr, dict) or type(pr.get("number")) is not int
                or not isinstance(pr.get("head"), dict) or not isinstance(pr.get("base"), dict)
                or pr["head"].get("ref") != head or pr["base"].get("ref") != base
                or (pr["head"].get("repo") or {}).get("full_name") != repo
                or (pr["base"].get("repo") or {}).get("full_name") != repo
                or not isinstance(pr["head"].get("sha"), str)
                or pr.get("state") != state):
            raise RuntimeError("Incomplete or mismatched PR identity")
    return prs


def pr_by_number(number: int, head: str, base: str, expected_sha: str) -> dict:
    pr = json.loads(command(["gh", "api", f"repos/{{owner}}/{{repo}}/pulls/{number}"]))
    repo = repository_name()
    if (pr.get("number") != number or (pr.get("head") or {}).get("ref") != head
            or (pr.get("base") or {}).get("ref") != base
            or (pr.get("head") or {}).get("sha") != expected_sha
            or ((pr.get("head") or {}).get("repo") or {}).get("full_name") != repo
            or ((pr.get("base") or {}).get("repo") or {}).get("full_name") != repo):
        raise RuntimeError(f"PR #{number} does not match expected head and base")
    if pr.get("state") not in {"open", "closed"}:
        raise RuntimeError(f"PR #{number} has an unknown state")
    return pr


def open_pr(head: str, base: str, expected_sha: str, title: str, body: str) -> int:
    prs = pull_requests(head, base, "open")
    if len(prs) > 1:
        raise RuntimeError(f"Ambiguous open PRs for {head} -> {base}")
    if not prs:
        command(["gh", "pr", "create", "--base", base, "--head", head,
                 "--title", title, "--body", body])
        prs = pull_requests(head, base, "open")
        if len(prs) != 1:
            raise RuntimeError(f"Created PR for {head} -> {base} is missing or ambiguous")
    number = prs[0]["number"]
    pr = pr_by_number(number, head, base, expected_sha)
    if pr["state"] != "open" or pr.get("merged_at") is not None:
        raise RuntimeError(f"PR #{number} is not open")
    return number


def is_ancestor(commit: str, ref: str) -> bool:
    if not commit or not ref or any(c not in "0123456789abcdef" for c in commit.lower()):
        raise RuntimeError("Invalid commit identity")
    comparison = json.loads(command([
        "gh", "api", f"repos/{{owner}}/{{repo}}/compare/{commit}...{ref}",
    ]))
    status = comparison.get("status")
    if status not in {"ahead", "identical", "behind", "diverged"}:
        raise RuntimeError("Incomplete commit comparison")
    return status in {"ahead", "identical"}


def merge_pr(head: str, base: str, expected_sha: str, title: str, body: str,
             method: str) -> str:
    number = open_pr(head, base, expected_sha, title, body)
    args = ["gh", "pr", "merge", str(number), "--auto", method]
    if head != "dev":
        args.append("--delete-branch")
    command(args)
    start = time.monotonic()
    while time.monotonic() - start < MAX_WAIT_SECONDS:
        pr = pr_by_number(number, head, base, expected_sha)
        if pr["state"] == "closed":
            commit = pr.get("merge_commit_sha")
            if not pr.get("merged_at") or not isinstance(commit, str):
                raise RuntimeError(f"PR #{number} closed without confirmed merge")
            if not is_ancestor(commit, base):
                raise RuntimeError(f"PR #{number} merge commit is not in {base}")
            return commit
        time.sleep(POLL_SECONDS)
    raise RuntimeError(f"Timed out waiting for PR #{number} to {base}")


def pr_and_wait(base: str, head: str, title: str) -> str:
    expected_sha = command(["git", "rev-parse", "HEAD"])
    command(["git", "push", "-u", "origin", head])
    return merge_pr(head, base, expected_sha, title,
                    "Autonomous EIR implementation. Must pass all required CI status checks.",
                    "--squash")


def reconcile_task(name: str, data: dict) -> None:
    """Reconcile an interrupted task using merged PRs and remote commit ancestry."""
    entry = data["tasks"][name]
    if entry.get("status") not in {"BLOCKED", "IN_PROGRESS", "INTEGRATED"}:
        raise RuntimeError(f"Task {name} is not awaiting reconciliation")
    feature = f"feature/{name}"
    prs = [pr for pr in pull_requests(feature, "dev", "closed") if pr.get("merged_at")]
    if len(prs) != 1:
        raise RuntimeError(f"Expected one merged feature PR for {name}; found {len(prs)}")
    pr = prs[0]
    feature_sha = pr["head"]["sha"]
    if entry.get("feature_sha") and entry["feature_sha"] != feature_sha:
        raise RuntimeError("Feature PR SHA differs from recorded implementation")
    pr = pr_by_number(pr["number"], feature, "dev", feature_sha)
    commit = pr.get("merge_commit_sha")
    if pr["state"] != "closed" or not pr.get("merged_at") or not isinstance(commit, str):
        raise RuntimeError("Feature merge not confirmed")
    if entry.get("integration_commit") and entry["integration_commit"] != commit:
        raise RuntimeError("Feature merge commit differs from recorded implementation")
    if not is_ancestor(commit, "dev"):
        raise RuntimeError("Feature merge commit is not in remote dev")
    integrated_main = is_ancestor(commit, "main")
    if integrated_main:
        promotions = [pr for pr in pull_requests("dev", "main", "closed")
                      if pr.get("merged_at")]
        confirmed = False
        for promotion in promotions:
            promotion = pr_by_number(promotion["number"], "dev", "main",
                                     promotion["head"]["sha"])
            merge_commit = promotion.get("merge_commit_sha")
            if (promotion["state"] == "closed" and promotion.get("merged_at")
                    and isinstance(merge_commit, str)
                    and is_ancestor(commit, promotion["head"]["sha"])
                    and is_ancestor(merge_commit, "main")):
                confirmed = True
        if not confirmed:
            raise RuntimeError("No confirmed promotion PR containing the task in main")
    entry.update(status="COMPLETED" if integrated_main else "INTEGRATED",
                 feature_sha=feature_sha, integration_commit=commit, feature_pr=pr["number"])
    state_save(data)
    log({"task": name, "status": entry["status"], "reconciled": True})


def promote_task(name: str, data: dict) -> None:
    entry = data["tasks"][name]
    commit = entry.get("integration_commit")
    if entry.get("status") != "INTEGRATED" or not isinstance(commit, str):
        raise RuntimeError("Task must be reconciled as INTEGRATED before promotion")
    git_clean()
    verify_remote_protections()
    if not is_ancestor(commit, "dev"):
        raise RuntimeError("Task integration commit is no longer in remote dev")
    command(["git", "fetch", "origin", "dev", "main"])
    command(["git", "switch", "dev"])
    command(["git", "pull", "--ff-only", "origin", "dev"])
    quality_gate(ROOT)
    expected_sha = command(["git", "rev-parse", "HEAD"])
    merge_pr("dev", "main", expected_sha, f"EIR stable promotion after {name}",
             "Promote integration branch after required CI and branch protections.", "--merge")
    if not is_ancestor(commit, "main"):
        raise RuntimeError("Task integration commit not confirmed in main")
    entry.update(status="COMPLETED", commit=expected_sha)
    state_save(data)
    log({"task": name, "status": "COMPLETED", "promoted_to_main": True})


def run_one(item: dict, data: dict) -> None:
    name = item["id"]
    feature = f"feature/{name}"
    entry = data["tasks"][name]
    git_clean()
    if pull_requests(feature, "dev", "open") or any(
        pr.get("merged_at") for pr in pull_requests(feature, "dev", "closed")
    ):
        raise RuntimeError(f"Remote PR exists for {feature}; reconcile before implementation")
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
    feature_sha = command(["git", "rev-parse", "HEAD"])
    entry.update(feature_sha=feature_sha)
    state_save(data)
    commit = pr_and_wait("dev", feature, f"EIR: {name}")
    entry.update(status="INTEGRATED", integration_commit=commit)
    state_save(data)
    promote_task(name, data)


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--reconcile", metavar="TASK")
    modes.add_argument("--resume", metavar="TASK")
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
    if args.reconcile:
        if args.reconcile not in data["tasks"]:
            raise RuntimeError("Unknown task")
        reconcile_task(args.reconcile, data)
        print(f"{args.reconcile}: {data['tasks'][args.reconcile]['status']}")
        return 0
    if args.resume:
        if args.resume not in data["tasks"]:
            raise RuntimeError("Unknown task")
        reconcile_task(args.resume, data)
        if data["tasks"][args.resume]["status"] == "INTEGRATED":
            promote_task(args.resume, data)
        return 0
    git_clean()
    if any(entry.get("status") == "IN_PROGRESS" for entry in data["tasks"].values()):
        raise RuntimeError("Interrupted task requires manual merge and state reconciliation")
    if any(entry.get("status") == "INTEGRATED" for entry in data["tasks"].values()):
        raise RuntimeError("Integrated task requires explicit resume")
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
