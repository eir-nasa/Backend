#!/usr/bin/env bash
set -euo pipefail
# Run inside the extracted starter package, after deciding on repository remote.
if [ -e .git ]; then echo 'Existing Git repository; bootstrap refused'; exit 1; fi
command -v git >/dev/null
command -v python >/dev/null
git init -b main
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m orchestration.validate_contract
python -m ruff check src tests orchestration
python -m pytest -q tests
git add .
git commit -m 'chore: bootstrap approved EIR contract and autonomous harness'
git branch dev
printf '\nLocal main and dev prepared. Set origin, push, protect both branches and authenticate gh/codex before --execute.\n'
