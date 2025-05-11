"""
Custom exceptions for MrBets.ai API.
"""

from fastapi import HTTPException, status


class APIException(HTTPException):
    """Base API exception with status code and detail message."""

    def __init__(self, status_code: int, detail: str, headers: dict = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class NotFoundException(APIException):
    """Exception raised when a requested resource is not found."""

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class BadRequestException(APIException):
    """Exception raised when the request is invalid."""

    def __init__(self, detail: str = "Invalid request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class UnauthorizedException(APIException):
    """Exception raised when authentication is required but not provided."""

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenException(APIException):
    """Exception raised when the user doesn't have permission to access a resource."""

    def __init__(self, detail: str = "Access forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class ServiceUnavailableException(APIException):
    """Exception raised when a required external service is unavailable."""

    def __init__(self, service: str, detail: str = None):
        message = f"Service unavailable: {service}"
        if detail:
            message += f" - {detail}"
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=message)
