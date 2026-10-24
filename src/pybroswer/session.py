from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pybroswer._http import Transport
from pybroswer.models import (
    FrameInfo,
    FrameTarget,
    InspectResult,
    LoadState,
    LogEntry,
    SelectBy,
    SessionInfo,
    Snapshot,
    UploadFile,
    WaitState,
    frames_from,
    session_info_from,
    snapshot_from,
)


class Session:
    def __init__(self, transport: Transport, session_id: str) -> None:
        self._http: Transport = transport
        self.id = session_id

    def _path(self, suffix: str = "") -> str:
        return f"/api/v1/sessions/{self.id}{suffix}"

    def _frame_body(self, frame: FrameTarget | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if frame:
            body.update(frame.to_body())
        if extra:
            body.update({k: v for k, v in extra.items() if v is not None})
        return body

    def info(self) -> SessionInfo:
        return session_info_from(self._http.request("GET", self._path()))

    def close(self) -> bool:
        data = self._http.request("DELETE", self._path())
        return bool(data.get("ok", True))

    def goto(self, url: str) -> Snapshot:
        return snapshot_from(self._http.request("POST", self._path("/goto"), json={"url": url}))

    def back(self) -> Snapshot:
        return snapshot_from(self._http.request("POST", self._path("/back")))

    def reload(self) -> Snapshot:
        return snapshot_from(self._http.request("POST", self._path("/reload")))

    def wait_for_selector(
        self,
        selector: str,
        *,
        timeout: int | None = None,
        state: WaitState = "visible",
        frame: FrameTarget | None = None,
    ) -> dict[str, Any]:
        body = self._frame_body(frame, {"selector": selector, "timeout": timeout, "state": state})
        return self._http.request("POST", self._path("/wait-for-selector"), json=body)

    def click(
        self,
        selector: str | None = None,
        *,
        x: float | None = None,
        y: float | None = None,
        timeout: int | None = None,
        state: WaitState | None = None,
        screenshot: bool = True,
        settle_ms: int | None = None,
        frame: FrameTarget | None = None,
    ) -> Snapshot:
        body = self._frame_body(
            frame,
            {
                "selector": selector,
                "x": x,
                "y": y,
                "timeout": timeout,
                "state": state,
                "screenshot": screenshot,
                "settleMs": settle_ms,
            },
        )
        return snapshot_from(self._http.request("POST", self._path("/click"), json=body))

    def type(
        self,
        text: str,
        selector: str | None = None,
        *,
        timeout: int | None = None,
        state: WaitState | None = None,
        screenshot: bool = True,
        frame: FrameTarget | None = None,
    ) -> Snapshot:
        body = self._frame_body(
            frame,
            {
                "selector": selector,
                "text": text,
                "timeout": timeout,
                "state": state,
                "screenshot": screenshot,
            },
        )
        return snapshot_from(self._http.request("POST", self._path("/type"), json=body))

    def press(
        self,
        key: str,
        selector: str | None = None,
        *,
        timeout: int | None = None,
        state: WaitState | None = None,
        screenshot: bool = True,
        frame: FrameTarget | None = None,
    ) -> Snapshot:
        body = self._frame_body(
            frame,
            {
                "key": key,
                "selector": selector,
                "timeout": timeout,
                "state": state,
                "screenshot": screenshot,
            },
        )
        return snapshot_from(self._http.request("POST", self._path("/press"), json=body))

    def select(
        self,
        selector: str,
        *,
        value: str | list[str] | None = None,
        label: str | None = None,
        index: int | None = None,
        by: SelectBy | None = None,
        timeout: int | None = None,
        screenshot: bool = True,
        frame: FrameTarget | None = None,
    ) -> Snapshot:
        payload: dict[str, Any] = {
            "selector": selector,
            "timeout": timeout,
            "screenshot": screenshot,
        }
        if by == "label" or (label is not None and value is None and index is None):
            payload["label"] = label
        elif by == "index" or (index is not None and value is None and label is None):
            payload["index"] = index
        else:
            payload["value"] = value
        body = self._frame_body(frame, payload)
        return snapshot_from(self._http.request("POST", self._path("/select"), json=body))

    def scroll(
        self,
        *,
        dy: int = 400,
        dx: int = 0,
        selector: str | None = None,
        timeout: int | None = None,
        screenshot: bool = True,
        frame: FrameTarget | None = None,
    ) -> Snapshot:
        body = self._frame_body(
            frame,
            {"dy": dy, "dx": dx, "selector": selector, "timeout": timeout, "screenshot": screenshot},
        )
        return snapshot_from(self._http.request("POST", self._path("/scroll"), json=body))

    def wait_for_load(self, state: LoadState = "networkidle", *, timeout: int | None = None) -> Snapshot:
        return snapshot_from(
            self._http.request("POST", self._path("/wait-for-load"), json={"state": state, "timeout": timeout})
        )

    def evaluate(self, script: str, *, frame: FrameTarget | None = None) -> Any:
        body = self._frame_body(frame, {"script": script})
        data = self._http.request("POST", self._path("/evaluate"), json=body)
        return data.get("result")

    def inspect(self, selector: str, *, timeout: int | None = None, frame: FrameTarget | None = None) -> InspectResult:
        body = self._frame_body(frame, {"selector": selector, "timeout": timeout})
        data = self._http.request("POST", self._path("/inspect"), json=body)
        return InspectResult(
            ok=bool(data.get("ok", True)),
            selector=str(data.get("selector") or selector),
            tag=data.get("tag"),
            id=data.get("id"),
            name=data.get("name"),
            type=data.get("type"),
            value=data.get("value"),
            text=str(data.get("text") or ""),
            href=data.get("href"),
            visible=data.get("visible"),
            rect=data.get("rect"),
        )

    def frames(self) -> list[FrameInfo]:
        data = self._http.request("GET", self._path("/frames"))
        return frames_from(data.get("frames"))

    def html(self, *, frame: FrameTarget | None = None) -> str:
        params = frame.to_body() if frame else None
        data = self._http.request("GET", self._path("/html"), params=params)
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data.get("html") or "")

    def page(self) -> Snapshot:
        return snapshot_from(self._http.request("GET", self._path("/page")))

    def screenshot(self, *, full_page: bool = False) -> bytes:
        params = {"fullPage": "true"} if full_page else None
        data = self._http.request("GET", self._path("/screenshot"), params=params, expect_json=False)
        return data if isinstance(data, bytes) else bytes(data)

    def screenshot_b64(self, *, full_page: bool = False) -> str:
        params: dict[str, Any] = {"format": "json"}
        if full_page:
            params["fullPage"] = "true"
        data = self._http.request("GET", self._path("/screenshot"), params=params)
        return str(data.get("screenshotBase64") or "")

    def save_screenshot(self, path: str | Path, *, full_page: bool = False) -> Path:
        dest = Path(path)
        dest.write_bytes(self.screenshot(full_page=full_page))
        return dest

    def logs(self) -> list[LogEntry]:
        data = self._http.request("GET", self._path("/logs"))
        out: list[LogEntry] = []
        for item in data.get("logs") or []:
            out.append(
                LogEntry(
                    type=str(item.get("type") or ""),
                    level=str(item.get("level") or ""),
                    text=str(item.get("text") or ""),
                    ts=item.get("ts"),
                )
            )
        return out

    def upload(
        self,
        selector: str,
        files: Iterable[UploadFile | tuple[str, str, bytes] | Path],
        *,
        timeout: int | None = None,
        screenshot: bool = True,
        frame: FrameTarget | None = None,
    ) -> Snapshot:
        payloads: list[dict[str, str]] = []
        for item in files:
            if isinstance(item, UploadFile):
                payloads.append(item.to_payload())
            elif isinstance(item, Path):
                payloads.append(
                    UploadFile(name=item.name, mime_type="application/octet-stream", data=item.read_bytes()).to_payload()
                )
            else:
                name, mime, data = item
                payloads.append(UploadFile(name=name, mime_type=mime, data=data).to_payload())
        body = self._frame_body(
            frame, {"selector": selector, "files": payloads, "timeout": timeout, "screenshot": screenshot}
        )
        return snapshot_from(self._http.request("POST", self._path("/upload"), json=body))

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
