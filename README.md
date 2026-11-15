# EIR Backend

Backend de demostración de **EIR**, una aplicación de monitoreo de salud y bienestar para astronautas desarrollada en el contexto de NASA Space Apps Challenge 2026. Ofrece una API REST para cuentas sintéticas, registros de salud y bienestar, sincronización y consulta de alertas existentes.

Las mediciones y los autorreportes son experimentales y no constituyen diagnósticos ni capacidades clínicamente validadas. El repositorio está destinado a datos de demostración sintéticos; no debe contener información real de astronautas o pacientes.

## Alcance

El backend implementa autenticación online por dispositivo, rotación y revocación de sesiones, consulta del perfil y del historial, y carga de registros con identificadores estables y resultados individuales. La lectura de alertas está disponible, pero **no existe generación de alertas ni Risk Engine**: las reglas y umbrales siguen pendientes de aprobación.

Android es responsable de Room, el outbox durable y los mecanismos offline. Apollo está previsto para ejecutarse localmente en Android mediante Google AI Edge; este backend no realiza inferencia de modelos. La implementación Android y su integración no forman parte de este repositorio.

La API contiene las diez operaciones del [contrato OpenAPI aprobado](contracts/openapi.yaml). El documento OpenAPI generado por FastAPI presenta diferencias de esquemas, seguridad y códigos de respuesta respecto al contrato; consulte [API REST](docs/technical/04-api.md) antes de generar clientes. La nota del propio contrato que cuestiona su aprobación quedó obsoleta según [DECISIONS.md](docs/DECISIONS.md).

## Tecnologías y estructura

- Python 3.11+, FastAPI, Pydantic y Uvicorn.
- SQLite con migraciones aplicadas al iniciar la aplicación.
- Docker y Docker Compose para ejecución local preparada.
- pytest, Ruff y validación de OpenAPI para comprobaciones de desarrollo.

| Ruta | Contenido |
|---|---|
| `src/eir/` | Aplicación, autenticación, perfiles, registros, sincronización, alertas y base de datos. |
| `contracts/` | Contrato OpenAPI aprobado y archivo de integridad. |
| `tests/` | Pruebas del backend y de la infraestructura de automatización. |
| `docs/` | Decisiones, handoff, estado y documentación técnica. |
| `orchestration/` | Infraestructura de automatización y gobernanza del repositorio. |
| `Dockerfile`, `compose.yaml` | Definiciones para construir y ejecutar el servicio. |

## Ejecución local

Cree un entorno virtual e instale el paquete con sus dependencias de desarrollo:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Inicie el servidor y consulte su disponibilidad:

```sh
uvicorn eir.main:app
```

```sh
curl --fail http://127.0.0.1:8000/api/v1/health
```

La respuesta esperada es `{"status":"ok"}`. Este endpoint comprueba la disponibilidad de la API, no la salud de una persona. La configuración `EIR_DATABASE_PATH` selecciona el archivo SQLite; su valor predeterminado es `eir.sqlite3` en el directorio de ejecución. Al iniciar se aplican las migraciones pendientes.

No existen cuentas por defecto ni registro público. Para crear una cuenta de demostración sintética, ejecute:

```sh
python -m eir.auth demo "Synthetic Demo" demo-mission
```

El comando solicita y confirma la contraseña sin mostrarla. No incluya contraseñas ni tokens en argumentos, archivos versionados o logs. El archivo SQLite contiene información de cuentas, sesiones y registros y debe protegerse junto con sus respaldos.

## Docker Compose

Con Docker Engine y el plugin Compose instalados:

```sh
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:8000/api/v1/health
```

Compose publica el servicio en `127.0.0.1:8000` y conserva la base en el volumen `eir-data`, montado en `/data`. Para aprovisionar una cuenta dentro del contenedor:

```sh
docker compose exec backend python -m eir.auth demo "Synthetic Demo" demo-mission
```

El plan de EC2, Cloudflare DNS y Caddy está documentado, pero su despliegue externo y HTTPS no se han verificado. Consulte [Docker y despliegue](docs/technical/07-deployment.md) para conocer persistencia, backups y requisitos pendientes.

## Pruebas

Con las dependencias de desarrollo instaladas:

```sh
python -m pytest -q tests
python -m ruff check src tests orchestration
python -m orchestration.validate_contract
```

La validación del contrato comprueba su estructura y el lock; no demuestra por sí sola que la implementación sea completamente compatible. Los resultados y límites de las pruebas se detallan en [pruebas y validaciones](docs/technical/08-testing.md).

## Documentación

La [documentación técnica](docs/technical/README.md) cubre arquitectura, base de datos, API, seguridad, sincronización, despliegue, pruebas y estado de implementación. Las decisiones funcionales se encuentran en [EIR_HANDOFF.md](docs/EIR_HANDOFF.md) y [DECISIONS.md](docs/DECISIONS.md); el [estado de implementación](docs/IMPLEMENTATION_STATUS.md) recoge limitaciones adicionales.
