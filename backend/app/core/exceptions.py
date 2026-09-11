"""Application exception types with consistent HTTP status codes."""

from typing import Any, Dict, Optional

from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base class so every raised error carries a stable error_code."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "app_error"
    default_detail = "Something went wrong."

    def __init__(
        self,
        detail: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(
            status_code=self.status_code,
            detail=detail or self.default_detail,
            headers=headers,
        )


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"
    default_detail = "Resource not found."


class DuplicateError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "duplicate"
    default_detail = "Resource already exists."


class ValidationError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"
    default_detail = "The submitted data is not valid."


class AuthenticationError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_failed"
    default_detail = "Could not validate credentials."

    def __init__(self, detail: Optional[str] = None) -> None:
        super().__init__(detail, headers={"WWW-Authenticate": "Bearer"})


class PermissionDeniedError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "permission_denied"
    default_detail = "You do not have permission to perform this action."


class AccountLockedError(AppException):
    status_code = status.HTTP_423_LOCKED
    error_code = "account_locked"
    default_detail = "This account is temporarily locked."


class BusinessRuleError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "business_rule_violation"
    default_detail = "This action violates a business rule."
