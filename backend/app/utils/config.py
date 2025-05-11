"""
Configuration module for loading and validating environment variables.
"""

import logging
import os

from pydantic import BaseModel, Field

logger = logging.getLogger("mrbets.config")


class Settings(BaseModel):
    """Application settings loaded from environment variables with defaults."""

    # Application Settings
    APP_NAME: str = "MrBets.ai API"
    APP_VERSION: str = "1.0.0"
    APP_DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")

    # API Keys will be added when needed
    # API_FOOTBALL_KEY: str
    # OPENAI_API_KEY: str

    # Database connections will be added when needed
    # SUPABASE_URL: str
    # SUPABASE_KEY: str
    # REDIS_URL: str

    # Other settings
    LOG_LEVEL: str = Field(default="INFO")


# Create global settings object
settings = Settings(
    APP_DEBUG=os.getenv("APP_DEBUG", "False").lower() in ("true", "1", "t"),
    ENVIRONMENT=os.getenv("ENVIRONMENT", "development"),
    LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
)


def get_settings() -> Settings:
    """Return the global settings object."""
    return settings


def verify_env_variables():
    """
    Verify that all required environment variables are set.
    This will be expanded as we add actual service connections.
    """
    # List of variables that will be required for operation
    # required_vars = ["API_FOOTBALL_KEY", "OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"]
    required_vars = []

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        logger.warning(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False

    return True
