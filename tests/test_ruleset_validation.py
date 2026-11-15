"""Ruleset and interrupted promotion regression tests with mocked GitHub responses."""
import copy
import json

import pytest

from orchestration import runner


@pytest.fixture
def github(monkeypatch):
    rules = [
        {"ruleset_id": 27297017, "type": "pull_request", "parameters": {
            "required_approving_review_count": 0, "require_code_owner_review": False,
            "require_last_push_approval": False,
        }},
        {"ruleset_id": 27297017, "type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "quality"}],
        }},
        {"ruleset_id": 27297017, "type": "non_fast_forward"},
        {"ruleset_id": 27297017, "type": "deletion"},
    ]
    responses = {
        "repo": {"allow_auto_merge": True, "allow_squash_merge": True,
                 "allow_merge_commit": True},
        "dev": copy.deepcopy(rules), "main": copy.deepcopy(rules),
        "detail": {"id": 27297017, "enforcement": "active", "target": "branch",
                   "bypass_actors": []},
    }

    def command(args, **kwargs):
        if args[:3] == ["gh", "auth", "status"]:
            return ""
        endpoint = args[-1]
        if endpoint == "repos/{owner}/{repo}":
            return json.dumps(responses["repo"])
        if "/rules/branches/" in endpoint:
            return json.dumps([responses[endpoint.split("/")[-1].split("?")[0]]])
        if "/rulesets/" in endpoint:
            return json.dumps(responses["detail"])
        raise AssertionError(args)

    monkeypatch.setattr(runner.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(runner, "command", command)
    return responses


def test_effective_rules_for_both_branches(github):
    runner.verify_remote_protections()


@pytest.mark.parametrize("mutation", [
    lambda r: r["main"].clear(),
    lambda r: r["dev"].pop(),
    lambda r: r["dev"][0]["parameters"].update(required_approving_review_count=1),
    lambda r: r["dev"][0]["parameters"].pop("require_code_owner_review"),
    lambda r: r["main"][1]["parameters"].update(required_status_checks=[]),
    lambda r: r["detail"].update(enforcement="evaluate"),
    lambda r: r["detail"].pop("bypass_actors"),
    lambda r: r["detail"].update(bypass_actors=[{"actor_type": "RepositoryRole"}]),
    lambda r: r["repo"].update(allow_auto_merge=False),
    lambda r: r["repo"].pop("allow_merge_commit"),
    lambda r: r["main"][0].pop("ruleset_id"),
])
def test_missing_or_incompatible_protection_fails_closed(github, mutation):
    mutation(github)
    with pytest.raises(RuntimeError):
        runner.verify_remote_protections()


def test_permission_error_fails_closed(github, monkeypatch):
    def denied(*args, **kwargs):
        raise RuntimeError("API permission denied")

    monkeypatch.setattr(runner, "command", denied)
    with pytest.raises(RuntimeError):
        runner.verify_remote_protections()


@pytest.mark.parametrize("pr", [
    {"state": "MERGED", "baseRefName": "main", "headRefOid": "old", "mergedAt": "now"},
    {"state": "MERGED", "baseRefName": "dev", "headRefOid": "sha", "mergedAt": "now"},
    {"state": "MERGED", "baseRefName": "main", "headRefOid": "sha", "mergedAt": None},
    {"state": "UNKNOWN", "baseRefName": "main", "headRefOid": "sha"},
])
def test_merge_must_match_and_be_confirmed(monkeypatch, pr):
    monkeypatch.setattr(runner, "command", lambda *args, **kwargs: json.dumps(pr))
    with pytest.raises(RuntimeError):
        runner.confirmed_merge("dev", "main", "sha")


def test_confirmed_merge(monkeypatch):
    pr = {"state": "MERGED", "baseRefName": "main", "headRefOid": "sha", "mergedAt": "now"}
    monkeypatch.setattr(runner, "command", lambda *args, **kwargs: json.dumps(pr))
    assert runner.confirmed_merge("dev", "main", "sha") == "MERGED"


def test_interrupted_task_requires_reconciliation(monkeypatch):
    monkeypatch.setattr(runner, "tasks", lambda: [{"id": "x", "dependencies": []}])
    monkeypatch.setattr(runner, "state_load", lambda items: {
        "tasks": {"x": {"status": "IN_PROGRESS", "attempts": 1}},
    })
    monkeypatch.setattr(runner, "git_clean", lambda: None)
    monkeypatch.setattr("sys.argv", ["runner", "--execute"])
    with pytest.raises(RuntimeError, match="manual merge and state reconciliation"):
        runner.main()
