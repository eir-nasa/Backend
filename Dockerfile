FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 EIR_DATABASE_PATH=/data/eir.sqlite3
WORKDIR /app
COPY pyproject.toml ./
COPY src/eir ./src/eir
RUN pip install --no-cache-dir . && \
    mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "eir.main:app", "--host", "0.0.0.0", "--port", "8000"]
