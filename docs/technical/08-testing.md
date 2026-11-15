# 08 — Pruebas y validaciones

Se usa pytest, FastAPI TestClient/httpx, PyYAML, jsonschema y openapi-spec-validator; Ruff comprueba reglas seleccionadas E4, E7, E9, F e I. Dependencias declaradas en [pyproject.toml](../../pyproject.toml). Los tests `test_backend_*` cubren aplicación; `test_orchestrator`, `test_pr_recovery` y `test_ruleset_validation` cubren la infraestructura de gobernanza, sin ejecutar el roadmap.

Comandos ejecutados desde raíz el 15 de noviembre de 2026, con el entorno virtual existente y sin caché de pytest/Ruff:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ruff check --no-cache src tests orchestration
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m orchestration.validate_contract
docker compose config --quiet
```

Resultados reales: **79 passed en 2.70 s**; Ruff `All checks passed!`; validador `OpenAPI validated and lock verified`; Compose config terminó con código 0. El Python del sistema carece de pytest, Ruff y PyYAML, pero el entorno virtual existente sí permitió los comandos anteriores. `docker info` falló por permisos sobre el socket; no se hizo build ni prueba real de contenedor. No se encontró `mmdc`, por lo que los diagramas no se validaron con un renderizador Mermaid.

Cobertura funcional ejercitada por los tests: autenticación, vencimientos, rotación, sesiones y aislamiento; configuración, ciclo de vida y rollback de migraciones; validación y paginación de ambos tipos, bootstrap, alertas existentes y ausencia de generación; sync, replay, conflicto y fallo de almacenamiento; viaje sintético con reinicio. Los tests de despliegue inspeccionan archivos y ejecutan el comando de app de forma local, no construyen una imagen. Las pruebas de integración comparan inventario y operationId de OpenAPI, esquema de perfil y algunas respuestas contra JSON Schema; el validador comprueba la especificación y hash, no equivalencia completa con FastAPI. Véase [test_backend_integration.py](../../tests/test_backend_integration.py).

No hay porcentaje de cobertura medido aquí. Las pruebas no verifican Android, acceso concurrente real, seguridad exhaustiva, rendimiento, conectividad externa, TLS ni despliegue en AWS. Su éxito tampoco acredita validación clínica.
