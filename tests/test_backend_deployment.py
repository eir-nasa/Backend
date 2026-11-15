import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import yaml

from eir.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_compose_keeps_backend_on_loopback_and_persists_database():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    backend = compose["services"]["backend"]
    assert list(compose["services"]) == ["backend"]
    assert backend["ports"] == ["127.0.0.1:8000:8000"]
    assert backend["volumes"] == ["eir-data:/data"]
    assert "eir-data" in compose["volumes"]
    assert backend["restart"] == "unless-stopped"
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "EIR_DATABASE_PATH=/data/eir.sqlite3" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "chown 10001:10001 /data" in dockerfile


def test_image_command_and_database_lifecycle(monkeypatch, tmp_path):
    dockerfile = (ROOT / "Dockerfile").read_text()
    command = json.loads(next(line[4:] for line in dockerfile.splitlines()
                              if line.startswith("CMD ")))
    assert command == ["uvicorn", "eir.main:app", "--host", "0.0.0.0", "--port", "8000"]
    path = tmp_path / "eir.sqlite3"
    monkeypatch.setenv("EIR_DATABASE_PATH", str(path))

    async def exercise():
        app = create_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/health")
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}
                assert (await client.get("/api/v1/users/me")).status_code == 401
                assert (await client.get("/health")).status_code == 404
            app.state.database.execute("INSERT INTO eir_metadata VALUES ('deployment', 'saved')")
            app.state.database.commit()
        app = create_app()
        async with app.router.lifespan_context(app):
            assert app.state.database.execute("SELECT value FROM eir_metadata").fetchone() == (
                "saved",
            )

    asyncio.run(exercise())
    assert path.is_file()
    env = os.environ | {"EIR_DATABASE_PATH": str(tmp_path / "missing" / "eir.sqlite3")}
    failed = subprocess.run([sys.executable, "-m", *command], env=env, capture_output=True,
                            timeout=10)
    assert failed.returncode != 0
    assert b"unable to open database file" in failed.stderr
