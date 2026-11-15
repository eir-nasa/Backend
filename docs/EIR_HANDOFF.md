# HANDOFF SCRIPT — EIR
## Contexto compartido para continuar el desarrollo
**Versión:** 1.0 de transferencia · **Fecha:** 14 de noviembre de 2026  
**Estado:** Inicio de implementación; definición funcional consolidada; contrato OpenAPI v0.1 aprobado por el equipo como baseline de trabajo.  
**Uso:** Copiar el documento completo a una nueva conversación o sesión con un asistente de IA. No contiene asignaciones de tareas ni roles individuales.

---

## 1. INSTRUCCIONES PARA LA SIGUIENTE SESIÓN

Estás retomando el proyecto **EIR**, del equipo **Synergy**, para el reto **“Create Health Monitoring Software for Astronauts on Space Missions”** de **NASA Space Apps Challenge 2026**.

1. Trata las decisiones consolidadas de este documento como el baseline aprobado. No revivas decisiones descartadas (React como frontend principal, Ollama o varios productos separados) sin una petición explícita.
2. **Trabaja contract-first.** El archivo real `eir-openapi-review-v0.1.yaml`, aprobado por el equipo, es la referencia de los endpoints, schemas y respuestas. Pide el archivo si no está adjunto; no reconstruyas de memoria su contenido exacto.
3. Antes de modificar el proyecto, inspecciona los archivos reales y el estado del repositorio. Distingue **prototipos previos, decisiones aprobadas, código existente, trabajo pendiente y capacidades probadas**.
4. No inventes código, pruebas exitosas, endpoints implementados, dispositivos disponibles, resultados de IA o infraestructura ya desplegada.
5. Mantén el código desacoplado y explica las dependencias entre módulos. No cambies unilateralmente contratos acordados.
6. No asignes personas a funciones ni distribuyas tareas: la organización del equipo se acordará aparte.
7. El usuario conversa en español. **Los entregables oficiales de hackathon —especialmente documentación de entrega y video— deben estar en inglés**. Idioma definitivo de app y código: por confirmar.
8. EIR es un **prototipo experimental**: no constituye un dispositivo médico, no diagnostica ni sustituye atención de profesionales.

## 2. IDENTIDAD Y OBJETIVO

- **Nombre final:** EIR.
- **Reto:** Software de monitoreo de salud para astronautas durante misiones espaciales.
- **Producto:** Una aplicación Android integrada, no SOLIS, ASTRA y EIR como productos separados.
- **Objetivo:** Monitorear salud física y bienestar psicológico mediante registros, tendencias, alertas explicables y asistencia conversacional, con capacidad de trabajar durante desconexiones y sincronizar los registros pendientes.
- **Público objetivo de la demo:** astronautas simulados, usando datos sintéticos.
- **Enfoque:** prototipo funcional comprensible, con límites científicos y de validación explícitos.

Los nombres **ASTRA Health** y **SOLIS** son antecedentes conceptuales y de diseño. **SpaceCrew Wellbeing** es el antecedente del módulo psicológico incorporado a EIR. **Apollo Mental** es el asistente conversacional de EIR.

## 3. STACK Y ARQUITECTURA ACORDADOS

**Aplicación principal:** Kotlin para Android, Jetpack Compose / Material 3. Pruebas previstas en dispositivo físico Android y emulador. La UI React previa es un prototipo/antecedente, no el frontend definitivo.

**Datos y tareas locales:** Room/SQLite, almacenamiento protegido por cuenta, Persistent Outbox, WorkManager para envío diferido y reintentos. Son decisiones de arquitectura, no características ya implementadas.

**IA:** **Google AI Edge on-device** reemplaza Ollama como dirección tecnológica. Evaluar LiteRT-LM para Apollo y modelos compatibles para análisis visual/voz; modelo concreto, formatos, rendimiento, soporte del hardware y resultados aún no validados. El servidor no está obligado a ejecutar inferencia LLM.

**Backend central:** Python, FastAPI, SQLite, motor de reglas/alertas, servicios de salud y bienestar, autenticación y Sync API. El backend puede desplegarse en **AWS EC2 Ubuntu** para la demo o en un **servidor LAN** para operar sin conexión pública a internet.

**Contratos:** OpenAPI **3.1.0**, enfoque **contract-first**, en `eir-openapi-review-v0.1.yaml` (baseline aprobado por el equipo). HTTP/JSON; HTTPS para acceso remoto desde Android. Android y FastAPI se desarrollan de forma independiente contra el contrato.

**HTTPS diseñado, no verificado:** dominio administrado en Cloudflare, subdominio de API aún no confirmado, Cloudflare **DNS only** inicialmente, AWS EC2 Ubuntu, **Caddy** como reverse proxy TLS hacia FastAPI en `127.0.0.1:8000`, certificado público automático. Puertos públicos 80/443; 8000 no expuesto. El modo de ejecución de FastAPI (Docker Compose, Docker directo o Uvicorn) sigue por confirmar. Para LAN offline se estudia DNS local con certificado válido preemitido por DNS-01 o una CA privada; no se considera implementado.

## 4. ALCANCE FUNCIONAL

**MVP aprobado:**
- **Dashboard:** indicadores de salud física, historial y tendencias; visualización de alertas.
- **Daily Check-in:** registros físicos y autorreportes de bienestar psicológico.
- **Risk Engine:** reglas y tendencias explicables; no diagnósticos.
- **Apollo Mental:** asistente conversacional local con Google AI Edge, orientación y explicaciones, sin prometer capacidad clínica.

**Captura experimental incluida en el objetivo:** cámara y micrófono, con análisis automatizado experimental de ambos. Falta definir **qué señales exactas** se analizarán, qué modelo se usará, qué fiabilidad puede justificarse y qué resultados se guardarán. No afirmar que una foto o voz permiten diagnosticar condiciones fisiológicas o psicológicas.

**Diseños de referencia:** se compartieron **14 capturas de bocetos** provenientes de SOLIS. Incluyen interfaz de Salud/Dashboard, visualización corporal, Hábitos, Bitácora, Agente IA, Daily Check-in secuencial (foto, voz, indicadores manuales, ánimo/energía), y SOS con guía por pasos. **Son bocetos sin código**: no constituyen funcionalidades implementadas ni amplían automáticamente el MVP. Hábitos, Body Scan avanzado y SOS necesitan priorización y validación adicional; las instrucciones de emergencia requieren protocolos autorizados.

**Bienestar:** el antecedente EIR utiliza cinco dimensiones de autorreporte, en escala 1–5: `mood`, `connection`, `energy`, `purpose`, `sleep`; `note` opcional hasta 500 caracteres según el contrato. No es una escala psicológica validada ni debe presentarse como diagnóstico.

## 5. OFFLINE-FIRST Y PUSH SYNC: NIVEL 2 APROBADO

Capacidades comprometidas en diseño:
1. Registrar datos de salud y bienestar localmente mientras FastAPI no está disponible.
2. Guardar el registro y su operación de salida **en una sola transacción local**.
3. Mantener **Persistent Outbox** tras reinicios; sincronizar con **WorkManager** cuando sea posible y haya autorización válida.
4. Enviar registros gradualmente en lotes y procesar **confirmación individual por registro**.
5. Evitar duplicados con `record_id` UUID estable y deduplicación transaccional en FastAPI; reenvíos idénticos se reconocen sin insertar otra fila.
6. Ante timeout no presumir éxito; reintentar. Ante mismo ID con contenido diferente, reportar conflicto sin sobrescribir silenciosamente.
7. Validar propiedad del registro usando la sesión autenticada; el `device_id` no sustituye credenciales.

**Fuera de Nivel 2:** reconciliación bidireccional continua, edición concurrente entre dispositivos y sincronización automática de archivos originales de audio/foto. La descarga inicial del historial al primer login en cada dispositivo **sí** está acordada, pero no convierte la arquitectura en Sync bidireccional completa.

**Importante:** no se requiere duplicar físicamente todas las tablas del servidor en Room; se comparten **modelos lógicos/JSON** y la app guarda metadatos locales adicionales (`sync_status`, intentos, cola). El contrato actual propone lotes de máximo **20** registros.

**Offline tiene tres significados:** (a) demo AWS conectada; (b) servidor FastAPI dentro de una LAN sin salida a internet; (c) teléfono sin conexión alguna, donde solo estarán disponibles los datos/cache y capacidades locales implementadas. No afirmar autonomía total de todos los módulos. Las alertas calculadas exclusivamente en servidor no aparecen de inmediato durante aislamiento del backend.

## 6. IDENTIDAD, SESIONES Y PRIVACIDAD: DECISIONES APROBADAS

1. Se admiten **cuentas individuales y dispositivos compartidos**. Cada astronauta ve únicamente sus propios registros.
2. **Login online** con usuario y contraseña; el dispositivo obtiene perfil e historial inicial desde FastAPI.
3. **Desbloqueo offline** de una cuenta previamente habilitada mediante reintroducción de contraseña y verificación local segura. **Nunca almacenar la contraseña original en texto plano ni reutilizar el hash del backend**. Diseño criptográfico exacto pendiente.
4. Ventana offline de **24 horas desde la última autenticación online**. Pasado ese plazo, **bloquear acceso a toda información privada**, conservando registros pendientes protegidos. No extender automáticamente la ventana por un simple refresh de token.
5. En dispositivos compartidos, cambiar de astronauta exige **cerrar sesión e iniciar otra desde cero**; una nueva sesión después de logout debe autenticarse online.
6. **Logout:** eliminar caché ya sincronizada, revocar/eliminar credenciales activas y **conservar cifrados los registros no sincronizados** junto con los mínimos metadatos necesarios para enviarlos cuando la misma cuenta vuelva a autenticarse. No subir registros de una cuenta bajo credenciales de otra.
7. Una cuenta puede utilizar **varios dispositivos**; cada uno conserva identificadores propios. La información creada offline en A solo estará disponible en B después del envío al servidor y una consulta de B.
8. Los dispositivos nuevos descargan **perfil + copia inicial del historial** desde FastAPI, idealmente paginada.
9. Las cuentas de prueba para el MVP serán **sintéticas, preconfiguradas en FastAPI**. No hay registro público de usuarios aprobado.
10. Revocación remota no puede comprobarse mientras no exista conexión; políticas para reloj manipulado, duración de tokens, caducidad y manejo criptográfico deben probarse y documentarse.

## 7. OPENAPI v0.1 — BASELINE APROBADO

**Referencia obligatoria:** `eir-openapi-review-v0.1.yaml`. La portada del archivo conserva la etiqueta `REVIEW DRAFT`, pues se creó antes de la aprobación; **la aprobación posterior del equipo se refiere a ese borrador como baseline de contratos**, no demuestra que las rutas estén desplegadas o que los detalles de seguridad hayan sido validados.

**Operaciones definidas (10):**

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/v1/health` | Disponibilidad de la API (no salud del astronauta) |
| POST | `/api/v1/auth/login` | Login online y asociación con dispositivo |
| POST | `/api/v1/auth/refresh` | Rotación de token remoto |
| POST | `/api/v1/auth/logout` | Revocación remota de sesión |
| GET | `/api/v1/users/me` | Perfil de cuenta autenticada |
| GET | `/api/v1/users/me/bootstrap` | Perfil + historial inicial paginado |
| GET | `/api/v1/users/me/health-records` | Historial físico autorizado |
| GET | `/api/v1/users/me/wellbeing-checkins` | Historial de bienestar autorizado |
| GET | `/api/v1/users/me/alerts` | Alertas existentes del servidor |
| POST | `/api/v1/sync/records` | Push Sync con acuses individuales |

El archivo define **Bearer authentication**, `LoginRequest`, `LoginResponse`, `SessionTokens`, `AstronautProfile`, `HealthPayload`, `WellbeingPayload`, páginas de historia, `RiskAlert`, `SyncBatchRequest`, `SyncBatchResponse`, `ApiError` y otros schemas asociados.

**Sync:** `records` contiene elementos tipados `health_record` o `wellbeing_checkin`, identificadores UUID estables, `recorded_at` y `schema_version: 1`; límite de lote 20. Resultados por registro: `accepted`, `duplicate`, `rejected`, `conflict`, `retryable`. Se comprueba autorización por Bearer token; el servidor infiere propietario desde la sesión, no desde un `astronaut_id` libre. El endpoint se propone bajo `/api/v1`; código anterior utilizaba otras rutas.

**Estado técnico:** la sintaxis YAML y referencias locales del archivo se comprobaron en la sesión de creación; no hay evidencia todavía de validación formal completa de OpenAPI, generación de clientes, pruebas contractuales end-to-end ni implementación de esas diez operaciones. El host `https://api.example.org` es **placeholder**, no una dirección desplegada.

**Cambios futuros:** si el baseline aprobado requiere correcciones o extensiones, acordar primero el cambio en la especificación (versionado/revisión), luego adaptar backend y Android. No introducir endpoints autónomos contradictorios. Apollo on-device no requiere un endpoint remoto de inferencia; servicios futuros de contexto deben justificarse y contratarse explícitamente.

## 8. HTTPS Y DESPLIEGUE: PLAN APROBADO, NO EJECUTADO

- DNS: **Cloudflare** (control y subdominio concreto todavía por confirmar).
- Infraestructura demo: **AWS EC2 Ubuntu**.
- Reverse proxy recomendado: **Caddy instalado en el host**.
- Cloudflare: registro A hacia la IP de EC2, inicialmente **DNS only** (nube gris), para la primera emisión/verificación.
- Seguridad EC2: 443 público, 80 para emisión/redirección y SSH restringido; **no exponer 8000**.
- Caddy: `api.DOMINIO_REAL` → `reverse_proxy 127.0.0.1:8000`.
- Backend: si Docker, publicar `127.0.0.1:8000:8000`; si Uvicorn directo, bind `127.0.0.1:8000`.
- Android: base URL `https://api.DOMINIO_REAL/`; validar normalmente certificados TLS; **no desactivar comprobaciones TLS**.
- Si Cloudflare se pone Proxied más adelante: usar **Full (strict)**, no Flexible.
- LAN futura: DNS local y certificados públicos por desafío DNS-01 previamente emitidos o CA privada; aún no construida.

**Pendientes de infraestructura:** subdominio definitivo, permisos DNS/EC2, IP estable, método real de despliegue FastAPI, funcionamiento y pruebas de HTTPS. No afirmar que SSL/TLS ya funciona.

## 9. ESTADO REAL CONOCIDO DE LOS ANTECEDENTES

- **SOLIS:** capturas de UI y prototipo interactivo React; no se ha verificado que exista una implementación funcional nativa Kotlin. Las 14 capturas son referencias visuales.
- **EIR / SpaceCrew Wellbeing:** antecedente con Python/FastAPI, SQLite, React/Vite, Docker Compose, módulos de bienestar y Apollo determinista; algunos tests reportados por el handoff previo. No asumir que ese código esté integrado ya en la nueva app Android.
- **Ollama:** fue explorado antes, pero está **reemplazado por Google AI Edge on-device** en la definición vigente; no afirmar que el modelo Ollama corrió correctamente en EC2.
- **Google AI Edge:** dirección decidida; aún sin modelo/hardware/inferencia verificados.
- **OpenAPI:** borrador **aprobado para iniciar desarrollo**, pero la aprobación del contrato **no significa implementación exitosa**.
- **AWS + Caddy HTTPS:** guía acordada, configuración y despliegue aún no verificados.
- **Datos NASA:** solo fuentes científicas/educativas de contexto, no datos biomédicos reales de astronautas ni telemetría NASA.

## 10. ENTREGABLES DEL PROYECTO

**Producto técnico:** aplicación Android; backend FastAPI/SQLite; integración mediante OpenAPI; sincronización Nivel 2; prueba de Apollo local; demostración de captura experimental según factibilidad; despliegue HTTPS validado.

**Documento formal detallado (obligatorio):**
1. Project Overview
2. Problem Statement and Justification
3. Objectives, Scope and Limitations
4. Scientific Background and References
5. Functional and Non-Functional Requirements
6. System Architecture and Technology Choices
7. Data Models and OpenAPI Contract
8. Offline-First and Synchronization Design
9. Authentication, Privacy and Security
10. Implementation and User Interface
11. Testing, Evaluation and Evidence
12. Results, Limitations and Future Work
13. References and Appendices

**Hackathon:** documentación y video de entrega en **inglés**. El idioma de la interfaz y las convenciones de nombres del código aún no se han decidido.

Para cualquier funcionalidad, distinguir **Proposed / Implemented / Tested / Experimental / Future Work**, e incluir evidencias verificables. Reportar claramente uso de datos sintéticos. No atribuir validación clínica a promedios de autorreportes, análisis facial o audio.

## 11. DECISIONES AÚN ABIERTAS

- Idioma de interfaz Android y convenciones de código.
- Subdominio real, acceso a Cloudflare/EC2 y despliegue real del backend.
- Modelo específico de Google AI Edge y compatibilidad/rendimiento en teléfono físico y emulador.
- Variables y métodos de análisis experimental de cámara/micrófono, su validez y si solo se guardan resultados locales.
- Diseño preciso del verificador de contraseña offline, aislamiento/cifrado por cuenta, duración/rotación de tokens, manejo de logout offline y protección ante alteración del reloj.
- Umbrales y evidencia científica del Risk Engine; fuentes y frecuencia de datos.
- Semántica de historial paginado/bootstrap, consistencia de snapshots, migración desde rutas heredadas, política de errores y pruebas contractuales.
- Priorización final de funciones ilustradas fuera del MVP (Hábitos, Body Scan avanzado, SOS).
- Organización y asignación de tareas: **deliberadamente omitidas en este handoff**.

## 12. CRITERIOS PARA COMENZAR EL DESARROLLO

1. Obtener los repositorios y artefactos **reales**; comprobar estructura, dependencias, comandos, tests y estado Git sin sobrescribir trabajo previo.
2. Colocar el `eir-openapi-review-v0.1.yaml` aprobado como contrato de referencia y verificar con herramientas de OpenAPI antes de generar tipos o escribir endpoints.
3. Definir mocks contractuales para permitir desarrollo paralelo independiente del despliegue AWS.
4. Implementar recorridos verticales verificables: login + bootstrap; check-in Room + Outbox; Push Sync con idempotencia; consulta y alertas; Apollo on-device cuando el modelo se compruebe.
5. Probar situaciones offline, reinicios, duplicados, expiración de sesión, aislamiento entre astronautas y desconexión después de persistir pero antes de recibir la confirmación.
6. Separar alcance **probado** de alcance **propuesto** en el documento formal y en la demostración.

### Referencias públicas útiles
- Android offline-first: https://developer.android.com/topic/architecture/data-layer/offline-first
- Android WorkManager: https://developer.android.com/topic/libraries/architecture/workmanager
- OpenAPI: https://spec.openapis.org/oas/v3.1.0
- Caddy Automatic HTTPS: https://caddyserver.com/docs/automatic-https
- Cloudflare DNS: https://developers.cloudflare.com/dns/
- FastAPI HTTPS: https://fastapi.tiangolo.com/deployment/https/
- NASA HRP, isolation and confinement: https://www.nasa.gov/hrp/hazard-isolation-and-confinement/

---

**INSTRUCCIÓN DE CONTINUIDAD:** Confirma primero qué archivos reales te proporcionaron y qué parte del sistema se va a desarrollar. Con este baseline, ayuda a implementar o documentar EIR respetando OpenAPI y las decisiones aprobadas. No presupongas tareas asignadas a ninguna persona.
