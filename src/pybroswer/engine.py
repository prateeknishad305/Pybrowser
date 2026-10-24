from __future__ import annotations

import base64
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs

from pybroswer.exceptions import ActionFailed, ApiError, EngineError, SessionNotFound
from pybroswer.frames import eval_target, list_frames, resolve_scope, wait_locator
from pybroswer.ua import list_presets, public_url, resolve_device, timeout_of

GOTO_MS = 30000


class ChromiumEngine:
    def __init__(
        self,
        *,
        headless: bool = True,
        max_sessions: int = 5,
        idle_ms: int = 10 * 60 * 1000,
        executable_path: str | None = None,
        channel: str | None = None,
    ) -> None:
        self.headless = headless
        self.max_sessions = max_sessions
        self.idle_ms = idle_ms
        self.executable_path = executable_path
        self.channel = channel
        self._playwright: Any = None
        self._browser: Any = None
        self._pw_cm: Any = None
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise EngineError(
                    "playwright is not installed. On PC run: pip install 'pybroswer[chromium]' && playwright install chromium"
                ) from exc
            self._pw_cm = sync_playwright().start()
            self._playwright = self._pw_cm
            launch_kwargs: dict[str, Any] = {
                "headless": self.headless,
                "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            }
            if self.executable_path:
                launch_kwargs["executable_path"] = self.executable_path
            if self.channel:
                launch_kwargs["channel"] = self.channel
            self._browser = self._playwright.chromium.launch(**launch_kwargs)
            self._started = True

    def stop(self) -> None:
        with self._lock:
            for sid in list(self._sessions):
                self._close_session(sid)
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
            self._browser = None
            if self._pw_cm:
                try:
                    self._pw_cm.stop()
                except Exception:
                    pass
            self._pw_cm = None
            self._playwright = None
            self._started = False

    def handle(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any, str]:
        method = method.upper()
        path, query = _split_path(path)
        merged = {**query, **(params or {})}
        body = body or {}
        with self._lock:
            try:
                return self._dispatch(method, path, body, merged)
            except SessionNotFound as exc:
                return 404, {"error": str(exc)}, "json"
            except ValueError as exc:
                return 400, {"error": str(exc)}, "json"
            except Exception as exc:
                return 200, {"ok": False, "error": str(exc)}, "json"

    def _dispatch(
        self, method: str, path: str, body: dict[str, Any], params: dict[str, Any]
    ) -> tuple[int, Any, str]:
        if method == "GET" and path in {"/", ""}:
            return (
                200,
                {
                    "ok": True,
                    "service": "pybroswer",
                    "engine": "chromium",
                    "hint": "from pybroswer import Browser; Browser.connect('http://HOST:5173')",
                },
                "json",
            )
        if method == "GET" and path == "/api/v1/health":
            return 200, self._health(), "json"
        if method == "GET" and path == "/api/v1/ua":
            return 200, {"presets": list_presets()}, "json"
        if method == "POST" and path == "/api/v1/browse":
            return 200, self._browse(body), "json"
        if method == "POST" and path == "/api/v1/sessions":
            session = self._create_session(body)
            return 201, self._dto(session), "json"
        if method == "GET" and path == "/api/v1/sessions":
            return 200, {"sessions": [self._dto(s) for s in self._sessions.values()]}, "json"

        sid, action = _session_route(path)
        if not sid:
            return 404, {"error": "not found"}, "json"
        if method == "DELETE" and action is None:
            ok = self._close_session(sid)
            if not ok:
                raise SessionNotFound("session not found")
            return 200, {"ok": True}, "json"
        if method == "GET" and action is None:
            return 200, self._dto(self._get(sid)), "json"

        session = self._get(sid)
        if method == "POST" and action == "goto":
            return 200, self._goto(session, body), "json"
        if method == "POST" and action == "back":
            session["page"].go_back(wait_until="domcontentloaded", timeout=GOTO_MS)
            return 200, self._after_action(session), "json"
        if method == "POST" and action == "reload":
            session["page"].reload(wait_until="domcontentloaded", timeout=GOTO_MS)
            return 200, self._after_action(session), "json"
        if method == "POST" and action == "wait-for-selector":
            return 200, self._wait_for_selector(session, body), "json"
        if method == "GET" and action in {"screenshot", "screenshot.png"}:
            return self._screenshot(session, params, png_path=action == "screenshot.png")
        if method == "GET" and action == "frames":
            return 200, {"frames": list_frames(session["page"])}, "json"
        if method == "POST" and action == "evaluate":
            return 200, self._evaluate(session, body), "json"
        if method == "POST" and action == "click":
            return 200, self._click(session, body), "json"
        if method == "POST" and action == "type":
            return 200, self._type(session, body), "json"
        if method == "POST" and action == "press":
            return 200, self._press(session, body), "json"
        if method == "POST" and action == "select":
            return 200, self._select(session, body), "json"
        if method == "POST" and action == "scroll":
            return 200, self._scroll(session, body), "json"
        if method == "POST" and action == "wait-for-load":
            return 200, self._wait_for_load(session, body), "json"
        if method == "GET" and action == "html":
            return self._html(session, params)
        if method == "POST" and action == "inspect":
            return 200, self._inspect(session, body), "json"
        if method == "GET" and action == "logs":
            return 200, {"logs": session["logs"]}, "json"
        if method == "POST" and action == "upload":
            return 200, self._upload(session, body), "json"
        if method == "GET" and action == "page":
            html = session["page"].content()
            shot = self._after_action(session)
            shot["html"] = html[:200000]
            return 200, shot, "json"
        return 404, {"error": "not found"}, "json"

    def _health(self) -> dict[str, Any]:
        try:
            self.start()
            ok = bool(self._browser and self._browser.is_connected())
            return {
                "ok": ok,
                "service": "pybroswer",
                "engine": "chromium",
                "sessions": len(self._sessions),
                "maxSessions": self.max_sessions,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _get(self, session_id: str) -> dict[str, Any]:
        self._reap()
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFound("session not found")
        session["lastUsed"] = _now_ms()
        return session

    def _create_session(self, opts: dict[str, Any] | None = None) -> dict[str, Any]:
        self.start()
        self._reap()
        if len(self._sessions) >= self.max_sessions:
            oldest = min(self._sessions.values(), key=lambda s: s["lastUsed"])
            self._close_session(oldest["id"])
        profile = resolve_device(opts)
        viewport = profile["viewport"]
        context = self._browser.new_context(
            viewport=viewport,
            user_agent=profile["userAgent"],
            is_mobile=profile["isMobile"],
            has_touch=profile["hasTouch"],
            java_script_enabled=True,
        )
        page = context.new_page()
        sid = str(uuid.uuid4())
        logs: list[dict[str, Any]] = []

        def on_console(msg: Any) -> None:
            logs.append({"type": "console", "level": msg.type, "text": msg.text, "ts": _now_ms()})
            if len(logs) > 500:
                logs.pop(0)

        def on_page_error(err: Any) -> None:
            logs.append({"type": "pageerror", "level": "error", "text": str(err), "ts": _now_ms()})
            if len(logs) > 500:
                logs.pop(0)

        def on_request_failed(req: Any) -> None:
            failure = req.failure
            text = f"{req.method} {req.url} {failure if failure else ''}"
            logs.append({"type": "requestfailed", "level": "error", "text": text, "ts": _now_ms()})
            if len(logs) > 500:
                logs.pop(0)

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("requestfailed", on_request_failed)
        session = {
            "id": sid,
            "context": context,
            "page": page,
            "viewport": viewport,
            "device": profile["device"],
            "userAgent": profile["userAgent"],
            "isMobile": profile["isMobile"],
            "url": "about:blank",
            "title": "",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "lastUsed": _now_ms(),
            "logs": logs,
        }
        self._sessions[sid] = session
        return session

    def _close_session(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        try:
            session["context"].close()
        except Exception:
            pass
        return True

    def _dto(self, session: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": session["id"],
            "url": session["url"],
            "title": session["title"],
            "createdAt": session["createdAt"],
            "lastUsed": datetime.fromtimestamp(session["lastUsed"] / 1000, tz=timezone.utc).isoformat(),
            "viewport": session["viewport"],
            "device": session["device"],
            "userAgent": session["userAgent"],
            "isMobile": session["isMobile"],
        }

    def _snapshot(self, session: dict[str, Any]) -> dict[str, Any]:
        page = session["page"]
        session["url"] = page.url
        try:
            session["title"] = page.title()
        except Exception:
            session["title"] = ""
        try:
            text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            text = ""
        png = page.screenshot(type="png", full_page=False)
        return {
            **self._dto(session),
            "text": text[:20000],
            "screenshotBase64": base64.b64encode(png).decode("ascii"),
        }

    def _after_action(self, session: dict[str, Any], opts: dict[str, Any] | None = None) -> dict[str, Any]:
        opts = opts or {}
        settle = min(int(opts.get("settleMs") or 250), 2000)
        try:
            session["page"].wait_for_timeout(settle)
        except Exception:
            pass
        if opts.get("screenshot") is False:
            session["url"] = session["page"].url
            try:
                session["title"] = session["page"].title()
            except Exception:
                session["title"] = ""
            return {**self._dto(session), "ok": True, "screenshotBase64": None, "text": ""}
        try:
            return {"ok": True, **self._snapshot(session)}
        except Exception as exc:
            session["url"] = session["page"].url
            return {
                "ok": True,
                **self._dto(session),
                "screenshotError": str(exc),
                "text": "",
                "screenshotBase64": None,
            }

    def _goto(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        url = public_url(body.get("url"))
        if not url:
            raise ValueError("http(s) url required")
        nav = session["page"].goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
        try:
            session["page"].wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        shot = self._snapshot(session)
        shot["status"] = nav.status if nav else 0
        return shot

    def _browse(self, body: dict[str, Any]) -> dict[str, Any]:
        url = public_url(body.get("url"))
        if not url:
            raise ValueError("http(s) url required")
        session = self._create_session(body)
        try:
            nav = session["page"].goto(url, wait_until="domcontentloaded", timeout=GOTO_MS)
            try:
                session["page"].wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            shot = self._snapshot(session)
            return {"ok": True, "sessionId": session["id"], "status": nav.status if nav else 0, **shot}
        except Exception:
            self._close_session(session["id"])
            raise

    def _wait_for_selector(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        timeout = timeout_of(body, 15000)
        state = body.get("state") or "visible"
        scope = resolve_scope(session["page"], body)
        wait_locator(scope, selector, timeout, state)
        return {
            "ok": True,
            "selector": selector,
            "state": state,
            "timeout": timeout,
            "frames": list_frames(session["page"]),
        }

    def _screenshot(self, session: dict[str, Any], params: dict[str, Any], *, png_path: bool) -> tuple[int, Any, str]:
        full_page = str(params.get("fullPage") or "") == "true"
        png = session["page"].screenshot(type="png", full_page=full_page)
        if not png_path and str(params.get("format") or "") == "json":
            return 200, {"screenshotBase64": base64.b64encode(png).decode("ascii"), "url": session["page"].url}, "json"
        return 200, png, "png"

    def _evaluate(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        script = body.get("script") or body.get("expression") or body.get("js")
        if not script or not isinstance(script, str):
            raise ValueError("script required")
        target = eval_target(session["page"], body)
        result = target.evaluate(script)
        return {"ok": True, "result": result}

    def _click(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        x, y = body.get("x"), body.get("y")
        timeout = timeout_of(body, 8000)
        how = "mouse"
        if selector:
            scope = resolve_scope(session["page"], body)
            loc = wait_locator(scope, selector, timeout, body.get("state") or "visible")
            how = _click_locator(loc, timeout)
        elif _is_num(x) and _is_num(y):
            session["page"].mouse.click(float(x), float(y))
        else:
            raise ValueError("selector or x,y required")
        shot = self._after_action(session, {"screenshot": body.get("screenshot") is not False, "settleMs": body.get("settleMs")})
        shot["click"] = how
        return shot

    def _type(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        text = body.get("text")
        if not isinstance(text, str):
            raise ValueError("text required")
        timeout = timeout_of(body, 15000)
        selector = body.get("selector")
        if selector:
            scope = resolve_scope(session["page"], body)
            loc = wait_locator(scope, selector, timeout, body.get("state") or "visible")
            loc.fill(text, timeout=timeout)
        else:
            session["page"].keyboard.type(text)
        return self._after_action(session, {"screenshot": body.get("screenshot") is not False})

    def _press(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        key = body.get("key")
        if not key:
            raise ValueError("key required")
        timeout = timeout_of(body, 15000)
        if body.get("selector"):
            scope = resolve_scope(session["page"], body)
            loc = wait_locator(scope, body["selector"], timeout, body.get("state") or "visible")
            loc.press(key, timeout=timeout)
        else:
            session["page"].keyboard.press(key)
        return self._after_action(session, {"screenshot": body.get("screenshot") is not False})

    def _select(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        timeout = timeout_of(body, 15000)
        values = body.get("values", body.get("value"))
        scope = resolve_scope(session["page"], body)
        loc = wait_locator(scope, selector, timeout, body.get("state") or "visible")
        if body.get("label") is not None:
            selected = loc.select_option(label=body["label"], timeout=timeout)
        elif body.get("index") is not None:
            selected = loc.select_option(index=int(body["index"]), timeout=timeout)
        elif values is not None:
            selected = loc.select_option(values, timeout=timeout)
        else:
            raise ValueError("value, label, or index required")
        shot = self._after_action(session, {"screenshot": body.get("screenshot") is not False})
        shot["selected"] = selected
        return shot

    def _scroll(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        dy = int(body.get("dy") or 400)
        dx = int(body.get("dx") or 0)
        if body.get("selector"):
            scope = resolve_scope(session["page"], body)
            loc = wait_locator(scope, body["selector"], timeout_of(body, 8000), "attached")
            loc.scroll_into_view_if_needed()
        else:
            session["page"].mouse.wheel(dx, dy)
        return self._after_action(session, {"screenshot": body.get("screenshot") is not False})

    def _wait_for_load(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        state = body.get("state") or "networkidle"
        timeout = timeout_of(body, 15000)
        session["page"].wait_for_load_state(state, timeout=timeout)
        return self._after_action(session)

    def _html(self, session: dict[str, Any], params: dict[str, Any]) -> tuple[int, Any, str]:
        scope = resolve_scope(session["page"], params)
        if scope["kind"] == "frame":
            html = scope["root"].content()
        else:
            html = session["page"].content()
        if str(params.get("format") or "") == "html":
            return 200, html.encode("utf-8"), "html"
        return 200, {"url": session["page"].url, "html": html[:400000], "frames": list_frames(session["page"])}, "json"

    def _inspect(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        scope = resolve_scope(session["page"], body)
        loc = wait_locator(scope, selector, timeout_of(body, 8000), "attached")
        info = loc.evaluate(
            """el => ({
                tag: el.tagName,
                id: el.id,
                name: el.getAttribute("name"),
                type: el.getAttribute("type"),
                value: el.value,
                text: (el.innerText || "").slice(0, 2000),
                href: el.getAttribute("href"),
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                rect: el.getBoundingClientRect().toJSON(),
            })"""
        )
        return {"ok": True, "selector": selector, **info}

    def _upload(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        files = body.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("files[] required ({ name, mimeType, bufferBase64 })")
        payloads = [
            {
                "name": f.get("name") or "file.bin",
                "mimeType": f.get("mimeType") or "application/octet-stream",
                "buffer": base64.b64decode(f.get("bufferBase64") or f.get("bodyBase64") or ""),
            }
            for f in files
        ]
        scope = resolve_scope(session["page"], body)
        loc = wait_locator(scope, selector, timeout_of(body, 15000), "attached")
        loc.set_input_files(payloads)
        return self._after_action(session, {"screenshot": body.get("screenshot") is not False})

    def _reap(self) -> None:
        now = _now_ms()
        for sid, session in list(self._sessions.items()):
            if now - session["lastUsed"] > self.idle_ms:
                self._close_session(sid)


class EngineTransport:
    def __init__(self, engine: Any, *, owns: bool = True) -> None:
        self.base_url = "engine://local"
        self._engine = engine
        self._owns = owns

    def close(self) -> None:
        if self._owns:
            self._engine.stop()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        status, payload, kind = self._engine.handle(method, path, json, params)
        if status == 404:
            message = _payload_error(payload)
            if "session" in message.lower():
                raise SessionNotFound(message, status_code=404, payload=_as_dict(payload))
            raise ApiError(message, status_code=404, payload=_as_dict(payload))
        if status >= 400:
            raise ApiError(_payload_error(payload), status_code=status, payload=_as_dict(payload))
        if not expect_json or kind in {"png", "html"}:
            if isinstance(payload, str):
                return payload.encode("utf-8")
            return payload
        if isinstance(payload, dict) and payload.get("ok") is False and payload.get("error"):
            raise ActionFailed(str(payload["error"]), status_code=status, payload=payload)
        return payload


def _click_locator(loc: Any, timeout: int) -> str:
    t = min(timeout or 8000, 12000)
    try:
        loc.click(timeout=t)
        return "click"
    except Exception:
        try:
            loc.click(timeout=min(t, 5000), force=True)
            return "force"
        except Exception:
            loc.evaluate("el => el.click()")
            return "js"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _is_num(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _split_path(path: str) -> tuple[str, dict[str, Any]]:
    if "?" in path:
        path, qs = path.split("?", 1)
        parsed = {k: v[-1] if v else "" for k, v in parse_qs(qs, keep_blank_values=True).items()}
        return path.rstrip("/") or "/", parsed
    return path.rstrip("/") or "/", {}


def _session_route(path: str) -> tuple[str | None, str | None]:
    parts = [p for p in path.split("/") if p]
    if len(parts) < 4 or parts[0] != "api" or parts[1] != "v1" or parts[2] != "sessions":
        return None, None
    sid = parts[3]
    action = "/".join(parts[4:]) if len(parts) > 4 else None
    return sid, action


def _payload_error(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("error") or "error")
    return str(payload)


def _as_dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {"error": payload}
