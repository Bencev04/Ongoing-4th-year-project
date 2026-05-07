"""
Common exception classes for microservices.

Provides standardized exceptions that can be caught and
converted to appropriate HTTP responses.
"""

from typing import Any


class BaseServiceException(Exception):
    """
    Base exception for all service errors.

    Attributes:
        message: Human-readable error message
        code: Machine-readable error code
        status_code: HTTP status code
        details: Additional error details
    """

    def __init__(
        self,
        message: str,
        code: str = "SERVICE_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(BaseServiceException):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: str | None = None,
        resource_id: Any | None = None,
    ) -> None:
        details = {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id
        super().__init__(
            message=message, code="NOT_FOUND", status_code=404, details=details
        )


class ValidationError(BaseServiceException):
    """Raised when input validation fails."""

    def __init__(
        self, message: str = "Validation failed", errors: dict[str, str] | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details={"errors": errors or {}},
        )


class UnauthorizedError(BaseServiceException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message=message, code="UNAUTHORIZED", status_code=401)


class ForbiddenError(BaseServiceException):
    """Raised when user lacks permission for an action."""

    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message=message, code="FORBIDDEN", status_code=403)


class ConflictError(BaseServiceException):
    """Raised when there's a data conflict (e.g., duplicate)."""

    def __init__(
        self, message: str = "Resource conflict", field: str | None = None
    ) -> None:
        details = {"field": field} if field else {}
        super().__init__(
            message=message, code="CONFLICT", status_code=409, details=details
        )


class DatabaseError(BaseServiceException):
    """Raised when a database operation fails."""

    def __init__(self, message: str = "Database error") -> None:
        super().__init__(message=message, code="DATABASE_ERROR", status_code=500)
