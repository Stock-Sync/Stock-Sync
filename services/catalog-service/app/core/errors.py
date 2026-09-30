from typing import Any


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


class NotFoundError(APIError):
    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(status_code=404, code="not_found", message=f"{resource} not found")


class ConflictError(APIError):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(status_code=409, code="conflict", message=message)


class BadRequestError(APIError):
    def __init__(self, message: str = "Bad request", details: Any | None = None) -> None:
        super().__init__(status_code=400, code="bad_request", message=message, details=details)
