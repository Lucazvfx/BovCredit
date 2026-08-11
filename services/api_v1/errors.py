from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from flask import jsonify
from flask_limiter.errors import RateLimitExceeded


logger = logging.getLogger(__name__)


@dataclass
class APIError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: object | None = None

    def payload(self) -> dict:
        body = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details not in (None, {}, []):
            body["error"]["details"] = self.details
        return body


class MalformedRequestError(APIError):
    def __init__(self, message: str, details: object | None = None):
        super().__init__("malformed_request", message, 400, details)


class ValidationError(APIError):
    def __init__(self, message: str, details: object | None = None):
        super().__init__("validation_error", message, 400, details)


class MissingAPIKeyError(APIError):
    def __init__(self, message: str = "API key is required."):
        super().__init__("missing_api_key", message, 401)


class MalformedAPIKeyError(APIError):
    def __init__(self, message: str = "API key format is invalid."):
        super().__init__("malformed_api_key", message, 401)


class InvalidAPIKeyError(APIError):
    def __init__(self, message: str = "API key is invalid."):
        super().__init__("invalid_api_key", message, 401)


class RevokedAPIKeyError(APIError):
    def __init__(self, message: str = "API key has been revoked."):
        super().__init__("revoked_api_key", message, 401)


class ForbiddenOrganizationError(APIError):
    def __init__(self, message: str = "API key cannot access this organization."):
        super().__init__("forbidden_organization", message, 403)


class InsufficientScopeError(APIError):
    def __init__(self, message: str = "API key scope is insufficient.", details: object | None = None):
        super().__init__("insufficient_scope", message, 403, details)


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found.", *, code: str = "not_found", details: object | None = None):
        super().__init__(code, message, 404, details)


class ConflictError(APIError):
    def __init__(self, message: str = "Request conflicts with existing idempotency state.", details: object | None = None):
        super().__init__("idempotency_conflict", message, 409, details)


def error_response(error: APIError | Exception, *, trace_id: str | None = None):
    trace_id = trace_id or uuid.uuid4().hex[:8]
    if isinstance(error, APIError):
        body = error.payload()
        body["trace_id"] = trace_id
        return jsonify(body), error.status_code
    logger.exception("[%s] unhandled API v1 exception", trace_id)
    return jsonify({
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
        },
        "trace_id": trace_id,
    }), 500


def register_error_handlers(bp) -> None:
    @bp.errorhandler(APIError)
    def _api_error(error):
        return error_response(error)

    @bp.errorhandler(RateLimitExceeded)
    def _rate_limited(error):
        return error_response(APIError("rate_limited", "Too many requests. Please retry later.", 429))

    @bp.errorhandler(Exception)
    def _unexpected(error):
        return error_response(error)
