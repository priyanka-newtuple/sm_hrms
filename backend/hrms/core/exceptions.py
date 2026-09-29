from fastapi import HTTPException, status


class NotAuthenticated(HTTPException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class PermissionDenied(HTTPException):
    def __init__(self, detail: str = "You do not have permission to perform this action"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFound(HTTPException):
    def __init__(self, detail: str = "Not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class Conflict(HTTPException):
    """
    The request is well-formed and permitted, but conflicts with current state —
    archiving a customer that still has open projects, or double-booking an
    employee onto the same project twice. `context` carries the offending records
    so the UI can show the user exactly what to resolve.
    """

    def __init__(self, detail: str = "Conflict", context: dict | None = None):
        payload: dict = {"message": detail}
        if context:
            payload.update(context)
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=payload)


class ValidationFailed(HTTPException):
    """A business-rule violation (as opposed to a schema/type error, which FastAPI
    raises on its own)."""

    def __init__(self, detail: str, context: dict | None = None):
        payload: dict = {"message": detail}
        if context:
            payload.update(context)
        # Literal 422 — Starlette renamed the constant and deprecated the old name.
        super().__init__(status_code=422, detail=payload)
