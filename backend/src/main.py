"""Application entrypoint; no cloud clients are created at import time."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from src.errors import install_error_handlers


class HealthResponse(BaseModel):
    """Process liveness only, not dependency readiness."""

    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    """Build an independent application instance for serving or testing."""
    app = FastAPI(title="Enterprise RAG API", version="0.1.0")
    install_error_handlers(app)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        """Confirm the API process can serve requests without cloud calls."""
        return HealthResponse()

    return app
