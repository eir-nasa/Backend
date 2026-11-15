# 09 — Estado de implementación y mejoras

La clasificación se basa en código y pruebas locales descritas en [pruebas](08-testing.md); «verificada» significa para los escenarios probados, no certificada para producción.

| Estado | Funcionalidad y evidencia |
|---|---|
| Implementada y verificada | Health, configuración y migraciones transaccionales: [foundation](../../tests/test_backend_foundation.py). Login, rotación, expiración, logout y separación de sesiones: [auth](../../tests/test_backend_auth.py). Perfil e historiales por cuenta, bootstrap, sync con replay/conflicto y persistencia/reinicio: [integration](../../tests/test_backend_integration.py), tests específicos de sync e historiales. |
| Implementada y verificada | Consulta aislada de alertas existentes y ausencia de generación al guardar registros: [alerts tests](../../tests/test_backend_alerts.py). |
| Parcial | Compatibilidad OpenAPI: rutas e IDs coinciden y se validan ejemplos; faltan security scheme, schemas y estados en documento generado, y logout se describe 200 en lugar de 204. Rate limiting y algunos errores del contrato no implementados. Véase [API](04-api.md). |
| Parcial | Dockerfile y Compose definidos; configuración estática verificada, build/runtime no. HTTPS y despliegue externos no verificados. |
| Parcial | Paginación por UUID sin snapshot; registros insertados antes del cursor pueden omitirse. `device_id` de sync se valida pero no se vincula a la sesión. No se han probado garantías generales de concurrencia. |
| Pendiente | Rate limiting, revisión de seguridad, pruebas de carga/concurrencia y conformidad integral; backups y recuperación ensayados; infraestructura HTTPS. Android Room/outbox, cifrado y comportamiento offline no son verificables en este repositorio. |
| Bloqueada por diseño | Generación de alertas/Risk Engine: reglas, evidencia y umbrales no especificados ni aprobados. Una lista vacía no indica evaluación. Aprovisionamiento posterior al MVP, política de expiración y diseño criptográfico offline requieren decisiones. |
| Pendiente y externo | Verificación de modelo, dispositivo e inferencia Apollo/Google AI Edge en Android. No existe inferencia en backend. |

Prioridades propuestas:

1. **Riesgo de seguridad:** definir y aplicar controles frente a fuerza bruta, revisar implementación de tokens, manejo de claves y acceso al volumen; verificar TLS y política de logs antes de cualquier exposición. Mantener solo datos sintéticos.
2. **Errores funcionales/contrato:** acordar y corregir divergencias de OpenAPI generado, códigos y formas de error; añadir pruebas semánticas de contrato completas. Decidir si el `device_id` de sync debe compararse con la sesión antes de cambiar comportamiento. Revisar concurrencia SQLite y semántica de páginas.
3. **Operación:** construir y ejecutar imagen en host autorizado; probar persistencia, backup/restauración y recuperación; validar dominio, DNS, Caddy y certificado externo.
4. **Bloqueos funcionales:** acordar reglas, evidencia y límites de Risk Engine antes de implementarlo; resolver diseño offline y política de sesión con responsables de Android. Ninguna regla experimental debe presentarse como diagnóstico.
5. **Opcional:** mejorar observabilidad sin datos sensibles y documentar decisiones de rendimiento y operación tras obtener requisitos.

El [README raíz](../../README.md) sigue diciendo que no hay endpoints; es histórico y contradice el código. La nota no aprobada dentro del contrato también es histórica respecto de la aprobación, según [DECISIONS](../DECISIONS.md). No se verificó un despliegue real ni el frontend.
