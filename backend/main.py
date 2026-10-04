"""Detecto FastAPI application entry point.

Run from the project root:
    uvicorn backend.main:app --reload
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.db import get_repository
from backend.routes import detect
from backend.services.detector import get_detector
from backend.utils.preprocessing import ImageError

settings = get_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("detecto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks. The DB schema is created and the model loaded once here."""
    logger.info("Starting Detecto (model=%s, device=%s)", settings.model_name, settings.device)
    app.state.repository = get_repository()
    logger.info("History database: %s", settings.db_path)
    app.state.detector = get_detector()
    yield
    logger.info("Shutting down Detecto")


app = FastAPI(
    title="Detecto API",
    description="Real-time person detection and counting.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the React/Vite frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each request with its status code and total processing time."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time"] = f"{elapsed_ms:.1f}ms"
    logger.info(
        "%s %s -> %d (%.1f ms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


@app.exception_handler(ImageError)
async def image_error_handler(request: Request, exc: ImageError):
    """Turn invalid-image errors into clean JSON 4xx responses."""
    logger.warning("%s %s rejected: %s", request.method, request.url.path, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error": type(exc).__name__},
    )


app.include_router(detect.router)


@app.get("/health", tags=["system"])
def health(request: Request) -> dict:
    """Liveness check with basic runtime info."""
    detector = getattr(request.app.state, "detector", None)
    return {
        "status": "ok",
        "version": app.version,
        "model": settings.model_name,
        "device": detector.device if detector else settings.device,
        "model_loaded": detector is not None,
    }
