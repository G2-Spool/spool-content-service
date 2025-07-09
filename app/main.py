"""Main FastAPI application for Content Service."""

import os
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.dependencies import get_neo4j_client, get_pinecone_client
from app.routers import content, graph, hooks, processing

# Setup structured logging
setup_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup
    logger.info("Starting Spool Content Service", version=settings.APP_VERSION)
    
    # Initialize clients
    neo4j_client = await get_neo4j_client()
    pinecone_client = await get_pinecone_client()
    
    # Store in app state
    app.state.neo4j = neo4j_client
    app.state.pinecone = pinecone_client
    
    # Setup Prometheus metrics
    if settings.ENABLE_METRICS:
        instrumentator = Instrumentator()
        instrumentator.instrument(app).expose(app, endpoint="/metrics")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Spool Content Service")
    
    # Close connections
    if hasattr(app.state, "neo4j") and app.state.neo4j:
        await app.state.neo4j.close()


# Create FastAPI app
app = FastAPI(
    title="Spool Content Service",
    description="Content processing, vector generation, and knowledge graph management",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(content.router, prefix="/api/content", tags=["content"])
app.include_router(processing.router, prefix="/api/content", tags=["processing"])
app.include_router(graph.router, prefix="/api/content/graph", tags=["graph"])
app.include_router(hooks.router, prefix="/api/content/hooks", tags=["hooks"])


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "service": "Spool Content Service",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "operational"
    }


@app.get("/health", tags=["health"])
async def health_check(request: Request):
    """Health check endpoint."""
    health_status = {
        "status": "healthy",
        "service": "content-service",
        "version": settings.APP_VERSION,
        "checks": {}
    }
    
    # Check Neo4j
    try:
        if hasattr(request.app.state, "neo4j") and request.app.state.neo4j:
            await request.app.state.neo4j.verify_connectivity()
            health_status["checks"]["neo4j"] = "healthy"
    except Exception as e:
        health_status["checks"]["neo4j"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Pinecone
    try:
        if hasattr(request.app.state, "pinecone") and request.app.state.pinecone:
            # Simple health check - list indexes
            request.app.state.pinecone.list_indexes()
            health_status["checks"]["pinecone"] = "healthy"
    except Exception as e:
        health_status["checks"]["pinecone"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    status_code = 200 if health_status["status"] == "healthy" else 503
    return JSONResponse(content=health_status, status_code=status_code)


@app.get("/config", tags=["debug"])
async def get_config():
    """Get current configuration (development only)."""
    if settings.ENVIRONMENT == "production":
        return JSONResponse(
            content={"error": "Not available in production"},
            status_code=403
        )
    
    return {
        "environment": settings.ENVIRONMENT,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
        "pinecone_index": settings.PINECONE_INDEX_NAME,
        "neo4j_database": settings.NEO4J_DATABASE,
        "s3_bucket": settings.S3_BUCKET,
        "max_pdf_size_mb": settings.MAX_PDF_SIZE_MB,
        "chunk_size": settings.CHUNK_SIZE
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.SERVICE_PORT,
        reload=settings.ENVIRONMENT == "development",
        log_config=None  # Use structlog instead
    )