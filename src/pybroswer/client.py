from __future__ import annotations

from typing import Any

from pybroswer._http import HttpTransport, Transport
from pybroswer.models import (
    DeviceName,
    DevicePreset,
    Health,
    SessionInfo,
    Snapshot,
    presets_from,
    session_info_from,
    snapshot_from,
)
from pybroswer.session import Session


class Browser:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 60.0,
        headers: dict[str, str] | None = None,
        transport: Transport | None = None,
        engine: Any | None = None,
    ) -> None:
        if transport is not None:
            self._http: Transport = transport
        elif engine is not None:
            from pybroswer.engine import EngineTransport

            self._http = EngineTransport(engine, owns=False)
        elif base_url:
            self._http = HttpTransport(base_url, timeout=timeout, headers=headers)
        else:
            self._http = _http_engine_transport(max_sessions=5, idle_ms=10 * 60 * 1000, timeout=timeout)

    @classmethod
    def launch(
        cls,
        *,
        engine: str = "http",
        headless: bool = True,
        max_sessions: int = 5,
        idle_ms: int = 10 * 60 * 1000,
        timeout: float = 30.0,
        executable_path: str | None = None,
        channel: str | None = None,
    ) -> Browser:
        from pybroswer.engine import EngineTransport

        if engine in {"chromium", "playwright"}:
            from pybroswer.engine import ChromiumEngine

            chromium = ChromiumEngine(
                headless=headless,
                max_sessions=max_sessions,
                idle_ms=idle_ms,
                executable_path=executable_path,
                channel=channel,
            )
            chromium.start()
            return cls(transport=EngineTransport(chromium, owns=True))
        return cls(transport=_http_engine_transport(max_sessions=max_sessions, idle_ms=idle_ms, timeout=timeout))

    @classmethod
    def connect(
        cls,
        url: str = "http://127.0.0.1:5173",
        *,
        timeout: float = 60.0,
        headers: dict[str, str] | None = None,
    ) -> Browser:
        return cls(url, timeout=timeout, headers=headers)

    def close(self) -> None:
        self._http.close()

    def health(self) -> Health:
        data = self._http.request("GET", "/api/v1/health")
        return Health(
            ok=bool(data.get("ok")),
            service=data.get("service"),
            engine=data.get("engine"),
            sessions=int(data.get("sessions") or 0),
            max_sessions=int(data.get("maxSessions") or 0),
            error=data.get("error"),
        )

    def ua_presets(self) -> list[DevicePreset]:
        data = self._http.request("GET", "/api/v1/ua")
        return presets_from(data.get("presets"))

    def sessions(self) -> list[SessionInfo]:
        data = self._http.request("GET", "/api/v1/sessions")
        return [session_info_from(item) for item in data.get("sessions") or []]

    def create_session(
        self,
        *,
        device: DeviceName | str = "mobile",
        url: str | None = None,
        user_agent: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Session:
        body: dict[str, Any] = {"device": device}
        if url:
            body["url"] = url
        if user_agent:
            body["userAgent"] = user_agent
        if width is not None:
            body["width"] = width
        if height is not None:
            body["height"] = height
        data = self._http.request("POST", "/api/v1/sessions", json=body)
        return Session(self._http, str(data["id"]))

    def session(self, session_id: str) -> Session:
        return Session(self._http, session_id)

    def browse(
        self,
        url: str,
        *,
        device: DeviceName | str = "desktop",
        user_agent: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Snapshot:
        body: dict[str, Any] = {"url": url, "device": device}
        if user_agent:
            body["userAgent"] = user_agent
        if width is not None:
            body["width"] = width
        if height is not None:
            body["height"] = height
        return snapshot_from(self._http.request("POST", "/api/v1/browse", json=body))

    def __enter__(self) -> Browser:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _http_engine_transport(*, max_sessions: int, idle_ms: int, timeout: float) -> Any:
    from pybroswer.engine import EngineTransport
    from pybroswer.http_engine import HttpEngine

    engine = HttpEngine(max_sessions=max_sessions, idle_ms=idle_ms, timeout=timeout)
    engine.start()
    return EngineTransport(engine, owns=True)
