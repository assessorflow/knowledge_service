"""Knowledge Service — FastAPI + gRPC application entry point.

Port 8030 (REST)  — Postman testing + admin/policies endpoint
Port 9030 (gRPC)  — 7 internal endpoints for agent-to-service communication

Owns af_knowledge database (topics, document_chunks, policy_chunks, enriched_chunks).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
import structlog

from knowledge_service import config
from knowledge_service.db.pool import get_pool, close_pool
from knowledge_service.routes.internal import router as internal_router
from knowledge_service.grpc.server import start_grpc_server, stop_grpc_server, GRPC_PORT

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
)

logger = structlog.get_logger(__name__)

_grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _grpc_server
    # Startup
    logger.info("knowledge_service_starting", rest_port=config.SERVICE_PORT, grpc_port=GRPC_PORT)
    await get_pool()
    _grpc_server = await start_grpc_server()
    logger.info("knowledge_service_ready", rest_port=config.SERVICE_PORT, grpc_port=GRPC_PORT)
    yield
    # Shutdown
    if _grpc_server:
        await stop_grpc_server(_grpc_server)
    await close_pool()
    logger.info("knowledge_service_stopped")


app = FastAPI(
    title="AssessorFlow Knowledge Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(internal_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "knowledge-service", "grpc_port": GRPC_PORT}


@app.get("/ready")
async def ready():
    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        return {"status": "ready", "database": "connected", "grpc_port": GRPC_PORT}
    except Exception as exc:
        return {"status": "not_ready", "error": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "knowledge_service.main:app",
        host="0.0.0.0",
        port=config.SERVICE_PORT,
        reload=True,
    )
