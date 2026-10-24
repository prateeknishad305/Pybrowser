from __future__ import annotations

from pybroswer import Browser
from pybroswer.engine import EngineTransport


class FakeEngine:
    def __init__(self) -> None:
        self.closed = False
        self.sessions: dict[str, dict] = {}

    def handle(self, method, path, body=None, params=None):
        body = body or {}
        if method == "GET" and path == "/api/v1/health":
            return (
                200,
                {
                    "ok": True,
                    "service": "pybroswer",
                    "engine": "chromium",
                    "sessions": len(self.sessions),
                    "maxSessions": 5,
                },
                "json",
            )
        if method == "POST" and path == "/api/v1/sessions":
            self.sessions["s1"] = {"id": "s1", "device": body.get("device", "mobile")}
            return 201, {"id": "s1", "url": "about:blank", "title": "", "device": body.get("device")}, "json"
        if method == "POST" and path == "/api/v1/sessions/s1/goto":
            return 200, {"ok": True, "id": "s1", "url": body.get("url"), "title": "Example", "text": "hi"}, "json"
        if method == "POST" and path == "/api/v1/sessions/s1/evaluate":
            return 200, {"ok": True, "result": "Example"}, "json"
        if method == "DELETE" and path == "/api/v1/sessions/s1":
            self.sessions.pop("s1", None)
            return 200, {"ok": True}, "json"
        return 404, {"error": "not found"}, "json"

    def stop(self) -> None:
        self.closed = True


def test_browser_with_local_engine():
    engine = FakeEngine()
    with Browser(engine=engine) as browser:
        health = browser.health()
        assert health.ok and health.engine == "chromium"
        with browser.create_session(device="desktop") as page:
            shot = page.goto("https://example.com")
            assert shot.title == "Example"
            assert page.evaluate("document.title") == "Example"
    assert engine.closed is False


def test_engine_transport_owns_stop():
    engine = FakeEngine()
    t = EngineTransport(engine, owns=True)
    t.close()
    assert engine.closed is True
