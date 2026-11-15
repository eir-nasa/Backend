"""Harness regression checks; backend behavior tests are additional and mandatory."""
from orchestration.runner import select_task, state_load, tasks


def test_first_task_is_foundation():
    items = tasks()
    state = state_load(items)
    assert select_task(items, state)["id"] == "foundation"


def test_dependencies_gate_progress():
    items = tasks()
    state = state_load(items)
    state["tasks"]["foundation"]["status"] = "COMPLETED"
    assert select_task(items, state)["id"] == "authentication"


def test_blocked_task_not_selected():
    items = tasks()
    state = state_load(items)
    state["tasks"]["foundation"]["status"] = "BLOCKED"
    assert select_task(items, state) is None
