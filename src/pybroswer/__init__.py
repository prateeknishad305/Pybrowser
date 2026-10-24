"""Python browser for PyDroid. HTTP engine in-app; optional remote Chromium."""

from pybroswer.client import Browser
from pybroswer.exceptions import ActionFailed, ApiError, EngineError, PyBroswerError, SessionNotFound
from pybroswer.models import (
    DevicePreset,
    FrameInfo,
    FrameTarget,
    Health,
    InspectResult,
    LogEntry,
    SessionInfo,
    Snapshot,
    UploadFile,
    Viewport,
)
from pybroswer.session import Session

__all__ = [
    "ActionFailed",
    "ApiError",
    "Browser",
    "DevicePreset",
    "EngineError",
    "FrameInfo",
    "FrameTarget",
    "Health",
    "InspectResult",
    "LogEntry",
    "PyBroswerError",
    "Session",
    "SessionInfo",
    "SessionNotFound",
    "Snapshot",
    "UploadFile",
    "Viewport",
    "__version__",
]

__version__ = "0.3.1"
