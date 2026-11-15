"""Regression tests for PR identity, promotion and interrupted task recovery."""
import copy
import json

import pytest

from orchestration import runner

REPO = "eir-nasa/Backend"
FEATURE = "a" * 40
INTEGRATION = "b" * 40
DEV = "c" * 40
MERGE = "d" * 40


def pr(number, head, base, sha, state="open", merged=False, merge=None):
    return {"number": number, "state": state, "merged_at": "date" if merged else None,
            "merge_commit_sha": merge,
            "head": {"ref": head, "sha": sha, "repo": {"full_name": REPO}},
            "base": {"ref": base, "repo": {"full_name": REPO}}}


def test_open_pr_ignores_merged_history_and_creates_new(monkeypatch):
    current = pr(4, "dev", "main", DEV)
    responses = iter([[], [current]])
    commands = []
    monkeypatch.setattr(runner, "pull_requests", lambda *args: next(responses))
    monkeypatch.setattr(runner, "pr_by_number", lambda *args: current)
    monkeypatch.setattr(runner, "command", lambda args: commands.append(args) or "")
    assert runner.open_pr("dev", "main", DEV, "title", "body") == 4
    assert commands[0][:3] == ["gh", "pr", "create"]


def test_open_pr_reuses_current_number(monkeypatch):
    current = pr(4, "dev", "main", DEV)
    monkeypatch.setattr(runner, "pull_requests", lambda *args: [current])
    monkeypatch.setattr(runner, "pr_by_number", lambda *args: current)
    assert runner.open_pr("dev", "main", DEV, "title", "body") == 4


def test_ambiguous_open_prs_fail(monkeypatch):
    current = pr(4, "dev", "main", DEV)
    monkeypatch.setattr(runner, "pull_requests", lambda *args: [current, current])
    with pytest.raises(RuntimeError, match="Ambiguous"):
        runner.open_pr("dev", "main", DEV, "title", "body")


def test_incorrect_sha_is_rejected(monkeypatch):
    current = pr(4, "dev", "main", FEATURE)
    monkeypatch.setattr(runner, "repository_name", lambda: REPO)
    monkeypatch.setattr(runner, "command", lambda *args: json.dumps(current))
    with pytest.raises(RuntimeError, match="expected head and base"):
        runner.pr_by_number(4, "dev", "main", DEV)


def test_merge_polls_by_number_and_requires_main_ancestry(monkeypatch):
    current = pr(4, "dev", "main", DEV, "closed", True, MERGE)
    calls = []
    monkeypatch.setattr(runner, "open_pr", lambda *args: 4)
    monkeypatch.setattr(runner, "command", lambda args: calls.append(args) or "")
    monkeypatch.setattr(runner, "pr_by_number", lambda *args: current)
    monkeypatch.setattr(runner, "is_ancestor", lambda commit, base: False)
    with pytest.raises(RuntimeError, match="not in main"):
        runner.merge_pr("dev", "main", DEV, "title", "body", "--merge")
    assert calls[0][3] == "4"


@pytest.fixture
def recovery(monkeypatch):
    feature = pr(3, "feature/foundation", "dev", FEATURE, "closed", True, INTEGRATION)
    historic = pr(2, "dev", "main", "e" * 40, "closed", True, "f" * 40)
    promotion = pr(4, "dev", "main", DEV, "closed", True, MERGE)
    state = {"tasks": {"foundation": {"status": "BLOCKED", "attempts": 1}}}
    remote = {"feature": [feature], "promotion": [historic], "main": False}

    def pulls(head, base, status):
        return copy.deepcopy(remote["feature" if head.startswith("feature/") else "promotion"])

    def get(number, head, base, sha):
        for item in remote["feature"] + remote["promotion"]:
            if item["number"] == number and item["head"]["sha"] == sha:
                return copy.deepcopy(item)
        raise RuntimeError("PR missing")

    def ancestor(commit, ref):
        if ref == "dev":
            return True
        if ref == "main":
            return remote["main"] and commit in {INTEGRATION, MERGE}
        return commit == INTEGRATION and ref == DEV

    monkeypatch.setattr(runner, "pull_requests", pulls)
    monkeypatch.setattr(runner, "pr_by_number", get)
    monkeypatch.setattr(runner, "is_ancestor", ancestor)
    monkeypatch.setattr(runner, "state_save", lambda data: None)
    monkeypatch.setattr(runner, "log", lambda event: None)
    return state, remote, promotion


@pytest.mark.parametrize("status", ["BLOCKED", "IN_PROGRESS"])
def test_reconcile_merged_foundation_in_dev_without_rerunning(recovery, status):
    state, _, _ = recovery
    state["tasks"]["foundation"]["status"] = status
    runner.reconcile_task("foundation", state)
    assert state["tasks"]["foundation"]["status"] == "INTEGRATED"
    assert state["tasks"]["foundation"]["integration_commit"] == INTEGRATION


def test_reconcile_main_requires_correct_promotion(recovery):
    state, remote, promotion = recovery
    remote["main"] = True
    with pytest.raises(RuntimeError, match="No confirmed promotion"):
        runner.reconcile_task("foundation", state)
    assert state["tasks"]["foundation"]["status"] == "BLOCKED"
    remote["promotion"].append(promotion)
    runner.reconcile_task("foundation", state)
    assert state["tasks"]["foundation"]["status"] == "COMPLETED"


def test_reconcile_rejects_ambiguous_feature_prs(recovery):
    state, remote, _ = recovery
    remote["feature"].append(copy.deepcopy(remote["feature"][0]))
    with pytest.raises(RuntimeError, match="Expected one merged feature PR"):
        runner.reconcile_task("foundation", state)
    assert state["tasks"]["foundation"]["status"] == "BLOCKED"


def test_reconcile_rejects_unexpected_recorded_sha(recovery):
    state, _, _ = recovery
    state["tasks"]["foundation"]["feature_sha"] = DEV
    with pytest.raises(RuntimeError, match="differs"):
        runner.reconcile_task("foundation", state)
    assert state["tasks"]["foundation"]["status"] == "BLOCKED"


def test_remote_existing_pr_prevents_implementation(monkeypatch):
    state = {"tasks": {"foundation": {"status": "PENDING", "attempts": 0}}}
    monkeypatch.setattr(runner, "git_clean", lambda: None)
    monkeypatch.setattr(runner, "pull_requests", lambda *args: [
        pr(3, "feature/foundation", "dev", FEATURE, "closed", True, INTEGRATION),
    ])
    monkeypatch.setattr(runner, "codex_task", lambda *args: pytest.fail("implementation restarted"))
    with pytest.raises(RuntimeError, match="reconcile before implementation"):
        runner.run_one({"id": "foundation"}, state)


def test_incomplete_pr_api_does_not_create_pr(monkeypatch):
    monkeypatch.setattr(runner, "repository_name", lambda: REPO)
    monkeypatch.setattr(runner, "command", lambda args: json.dumps({"message": "forbidden"}))
    with pytest.raises(RuntimeError, match="Incomplete PR list"):
        runner.open_pr("dev", "main", DEV, "title", "body")


def test_closed_unmerged_promotion_cannot_complete(monkeypatch):
    closed = pr(4, "dev", "main", DEV, "closed")
    monkeypatch.setattr(runner, "open_pr", lambda *args: 4)
    monkeypatch.setattr(runner, "command", lambda args: "")
    monkeypatch.setattr(runner, "pr_by_number", lambda *args: closed)
    with pytest.raises(RuntimeError, match="without confirmed merge"):
        runner.merge_pr("dev", "main", DEV, "title", "body", "--merge")
