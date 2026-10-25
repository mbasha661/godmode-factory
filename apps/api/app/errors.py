"""Consistent error responses + error categories from spec section 13."""
from enum import Enum
from fastapi import HTTPException


class ErrorCategory(str, Enum):
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    QUOTA_EXHAUSTED = "quota_exhausted"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    AUTH_FAILURE = "auth_failure"
    DATABASE_FAILURE = "database_failure"
    CODE_EXECUTION_FAILURE = "code_execution_failure"
    TEST_FAILURE = "test_failure"
    BUILD_FAILURE = "build_failure"
    ARTIFACT_STORAGE_FAILURE = "artifact_storage_failure"
    DEPLOYMENT_FAILURE = "deployment_failure"


def api_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def not_found(what: str = "resource") -> HTTPException:
    return api_error(404, "not_found", f"{what} not found")


def forbidden(msg: str = "not allowed") -> HTTPException:
    return api_error(403, "forbidden", msg)


def unauthorized(msg: str = "authentication required") -> HTTPException:
    return api_error(401, "unauthorized", msg)


def conflict(msg: str) -> HTTPException:
    return api_error(409, "conflict", msg)


def bad_request(msg: str) -> HTTPException:
    return api_error(400, "bad_request", msg)
