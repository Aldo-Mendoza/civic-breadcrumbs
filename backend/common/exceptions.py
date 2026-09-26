"""
Predictable API errors (CLAUDE.md §27).

Every failure leaves the client with a machine-readable code, a sentence the
citizen can actually read, whether retrying helps, and -- crucially -- a
suggested action, so a dead end always offers a way forward.

Provider error details and stack traces never cross this boundary.
"""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, Throttled
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("civic.errors")


class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    AI_INVALID_OUTPUT = "AI_INVALID_OUTPUT"
    AI_RATE_LIMITED = "AI_RATE_LIMITED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    UNSUPPORTED_ACTION = "UNSUPPORTED_ACTION"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SuggestedAction:
    SAVE_AS_NOTE = "SAVE_AS_NOTE"
    RETRY = "RETRY"
    EDIT_INPUT = "EDIT_INPUT"
    NONE = "NONE"


class ApiError(APIException):
    """An error with a stable contract for the frontend."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = ErrorCode.VALIDATION_ERROR
    recoverable = True
    suggested_action = SuggestedAction.EDIT_INPUT

    def __init__(
        self,
        message=None,
        code=None,
        status_code=None,
        recoverable=None,
        suggested_action=None,
        extra=None,
    ):
        self.detail = message or "Something went wrong."
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        if recoverable is not None:
            self.recoverable = recoverable
        if suggested_action is not None:
            self.suggested_action = suggested_action
        self.extra = extra or {}

    def to_payload(self):
        payload = {
            "code": self.code,
            "message": str(self.detail),
            "recoverable": self.recoverable,
            "suggested_action": self.suggested_action,
        }
        payload.update(self.extra)
        return {"error": payload}


class AIUnavailable(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = ErrorCode.AI_UNAVAILABLE
    recoverable = True
    suggested_action = SuggestedAction.SAVE_AS_NOTE

    def __init__(self, message=None, **kwargs):
        super().__init__(
            message or "I couldn't organize this automatically right now.", **kwargs
        )


class AIInvalidOutput(AIUnavailable):
    code = ErrorCode.AI_INVALID_OUTPUT


class OutOfScope(ApiError):
    status_code = status.HTTP_200_OK
    code = ErrorCode.OUT_OF_SCOPE
    recoverable = True
    suggested_action = SuggestedAction.EDIT_INPUT


def api_exception_handler(exc, context):
    """
    Normalize every exception into the §27 envelope.

    Ownership failures surface as 404 rather than 403 so that object ids cannot
    be enumerated by probing (§29, IDOR protection).
    """
    if isinstance(exc, ApiError):
        return Response(exc.to_payload(), status=exc.status_code)

    if isinstance(exc, Http404):
        return Response(
            ApiError(
                "We couldn't find that.",
                code=ErrorCode.NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
                recoverable=False,
                suggested_action=SuggestedAction.NONE,
            ).to_payload(),
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, Throttled):
        wait = int(exc.wait or 0)
        return Response(
            ApiError(
                "You have made a lot of requests. Please try again in "
                + str(wait)
                + " seconds.",
                code=ErrorCode.AI_RATE_LIMITED,
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                recoverable=True,
                suggested_action=SuggestedAction.RETRY,
                extra={"retry_after_seconds": wait},
            ).to_payload(),
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            ApiError(
                "You do not have access to that.",
                code=ErrorCode.FORBIDDEN,
                status_code=status.HTTP_403_FORBIDDEN,
                recoverable=False,
                suggested_action=SuggestedAction.NONE,
            ).to_payload(),
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, (DRFValidationError, DjangoValidationError)):
        detail = getattr(exc, "detail", None) or getattr(exc, "messages", None)
        return Response(
            ApiError(
                "Some of that information was not valid.",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=status.HTTP_400_BAD_REQUEST,
                extra={"fields": detail},
            ).to_payload(),
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        return Response(
            ApiError(
                "That request could not be completed.",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=response.status_code,
            ).to_payload(),
            status=response.status_code,
        )

    logger.exception("Unhandled exception in %s", context.get("view"))
    return Response(
        ApiError(
            "Something went wrong on our side.",
            code=ErrorCode.INTERNAL_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            recoverable=True,
            suggested_action=SuggestedAction.RETRY,
        ).to_payload(),
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
