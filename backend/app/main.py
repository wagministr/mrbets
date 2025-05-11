"""
MrBets.ai FastAPI Backend - Main Application Entry Point
"""

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables before imports that might use them
load_dotenv()

# Now import app modules that require environment variables
from app.models.common import HealthResponse, ReadinessResponse
from app.routers import fixtures, predictions
from app.utils.config import settings, verify_env_variables
from app.utils.logger import logger

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for MrBets.ai football prediction platform",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    debug=settings.APP_DEBUG,
)

# Log that app is initialized
logger.info("Environment variables loaded")

# Configure CORS - allow frontend to communicate with backend
frontend_urls = [
    "http://localhost:3000",  # Local development
    "http://localhost:8080",  # Docker development
    "https://mrbets.ai",  # Production
    "https://www.mrbets.ai",  # Production with www
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_urls,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    max_age=86400,  # 24 hours cache for preflight requests
)


# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint to verify API is running.
    Returns current API version and status.
    """
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


# Readiness check - validates essential connections
@app.get("/ready", response_model=ReadinessResponse)
async def ready_check():
    """
    Readiness check to verify that the application can serve requests.
    Validates connections to required services.
    """
    status = {
        "database": False,
        "redis": False,
    }

    # Simple placeholder - will be implemented when DB & Redis connections are added
    # This helps Kubernetes or other orchestrators know when the app is ready
    status["database"] = True
    status["redis"] = True

    is_ready = all(status.values())
    return {"ready": is_ready, "services": status}


# Register routers
app.include_router(fixtures.router, prefix="/fixtures", tags=["fixtures"])
app.include_router(predictions.router, prefix="/predictions", tags=["predictions"])


# Startup event
@app.on_event("startup")
async def startup_event():
    """
    Executes when the FastAPI application starts.
    Initialize connections and validate configuration.
    """
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    if settings.APP_DEBUG:
        logger.warning("Running in DEBUG mode - not recommended for production")

    # Verify environment variables
    if not verify_env_variables():
        logger.warning(
            "Some required environment variables are missing. "
            "Some features may not work correctly."
        )

    # This is a placeholder, will add actual connection initialization when needed


@app.on_event("shutdown")
async def shutdown_event():
    """
    Executes when the FastAPI application shuts down.
    Close connections and perform cleanup.
    """
    logger.info(f"Shutting down {settings.APP_NAME}")
    # Close connections - will be implemented when connections are added


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.APP_DEBUG)
