"""Independent, fail-closed quality gates. No Codex-produced verdict is trusted."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_command(args: list[str], cwd: Path = ROOT, timeout: int = 180) -> None:
    proc = subprocess.run(args, cwd=cwd, text=True, timeout=timeout, check=False)
    if proc.returncode:
        raise RuntimeError(f"Gate failed (exit {proc.returncode}): {' '.join(args)}")


def quality_gate(root: Path = ROOT) -> None:
    """Validate contract, lint, and actually collected backend tests."""
    run_command(["python", "-m", "orchestration.validate_contract"], root)
    run_command(["python", "-m", "ruff", "check", "src", "tests", "orchestration"], root)
    run_command(["python", "-m", "pytest", "-q", "tests"], root)
    # A backend task must ship substantive tests, not only harness tests.
    tests = list((root / "tests").glob("test_backend_*.py"))
    if not tests:
        raise RuntimeError("No backend behavior tests (tests/test_backend_*.py). Fail closed.")
