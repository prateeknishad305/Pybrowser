from __future__ import annotations

import base64

import httpx
import pytest

from pybroswer import ActionFailed, Browser, FrameTarget, SessionNotFound, UploadFile, __version__


def test_version():
    assert __version__
    import pybrowser

    assert pybrowser.Browser is Browser


def test_connect_alias():
    b = Browser.connect("http://192.168.1.10:5173")
    assert b._http.base_url == "http://192.168.1.10:5173"
    b.close()


def test_no_arg_browser_is_local_http():
    b = Browser()
    try:
        assert b.health().engine == "http"
    finally:
        b.close()


def _mount(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://test")
    from pybroswer._http import HttpTransport

    return Browser(transport=HttpTransport("http://test", client=client))


def test_health_and_browse():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/health":
            return httpx.Response(
                200,
                json={"ok": True, "service": "remote-playwright", "engine": "chromium", "sessions": 1, "maxSessions": 5},
            )
        if request.url.path == "/api/v1/browse":
            body = request.read()
            assert b"example.com" in body
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "sessionId": "abc",
                    "id": "abc",
                    "title": "Example",
                    "url": "https://example.com/",
                    "status": 200,
                    "text": "hello",
                    "screenshotBase64": base64.b64encode(b"png").decode(),
                },
            )
        raise AssertionError(request.url.path)

    browser = _mount(handler)
    health = browser.health()
    assert health.ok and health.engine == "chromium"
    shot = browser.browse("https://example.com", device="desktop")
    assert shot.title == "Example"
    assert shot.screenshot_bytes() == b"png"


def test_session_actions():
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        path = request.url.path
        if request.method == "POST" and path == "/api/v1/sessions":
            return httpx.Response(201, json={"id": "s1", "url": "about:blank", "title": "", "device": "mobile"})
        if path == "/api/v1/sessions/s1/goto":
            return httpx.Response(200, json={"ok": True, "id": "s1", "url": "https://example.com/", "title": "Example"})
        if path == "/api/v1/sessions/s1/click":
            return httpx.Response(
                200, json={"ok": True, "id": "s1", "url": "https://example.com/", "title": "Example", "click": "click"}
            )
        if path == "/api/v1/sessions/s1/type":
            return httpx.Response(200, json={"ok": True, "id": "s1", "url": "https://example.com/", "title": "Example"})
        if path == "/api/v1/sessions/s1/evaluate":
            return httpx.Response(200, json={"ok": True, "result": "Example Domain"})
        if path == "/api/v1/sessions/s1/frames":
            return httpx.Response(
                200,
                json={"frames": [{"index": 0, "name": "", "url": "https://example.com/", "parentUrl": None, "isMain": True}]},
            )
        if path == "/api/v1/sessions/s1":
            return httpx.Response(200, json={"ok": True})
        raise AssertionError(path)

    browser = _mount(handler)
    with browser.create_session(device="mobile") as page:
        assert page.id == "s1"
        shot = page.goto("https://example.com")
        assert shot.title == "Example"
        clicked = page.click("a")
        assert clicked.click == "click"
        page.type("hi", selector="input")
        assert page.evaluate("document.title") == "Example Domain"
        frames = page.frames()
        assert frames[0].is_main
    assert ("DELETE", "/api/v1/sessions/s1") in calls


def test_frame_target_and_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/wait-for-selector"):
            body = request.read()
            assert b"stripe_checkout" in body
            return httpx.Response(200, json={"ok": True, "selector": "input", "state": "visible"})
        if request.url.path.endswith("/missing"):
            return httpx.Response(404, json={"error": "session not found"})
        if request.url.path.endswith("/type"):
            return httpx.Response(200, json={"ok": False, "error": "timeout"})
        raise AssertionError(request.url.path)

    browser = _mount(handler)
    page = browser.session("s1")
    frame = FrameTarget(selector="iframe[name=stripe_checkout]")
    data = page.wait_for_selector("input", timeout=20000, frame=frame)
    assert data["ok"] is True

    with pytest.raises(SessionNotFound):
        browser.session("missing").info()

    with pytest.raises(ActionFailed, match="timeout"):
        page.type("x", selector="input")


def test_upload_file_payload():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"ok": True, "id": "s1", "url": "https://x", "title": "t"})

    browser = _mount(handler)
    page = browser.session("s1")
    page.upload("input[type=file]", [UploadFile(name="a.txt", mime_type="text/plain", data=b"hi")])
    assert b"a.txt" in captured["body"]
    assert b"bufferBase64" in captured["body"]
