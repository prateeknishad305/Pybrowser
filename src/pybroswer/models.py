from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DeviceName = Literal["mobile", "mobile-ios", "mobile-android", "desktop", "desktop-mac"]
LoadState = Literal["load", "domcontentloaded", "networkidle", "commit"]
WaitState = Literal["attached", "detached", "visible", "hidden"]
SelectBy = Literal["value", "label", "index"]


@dataclass(slots=True)
class Viewport:
    width: int
    height: int


@dataclass(slots=True)
class DevicePreset:
    device: str
    user_agent: str
    viewport: Viewport
    is_mobile: bool


@dataclass(slots=True)
class FrameInfo:
    index: int
    name: str
    url: str
    parent_url: str | None
    is_main: bool


@dataclass(slots=True)
class FrameTarget:
    selector: str | None = None
    name: str | None = None
    url: str | None = None
    index: int | None = None

    def to_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if self.selector:
            body["frameSelector"] = self.selector
        if self.name:
            body["frameName"] = self.name
        if self.url:
            body["frameUrl"] = self.url
        if self.index is not None:
            body["frame"] = self.index
        return body


@dataclass(slots=True)
class SessionInfo:
    id: str
    url: str
    title: str
    created_at: str | None = None
    last_used: str | None = None
    viewport: Viewport | None = None
    device: str | None = None
    user_agent: str | None = None
    is_mobile: bool | None = None


@dataclass(slots=True)
class Snapshot:
    id: str
    url: str
    title: str
    ok: bool = True
    session_id: str | None = None
    status: int | None = None
    text: str = ""
    screenshot_base64: str | None = None
    html: str | None = None
    click: str | None = None
    selected: Any = None
    created_at: str | None = None
    last_used: str | None = None
    viewport: Viewport | None = None
    device: str | None = None
    user_agent: str | None = None
    is_mobile: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def screenshot_bytes(self) -> bytes:
        import base64

        if not self.screenshot_base64:
            raise ValueError("snapshot has no screenshot")
        return base64.b64decode(self.screenshot_base64)

    def save_screenshot(self, path: str) -> None:
        from pathlib import Path

        Path(path).write_bytes(self.screenshot_bytes())


@dataclass(slots=True)
class Health:
    ok: bool
    service: str | None = None
    engine: str | None = None
    sessions: int = 0
    max_sessions: int = 0
    error: str | None = None


@dataclass(slots=True)
class InspectResult:
    ok: bool
    selector: str
    tag: str | None = None
    id: str | None = None
    name: str | None = None
    type: str | None = None
    value: Any = None
    text: str = ""
    href: str | None = None
    visible: bool | None = None
    rect: dict[str, Any] | None = None


@dataclass(slots=True)
class LogEntry:
    type: str
    level: str
    text: str
    ts: int | None = None


@dataclass(slots=True)
class UploadFile:
    name: str
    mime_type: str
    data: bytes

    def to_payload(self) -> dict[str, str]:
        import base64

        return {
            "name": self.name,
            "mimeType": self.mime_type,
            "bufferBase64": base64.b64encode(self.data).decode("ascii"),
        }


def viewport_from(data: Any) -> Viewport | None:
    if not isinstance(data, dict):
        return None
    width = data.get("width")
    height = data.get("height")
    if width is None or height is None:
        return None
    return Viewport(width=int(width), height=int(height))


def session_info_from(data: dict[str, Any]) -> SessionInfo:
    return SessionInfo(
        id=str(data.get("id") or data.get("sessionId") or ""),
        url=str(data.get("url") or ""),
        title=str(data.get("title") or ""),
        created_at=data.get("createdAt"),
        last_used=data.get("lastUsed"),
        viewport=viewport_from(data.get("viewport")),
        device=data.get("device"),
        user_agent=data.get("userAgent"),
        is_mobile=data.get("isMobile"),
    )


def snapshot_from(data: dict[str, Any]) -> Snapshot:
    known = {
        "id",
        "url",
        "title",
        "ok",
        "sessionId",
        "status",
        "text",
        "screenshotBase64",
        "html",
        "click",
        "selected",
        "createdAt",
        "lastUsed",
        "viewport",
        "device",
        "userAgent",
        "isMobile",
        "error",
    }
    extra = {k: v for k, v in data.items() if k not in known}
    return Snapshot(
        id=str(data.get("id") or data.get("sessionId") or ""),
        url=str(data.get("url") or ""),
        title=str(data.get("title") or ""),
        ok=bool(data.get("ok", True)),
        session_id=data.get("sessionId") or data.get("id"),
        status=data.get("status"),
        text=str(data.get("text") or ""),
        screenshot_base64=data.get("screenshotBase64"),
        html=data.get("html"),
        click=data.get("click"),
        selected=data.get("selected"),
        created_at=data.get("createdAt"),
        last_used=data.get("lastUsed"),
        viewport=viewport_from(data.get("viewport")),
        device=data.get("device"),
        user_agent=data.get("userAgent"),
        is_mobile=data.get("isMobile"),
        extra=extra,
    )


def frames_from(data: list[dict[str, Any]] | None) -> list[FrameInfo]:
    out: list[FrameInfo] = []
    for item in data or []:
        out.append(
            FrameInfo(
                index=int(item.get("index", 0)),
                name=str(item.get("name") or ""),
                url=str(item.get("url") or ""),
                parent_url=item.get("parentUrl"),
                is_main=bool(item.get("isMain")),
            )
        )
    return out


def presets_from(data: list[dict[str, Any]] | None) -> list[DevicePreset]:
    out: list[DevicePreset] = []
    for item in data or []:
        vp = viewport_from(item.get("viewport")) or Viewport(0, 0)
        out.append(
            DevicePreset(
                device=str(item.get("device") or ""),
                user_agent=str(item.get("userAgent") or ""),
                viewport=vp,
                is_mobile=bool(item.get("isMobile")),
            )
        )
    return out
