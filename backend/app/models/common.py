"""
Common data models shared across the application.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Error response model returned when an API request fails."""

    status: str = "error"
    message: str
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Response model for readiness check endpoint."""

    ready: bool
    services: Dict[str, bool]


class SuccessResponse(BaseModel):
    """Generic success response."""

    status: str = "success"
    message: str
    data: Optional[Dict[str, Any]] = None
