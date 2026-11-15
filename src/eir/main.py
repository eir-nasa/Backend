"""FastAPI entry point for the EIR backend."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from eir.auth import router as auth_router
from eir.config import Settings
from eir.database import open_database
from eir.health_records import router as health_records_router
from eir.profiles import router as profiles_router


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"] = "ok"


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_settings = settings if settings is not None else Settings.from_environment()
        connection = open_database(resolved_settings.database_path)
        app.state.settings = resolved_settings
        app.state.database = connection
        try:
            yield
        finally:
            connection.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    app.include_router(auth_router)
    app.include_router(profiles_router)
    app.include_router(health_records_router)

    @app.get("/api/v1/health", response_model=HealthResponse, operation_id="getHealth")
    async def get_health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()
