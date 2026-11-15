# 01 — Descripción general

EIR busca apoyar el registro de salud y bienestar en un contexto de conectividad intermitente. Este backend proporciona un repositorio remoto de demostración para cuentas sintéticas: autenticación online, perfil, carga idempotente de registros, consulta de historiales y lectura de alertas ya almacenadas. No ofrece diagnósticos; las mediciones y autorreportes son experimentales y no están clínicamente validados.

La implementación es un monolito modular Python 3.11+ con FastAPI, Pydantic, SQLite y Uvicorn; el Dockerfile usa Python 3.12. Android se comunica por HTTP y es responsable de Room, outbox durable y mecanismos offline. Apollo y Google AI Edge están previstos en Android; aquí no hay inferencia LLM. La implementación Android y su integración no se encuentran en este repositorio y no se han verificado.

Las diez operaciones del contrato están presentes en el código, con limitaciones de compatibilidad OpenAPI detalladas en [API](04-api.md). Existe lectura de alertas, pero no generación ni Risk Engine. No hay registro público ni cuentas por defecto. El plan de despliegue HTTPS no acredita un servicio desplegado. Las pruebas locales y sus límites se describen en [pruebas](08-testing.md).

Fuentes: [handoff](../EIR_HANDOFF.md), [decisiones](../DECISIONS.md), [aplicación](../../src/eir/main.py), [configuración](../../pyproject.toml).
