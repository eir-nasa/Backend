# 04 — API REST

La fuente normativa es el [contrato aprobado](../../contracts/openapi.yaml); esta página describe el comportamiento observado en [routers](../../src/eir/). Todas las rutas usan `/api/v1`. No existe documentación interactiva ni endpoint HTTP OpenAPI: `docs_url`, `redoc_url` y `openapi_url` están desactivados. Las respuestas de error propias usan `{"code":"unauthorized","message":"Invalid credentials"}` para 401, con `WWW-Authenticate: Bearer`. Fallos de validación de FastAPI devuelven 422 con `detail`, estructura distinta de `ApiError`.

| Método y ruta | Auth | Request | Response / errores observables |
|---|---|---|---|
| GET `/health` | No | Sin cuerpo | 200 `{"status":"ok"}` |
| POST `/auth/login` | No | JSON `username`, `password`, `device_id`; strings no vacíos, dispositivo máximo 128; sin extras | 200 tokens, `user` y `online_authenticated_at`; 401 credenciales incorrectas; 422 validación |
| POST `/auth/refresh` | No | JSON `refresh_token`, `device_id`, strings no vacíos, sin extras | 200 tokens rotados; 401 token, dispositivo o expiración inválidos; 422 validación |
| POST `/auth/logout` | Bearer | Sin cuerpo requerido | 204 sin cuerpo; 401 sesión inválida o ya revocada |
| GET `/users/me` | Bearer | Sin cuerpo | 200 perfil; 401 |
| GET `/users/me/bootstrap` | Bearer | `cursor` opcional, `limit` 1–100, default 30 | 200 perfil, `health_records`, `wellbeing_checkins`, `next_cursor`; 401; 422 cursor o límite inválido |
| GET `/users/me/health-records` | Bearer | Mismo cursor/límite | 200 `items`, `next_cursor`; 401; 422 |
| GET `/users/me/wellbeing-checkins` | Bearer | Mismo cursor/límite | 200 `items`, `next_cursor`; 401; 422 |
| GET `/users/me/alerts` | Bearer | Sin cuerpo | 200 `items`; 401. Devuelve solo alertas existentes, sin paginación ni generación |
| POST `/sync/records` | Bearer | `device_id` y `records`; véase abajo | 200 `results`, `server_time`; 401; 422 `invalid_batch` para JSON/envoltura/UUID inválidos |

Perfil: `user_id`, `astronaut_id`, `username`, `display_name`, `mission_id`, `profile_version`. Login agrega `access_token`, `refresh_token`, `token_type: Bearer`, `expires_in: 900` y `online_authenticated_at` UTC; refresh devuelve esos cuatro campos de sesión. No se reproducen credenciales en ejemplos. Para probar login suministre interactivamente una contraseña sintética, sin registrarla en el historial de shell. Use un cliente que proteja el token al incluir `Authorization: Bearer <access_token>`.

Ejemplo sintético de sync (el UUID es ilustrativo):

```json
{"device_id":"demo-device","records":[{"record_id":"550e8400-e29b-41d4-a716-446655440000","recorded_at":"2026-01-01T12:00:00Z","schema_version":1,"type":"health_record","payload":{"heart_rate_bpm":70}}]}
```

Respuesta ilustrativa: `{"results":[{"record_id":"550e8400-e29b-41d4-a716-446655440000","status":"accepted"}],"server_time":"2026-01-01T12:00:01+00:00"}`. Un replay equivalente produce `duplicate`; datos distintos o colisión con otra cuenta/tipo producen `conflict`; invalidación de un elemento produce `rejected`; fallo SQLite produce `retryable`. Un UUID inválido invalida todo el lote antes de escribir. `device_id` tiene 1–128 caracteres, `records` entre 1 y 20 y no se permiten claves adicionales en la envoltura. No se comprueba que el `device_id` del lote coincida con el de la sesión.

Cada registro exige UUID, fecha ISO con zona horaria, `schema_version` entero estricto igual a 1, tipo y payload. `health_record`: al menos uno de `heart_rate_bpm`, `glucose_mg_dl`, `temperature_c`, `sleep_hours`, `systolic_bp_mmhg`, `diastolic_bp_mmhg`; valores numéricos finitos, no negativos salvo temperatura; sueño 0–24; ritmo y presiones enteros. `wellbeing_checkin`: `mood`, `connection`, `energy`, `purpose`, `sleep`, enteros de 1 a 5, y `note` opcional string hasta 500 caracteres. Los payloads rechazan campos extra y null; la envoltura del registro admite campos extra. Se guardan fechas normalizadas a UTC y las respuestas de historial agregan `received_at`. Cursores son opacos, se ordena por UUID textual y no existe snapshot; bootstrap comparte el límite entre los dos tipos.

Alertas existentes tienen `alert_id`, `severity` (`info`, `warning`, `critical`), `rule_id`, `explanation`, `created_at` y opcional `evidence_record_ids`. Un ejemplo de respuesta vacía es `{"items":[]}`, que no demuestra evaluación.

## Compatibilidad

Las pruebas comparan inventario de rutas y operationId, el esquema de perfil y algunas instancias de respuesta con el baseline, no toda la semántica. `app.openapi()` omite esquema Bearer, request de sync y varios esquemas y estados; describe logout como 200 aunque devuelve 204. El contrato declara 429 para login y sync pero no hay rate limiting; 400, 413 y 503 de sync tampoco están implementados explícitamente como respuestas de aplicación. La implementación emite 422 de validación de FastAPI en rutas donde el contrato no lo documenta, y ese formato no es `ApiError`. Estas observaciones no garantizan exhaustividad; faltan pruebas de conformidad completas. El texto del contrato que niega aprobación está obsoleto según [DECISIONS](../DECISIONS.md).
