"""Domain error types. The API layer maps each class to one HTTP status and one response shape.

- RuleViolation      -> 422  the request is well-formed but breaks a business rule
- NotFound           -> 404  a referenced product / location / movement does not exist
- Conflict (+ subs)  -> 409  the request is valid but clashes with current state
"""

from typing import Any


class DomainError(Exception):
    http_status = 400
    code = "DOMAIN_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.field = field
        self.details = details or {}


class RuleViolation(DomainError):
    http_status = 422
    code = "RULE_VIOLATION"


class NotFound(DomainError):
    http_status = 404
    code = "NOT_FOUND"


class Conflict(DomainError):
    http_status = 409
    code = "CONFLICT"


class DuplicateResource(Conflict):
    code = "DUPLICATE"


class InsufficientStock(Conflict):
    code = "INSUFFICIENT_STOCK"


class AlreadyReversed(Conflict):
    code = "ALREADY_REVERSED"


class CannotReverseReversal(Conflict):
    code = "CANNOT_REVERSE_A_REVERSAL"
