# Documentación técnica del backend EIR

Esta guía describe el código del repositorio examinado el 15 de noviembre de 2026. Se limita al backend y usa datos sintéticos. El contrato aprobado es [OpenAPI](../../contracts/openapi.yaml); las decisiones funcionales están en [EIR_HANDOFF](../EIR_HANDOFF.md) y [DECISIONS](../DECISIONS.md). La aprobación del contrato no demuestra que todas sus capacidades estén implementadas. El README raíz describe una etapa anterior y no refleja todas las rutas actuales.

Orden de lectura recomendado:

1. [Descripción general](01-overview.md): propósito, alcance y límites.
2. [Arquitectura](02-architecture.md): componentes, dependencias y flujos.
3. [Base de datos](03-database.md): esquema real, migraciones e integridad.
4. [API REST](04-api.md): operaciones, ejemplos y diferencias con el contrato.
5. [Seguridad](05-security.md): autenticación, sesiones y riesgos.
6. [Sincronización](06-synchronization.md): idempotencia y responsabilidades Android.
7. [Despliegue](07-deployment.md): Docker, configuración y plan de infraestructura.
8. [Pruebas](08-testing.md): comandos, resultados y cobertura funcional.
9. [Estado y limitaciones](09-status-and-limitations.md): clasificación y prioridades.

La evidencia primaria enlazada en cada documento prevalece sobre descripciones históricas. Las pruebas no demuestran seguridad total ni validez clínica.
