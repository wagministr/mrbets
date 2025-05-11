"""
Logger configuration module for MrBets.ai.
"""

import json
import logging
import sys
from datetime import datetime

from app.utils.config import settings


class JsonFormatter(logging.Formatter):
    """Custom formatter to output logs in JSON format."""

    def format(self, record):
        """Format the log record as a JSON string."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "path": record.pathname,
            "line": record.lineno,
            "environment": settings.ENVIRONMENT,
        }

        # Add exception info if exists
        if record.exc_info:
            log_data["exception"] = {
                "type": str(record.exc_info[0].__name__),
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_data)


def setup_logging():
    """Configure the logging system."""
    # Get the root logger
    root_logger = logging.getLogger()

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set the log level from settings
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)

    # Set the formatter based on debug mode
    if settings.APP_DEBUG:
        # Use a more readable format in debug mode
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    else:
        # Use JSON formatter in production
        formatter = JsonFormatter()

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Create app logger
    app_logger = logging.getLogger("mrbets")
    app_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    return app_logger


# Create the application logger
logger = setup_logging()
