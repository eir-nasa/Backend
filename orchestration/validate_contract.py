"""Ensure approved OpenAPI is syntactically valid and unmodified."""
import hashlib
import json
from pathlib import Path

import yaml
from openapi_spec_validator import validate_spec

ROOT = Path(__file__).resolve().parents[1]


def validate() -> None:
    contract = ROOT / "contracts/openapi.yaml"
    document = yaml.safe_load(contract.read_text(encoding="utf-8"))
    validate_spec(document)
    expected = json.loads((ROOT / "contracts/lock.json").read_text())["sha256"]
    digest = hashlib.sha256(contract.read_bytes()).hexdigest()
    if digest != expected:
        raise ValueError("Approved OpenAPI baseline changed; review and update lock explicitly.")


if __name__ == "__main__":
    validate()
    print("OpenAPI validated and lock verified")
