"""OpsCentral - Unified SOC Dashboard API.

FastAPI application entry point providing REST API for security alerts,
infrastructure metrics, compliance scoring, and cost tracking.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from src.opscentral.config import get_settings
from src.opscentral.api.routes import alerts, compliance, cost, infrastructure
from src.opscentral.models.database import init_db, close_db

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Set log level
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    # Startup
    logger.info("Starting OpsCentral API", version=settings.app_version)
    await init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down OpsCentral API")
    await close_db()


# Initialize FastAPI application
app = FastAPI(
    title="OpsCentral API",
    description="Unified SOC Dashboard - Security alerts and infrastructure metrics aggregation",
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Grafana
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Prometheus metrics instrumentation
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler for unhandled errors."""
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Health check endpoint
@app.get("/api/v1/health", tags=["System"])
async def health_check() -> dict:
    """Service health check endpoint.

    Returns:
        Health status with component checks
    """
    from src.opscentral.models.database import check_db_connection

    db_healthy = await check_db_connection()

    return {
        "status": "healthy" if db_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.app_version,
        "components": {
            "database": "healthy" if db_healthy else "unhealthy",
            "api": "healthy",
        },
    }


# Include API routers
app.include_router(
    alerts.router,
    prefix="/api/v1/alerts",
    tags=["Alerts"],
)
app.include_router(
    infrastructure.router,
    prefix="/api/v1/infrastructure",
    tags=["Infrastructure"],
)
app.include_router(
    compliance.router,
    prefix="/api/v1/compliance",
    tags=["Compliance"],
)
app.include_router(
    cost.router,
    prefix="/api/v1/cost",
    tags=["Cost"],
)


# Root endpoint
@app.get("/", tags=["System"])
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs" if settings.debug else "disabled",
        "health": "/api/v1/health",
    }
