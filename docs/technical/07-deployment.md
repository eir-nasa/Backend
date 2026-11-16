# 07 — Docker and Deployment

[Dockerfile](../../Dockerfile): uses `python:3.12-slim`, sets `WORKDIR /app`, copies `pyproject.toml` and `src/eir`, installs the package with pip, creates `/data`, assigns it to UID/GID `10001:10001`, and runs Uvicorn as that user on `0.0.0.0:8000`. It sets `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, and `EIR_DATABASE_PATH=/data/eir.sqlite3`. The project requires Python >=3.11; there is no dependency lock. No accounts are included.

[compose.yaml](../../compose.yaml) builds the `backend` service, restarts it with `unless-stopped`, publishes `127.0.0.1:8000:8000`, and mounts the named `eir-data` volume at `/data`. It uses the default Compose network; only the host can access the port published on loopback. The volume persists when the container is recreated, but not when the volume is deliberately removed. Keep a single process/instance: the current SQLite design is not multi-host.

The diagram distinguishes the configured container and volume from the planned, unverified proxy and DNS.

```mermaid
flowchart LR
  Client[Android client] -. Planned HTTPS .-> DNS[Planned Cloudflare DNS]
  DNS -.-> Caddy[Planned Caddy on EC2]
  subgraph Host[Planned host]
    Caddy -. proxy 127.0.0.1:8000 .-> Port[Loopback port 8000]
    Port --> API[FastAPI container:8000]
    API --> Vol[(eir-data volume: /data)]
  end
```

Run these commands from the repository root with Docker Engine and Compose installed:

```sh
docker compose up -d --build
docker compose ps
docker compose exec backend python -m eir.auth demo "Synthetic Demo" demo-mission
curl --fail http://127.0.0.1:8000/api/v1/health
docker compose logs backend
```

Provisioning prompts for a synthetic password without echoing it; do not include it in arguments or logs. Health should return `{"status":"ok"}` and checks API availability only. Container logs are accessed through Compose; configure protection and retention, and keep credentials out of logs. For a consistent backup, use the SQLite online backup API or stop the backend before copying; test restoration and protect both the database and backups. Do not delete the volume when recreating the container.

`EIR_DATABASE_PATH` is the only application-specific variable read by [config.py](../../src/eir/config.py); without it, the application uses `eir.sqlite3` relative to the working directory and rejects an empty string. Locally, run `uvicorn eir.main:app` after installing dependencies. Volume permissions have not been verified on a real host.

Plan only; no deployment has been performed: use EC2 Ubuntu; allow ports 80/443 and restrict SSH, do not open 8000; initially set Cloudflare DNS to DNS only; configure Caddy on the host with `reverse_proxy 127.0.0.1:8000` for a real domain; validate the certificate and HTTPS externally. If Cloudflare proxying is enabled, use Full (strict). The host, domain, DNS, certificates, permissions, and external connectivity remain unverified. `docker compose config --quiet` passed locally; the image was not built or run because access to the Docker socket was denied. A production deployment still needs a security review, tested backups/restoration, observability, and load/concurrency testing. See [implementation status](../IMPLEMENTATION_STATUS.md).
