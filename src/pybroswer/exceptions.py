class PyBroswerError(Exception):
    """Base error for pybroswer."""


class ApiError(PyBroswerError):
    def __init__(self, message: str, *, status_code: int | None = None, payload: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class SessionNotFound(ApiError):
    pass


class ActionFailed(ApiError):
    pass


class EngineError(PyBroswerError):
    pass
