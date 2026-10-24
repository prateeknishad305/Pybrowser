from __future__ import annotations

from pybroswer.engine import ChromiumEngine, EngineTransport
from pybroswer.exceptions import EngineError, SessionNotFound
from pybroswer.ua import list_presets, public_url, resolve_device, timeout_of


def test_resolve_device_and_url():
    d = resolve_device({"device": "desktop", "width": 800})
    assert d["device"] == "desktop"
    assert d["viewport"]["width"] == 800
    assert d["isMobile"] is False
    assert public_url("https://example.com") == "https://example.com"
    assert public_url("javascript:alert(1)") is None
    assert timeout_of({"timeout": 3000}, 15000) == 3000
    assert len(list_presets()) >= 5


def test_engine_without_playwright():
    engine = ChromiumEngine()
    engine._started = True
    engine._browser = None
    status, payload, kind = engine.handle("GET", "/api/v1/ua")
    assert status == 200 and kind == "json"
    assert payload["presets"][0]["device"]

    status, payload, _ = engine.handle("GET", "/api/v1/sessions")
    assert payload["sessions"] == []

    status, payload, _ = engine.handle("GET", "/api/v1/sessions/missing")
    assert status == 404
    assert "session" in payload["error"]

    status, payload, _ = engine.handle("POST", "/api/v1/browse", {"url": "not-a-url"})
    assert status == 400


def test_engine_transport_session_not_found():
    engine = ChromiumEngine()
    engine._started = True
    t = EngineTransport(engine, owns=False)
    try:
        t.request("GET", "/api/v1/sessions/nope")
    except SessionNotFound:
        pass
    else:
        raise AssertionError("expected SessionNotFound")


def test_launch_chromium_without_playwright_raises():
    from pybroswer import Browser

    try:
        import playwright  # noqa: F401
    except ImportError:
        try:
            Browser.launch(engine="chromium")
        except EngineError:
            return
        raise AssertionError("expected EngineError")
