# 07 — Docker y despliegue

[Dockerfile](../../Dockerfile): `python:3.12-slim`, `WORKDIR /app`, copia `pyproject.toml` y `src/eir`, instala el paquete con pip, crea `/data`, lo asigna a UID/GID `10001:10001` y ejecuta Uvicorn como ese usuario en `0.0.0.0:8000`. Establece `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1` y `EIR_DATABASE_PATH=/data/eir.sqlite3`. El proyecto requiere Python >=3.11; no hay lock de dependencias. No se incluyen cuentas.

[compose.yaml](../../compose.yaml) construye el servicio `backend`, reinicia con `unless-stopped`, publica `127.0.0.1:8000:8000` y monta volumen nombrado `eir-data` en `/data`. Usa la red predeterminada de Compose; solo el host accede al puerto publicado por loopback. El volumen persiste al recrear el contenedor, no al eliminar deliberadamente el volumen. Mantener un solo proceso/instancia: el diseño SQLite actual no es multihost.

El diagrama distingue el contenedor y volumen configurados del proxy y DNS planificados, no verificados.

```mermaid
flowchart LR
  Client[Cliente Android] -. HTTPS previsto .-> DNS[Cloudflare DNS previsto]
  DNS -.-> Caddy[Caddy en EC2 previsto]
  subgraph Host[Host previsto]
    Caddy -. proxy 127.0.0.1:8000 .-> Port[Puerto loopback 8000]
    Port --> API[Contenedor FastAPI:8000]
    API --> Vol[(Volumen eir-data: /data)]
  end
```

Comandos desde la raíz con Docker Engine y Compose instalados:

```sh
docker compose up -d --build
docker compose ps
docker compose exec backend python -m eir.auth demo "Synthetic Demo" demo-mission
curl --fail http://127.0.0.1:8000/api/v1/health
docker compose logs backend
```

El aprovisionamiento solicita una contraseña sintética sin eco; no incluirla en argumentos ni logs. Health debe devolver `{"status":"ok"}` y solo comprueba disponibilidad de API. Los logs de contenedor se consultan con Compose; configurar protección, retención y evitar credenciales. Para copia consistente usar SQLite online backup API o detener backend antes de copiar; probar restauración y proteger tanto base como respaldos. No borrar el volumen durante recreación.

`EIR_DATABASE_PATH` es la única variable propia leída por [config.py](../../src/eir/config.py); sin ella usa `eir.sqlite3` relativo al directorio de ejecución y rechaza cadena vacía. Localmente puede ejecutarse `uvicorn eir.main:app` tras instalar dependencias. No se han verificado permisos del volumen en un host real.

Plan, no despliegue ejecutado: EC2 Ubuntu; permitir 80/443 y restringir SSH, no abrir 8000; DNS Cloudflare inicialmente DNS only; Caddy en host con `reverse_proxy 127.0.0.1:8000` para un dominio real; validar certificado y HTTPS desde fuera. Si se activa proxy Cloudflare, usar Full (strict). Host, dominio, DNS, certificados, permisos y conectividad externa siguen sin verificar. La configuración `docker compose config --quiet` pasó localmente; no se construyó ni ejecutó imagen porque el socket Docker denegó acceso. En producción faltan revisión de seguridad, backups/restauración probados, observabilidad y pruebas de carga/concurrencia. Véase [estado de implementación](../IMPLEMENTATION_STATUS.md).
