from __future__ import annotations

import base64
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from pybroswer.dom import (
    Node,
    body_of,
    document_element,
    form_action,
    form_fields,
    frames_of,
    inspect_node,
    parse_html,
    query_all,
    query_one,
    title_of,
)
from pybroswer.exceptions import ActionFailed, ApiError, SessionNotFound
from pybroswer.ua import list_presets, public_url, resolve_device, timeout_of

PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


class HttpEngine:
    """Fetch + HTML engine for PyDroid. No Chromium, no PC host."""

    def __init__(
        self,
        *,
        max_sessions: int = 5,
        idle_ms: int = 10 * 60 * 1000,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.max_sessions = max_sessions
        self.idle_ms = idle_ms
        self.timeout = timeout
        self._shared_client = client
        self._sessions: dict[str, dict[str, Any]] = {}
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        for sid in list(self._sessions):
            self._close_session(sid)
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
            return 200, {"ok": True, "service": "pybroswer", "engine": "http"}, "json"
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
            if not self._close_session(sid):
                raise SessionNotFound("session not found")
            return 200, {"ok": True}, "json"
        if method == "GET" and action is None:
            return 200, self._dto(self._get(sid)), "json"

        session = self._get(sid)
        if method == "POST" and action == "goto":
            return 200, self._goto(session, body), "json"
        if method == "POST" and action == "back":
            return 200, self._back(session), "json"
        if method == "POST" and action == "reload":
            return 200, self._reload(session), "json"
        if method == "POST" and action == "wait-for-selector":
            return 200, self._wait_for_selector(session, body), "json"
        if method == "GET" and action in {"screenshot", "screenshot.png"}:
            png = PIXEL_PNG
            if str(params.get("format") or "") == "json" and action == "screenshot":
                return 200, {"screenshotBase64": base64.b64encode(png).decode(), "url": session["url"]}, "json"
            return 200, png, "png"
        if method == "GET" and action == "frames":
            return 200, {"frames": frames_of(session["root"], session["url"])}, "json"
        if method == "POST" and action == "evaluate":
            return 200, {"ok": True, "result": self._evaluate(session, body)}, "json"
        if method == "POST" and action == "click":
            return 200, self._click(session, body), "json"
        if method == "POST" and action == "type":
            return 200, self._type(session, body), "json"
        if method == "POST" and action == "press":
            return 200, self._press(session, body), "json"
        if method == "POST" and action == "select":
            return 200, self._select(session, body), "json"
        if method == "POST" and action == "scroll":
            return 200, self._after_action(session, body), "json"
        if method == "POST" and action == "wait-for-load":
            return 200, self._after_action(session, body), "json"
        if method == "GET" and action == "html":
            html = session["html"]
            if str(params.get("format") or "") == "html":
                return 200, html.encode("utf-8"), "html"
            return 200, {"url": session["url"], "html": html[:400000], "frames": frames_of(session["root"], session["url"])}, "json"
        if method == "POST" and action == "inspect":
            return 200, self._inspect(session, body), "json"
        if method == "GET" and action == "logs":
            return 200, {"logs": session["logs"]}, "json"
        if method == "POST" and action == "upload":
            return 200, self._upload(session, body), "json"
        if method == "GET" and action == "page":
            shot = self._after_action(session, {})
            shot["html"] = session["html"][:200000]
            return 200, shot, "json"
        return 404, {"error": "not found"}, "json"

    def _health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "service": "pybroswer",
            "engine": "http",
            "sessions": len(self._sessions),
            "maxSessions": self.max_sessions,
        }

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
        sid = str(uuid.uuid4())
        client = self._shared_client or httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": profile["userAgent"],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        html = "<html><head><title></title></head><body></body></html>"
        session = {
            "id": sid,
            "client": client,
            "owns_client": self._shared_client is None,
            "viewport": profile["viewport"],
            "device": profile["device"],
            "userAgent": profile["userAgent"],
            "isMobile": profile["isMobile"],
            "url": "about:blank",
            "title": "",
            "html": html,
            "root": parse_html(html),
            "status": 0,
            "focused": None,
            "history": [],
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "lastUsed": _now_ms(),
            "logs": [],
        }
        self._sessions[sid] = session
        return session

    def _close_session(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if not session:
            return False
        if session.get("owns_client"):
            try:
                session["client"].close()
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
        body = body_of(session["root"])
        text = body.inner_text if body else session["root"].inner_text
        return {
            **self._dto(session),
            "text": text[:20000],
            "screenshotBase64": base64.b64encode(PIXEL_PNG).decode("ascii"),
        }

    def _after_action(self, session: dict[str, Any], opts: dict[str, Any] | None = None) -> dict[str, Any]:
        opts = opts or {}
        if opts.get("screenshot") is False:
            return {**self._dto(session), "ok": True, "screenshotBase64": None, "text": ""}
        return {"ok": True, **self._snapshot(session)}

    def _log(self, session: dict[str, Any], kind: str, text: str, level: str = "info") -> None:
        session["logs"].append({"type": kind, "level": level, "text": text, "ts": _now_ms()})
        if len(session["logs"]) > 500:
            session["logs"].pop(0)

    def _fetch(self, session: dict[str, Any], url: str, *, method: str = "GET", data: dict[str, str] | None = None) -> int:
        return self._open(session, url, method=method, data=data, push=True)

    def _open(
        self,
        session: dict[str, Any],
        url: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
        push: bool = True,
    ) -> int:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("http(s) url required")
        if push and session["url"] and session["url"] != "about:blank":
            session["history"].append(session["url"])
        headers = {"User-Agent": session["userAgent"], "Referer": session["url"]}
        if method.upper() == "GET" and data:
            response = session["client"].request("GET", url, params=data, headers=headers)
        elif method.upper() == "POST":
            response = session["client"].request("POST", url, data=data or {}, headers=headers)
        else:
            response = session["client"].request(method, url, headers=headers)
        html = response.text
        session["html"] = html
        session["root"] = parse_html(html)
        session["url"] = str(response.url)
        session["title"] = title_of(session["root"])
        session["status"] = response.status_code
        session["focused"] = None
        self._log(session, "console", f"{method} {session['url']} {session['status']}")
        return response.status_code

    def _goto(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        url = public_url(body.get("url"))
        if not url:
            raise ValueError("http(s) url required")
        status = self._fetch(session, url)
        shot = self._snapshot(session)
        shot["status"] = status
        return shot

    def _browse(self, body: dict[str, Any]) -> dict[str, Any]:
        url = public_url(body.get("url"))
        if not url:
            raise ValueError("http(s) url required")
        session = self._create_session(body)
        try:
            status = self._fetch(session, url)
            shot = self._snapshot(session)
            return {"ok": True, "sessionId": session["id"], "status": status, **shot}
        except Exception:
            self._close_session(session["id"])
            raise

    def _back(self, session: dict[str, Any]) -> dict[str, Any]:
        if not session["history"]:
            return self._after_action(session, {})
        url = session["history"].pop()
        self._open(session, url, push=False)
        return self._after_action(session, {})

    def _reload(self, session: dict[str, Any]) -> dict[str, Any]:
        if session["url"] in {"", "about:blank"}:
            return self._after_action(session, {})
        self._open(session, session["url"], push=False)
        return self._after_action(session, {})

    def _scope_root(self, session: dict[str, Any], body: dict[str, Any] | None) -> Node:
        body = body or {}
        root = session["root"]
        frame_sel = body.get("frameSelector") or body.get("iframe")
        if frame_sel:
            iframe = query_one(root, frame_sel)
            if not iframe or iframe.tag != "iframe":
                raise RuntimeError("frame not found for frameSelector")
            src = iframe.attrs.get("src")
            if src:
                html = f'<html><body><p>iframe {urljoin(session["url"], src)}</p></body></html>'
                return parse_html(html)
        return root

    def _wait_for_selector(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        root = self._scope_root(session, body)
        node = query_one(root, selector)
        if not node:
            raise RuntimeError(f"selector not found: {selector}")
        return {
            "ok": True,
            "selector": selector,
            "state": body.get("state") or "visible",
            "timeout": timeout_of(body, 15000),
            "frames": frames_of(session["root"], session["url"]),
        }

    def _click(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            if body.get("x") is not None:
                raise RuntimeError("coordinate click needs Chromium; use selector on PyDroid")
            raise ValueError("selector or x,y required")
        root = self._scope_root(session, body)
        node = query_one(root, selector)
        if not node:
            raise RuntimeError(f"selector not found: {selector}")
        session["focused"] = node
        how = "click"
        if node.tag == "a" and node.href:
            href = node.href.strip()
            if href.lower().startswith("javascript:"):
                how = "js"
            else:
                self._fetch(session, urljoin(session["url"], href))
        elif node.tag == "button" or (node.tag == "input" and node.type in {"submit", "image"}):
            form = node.form()
            if form:
                self._submit(session, form, extra={node.name: node.value} if node.name else None)
        elif node.tag == "input" and node.type == "checkbox":
            if "checked" in node.attrs:
                del node.attrs["checked"]
            else:
                node.attrs["checked"] = "checked"
        elif node.tag == "input" and node.type == "radio":
            node.attrs["checked"] = "checked"
        shot = self._after_action(session, {"screenshot": body.get("screenshot") is not False})
        shot["click"] = how
        return shot

    def _submit(self, session: dict[str, Any], form: Node, extra: dict[str, str] | None = None) -> None:
        method, action = form_action(form, session["url"])
        data = form_fields(form)
        if extra:
            data.update({k: v for k, v in extra.items() if k})
        self._fetch(session, action, method=method, data=data)

    def _type(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        text = body.get("text")
        if not isinstance(text, str):
            raise ValueError("text required")
        node = None
        if body.get("selector"):
            node = query_one(self._scope_root(session, body), body["selector"])
            if not node:
                raise RuntimeError(f"selector not found: {body['selector']}")
        else:
            node = session.get("focused")
        if node is None:
            raise RuntimeError("no focused element; pass selector")
        node.value = text
        session["focused"] = node
        session["html"] = _html_of(session["root"])
        return self._after_action(session, {"screenshot": body.get("screenshot") is not False})

    def _press(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        key = body.get("key")
        if not key:
            raise ValueError("key required")
        node = None
        if body.get("selector"):
            node = query_one(self._scope_root(session, body), body["selector"])
        else:
            node = session.get("focused")
        if str(key).lower() in {"enter", "return"} and node is not None:
            form = node.form()
            if form:
                self._submit(session, form)
        return self._after_action(session, {"screenshot": body.get("screenshot") is not False})

    def _select(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        node = query_one(self._scope_root(session, body), selector)
        if not node:
            raise RuntimeError(f"selector not found: {selector}")
        options = [n for n in node.descendants() if n.tag == "option"]
        chosen: list[str] = []
        target = None
        if body.get("label") is not None:
            target = next((o for o in options if o.inner_text == str(body["label"])), None)
        elif body.get("index") is not None:
            idx = int(body["index"])
            target = options[idx] if 0 <= idx < len(options) else None
        else:
            values = body.get("values", body.get("value"))
            if values is None:
                raise ValueError("value, label, or index required")
            want = values if isinstance(values, list) else [values]
            for opt in options:
                val = opt.attrs.get("value", opt.inner_text)
                if val in want or opt.inner_text in want:
                    target = opt
                    break
        for opt in options:
            opt.attrs.pop("selected", None)
        if target is None:
            raise RuntimeError("option not found")
        target.attrs["selected"] = "selected"
        chosen = [target.attrs.get("value", target.inner_text)]
        session["html"] = _html_of(session["root"])
        shot = self._after_action(session, {"screenshot": body.get("screenshot") is not False})
        shot["selected"] = chosen
        return shot

    def _inspect(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        node = query_one(self._scope_root(session, body), selector)
        if not node:
            raise RuntimeError(f"selector not found: {selector}")
        return {"ok": True, "selector": selector, **inspect_node(node)}

    def _upload(self, session: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        selector = body.get("selector")
        if not selector:
            raise ValueError("selector required")
        files = body.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError("files[] required ({ name, mimeType, bufferBase64 })")
        node = query_one(self._scope_root(session, body), selector)
        if not node:
            raise RuntimeError(f"selector not found: {selector}")
        node.attrs["value"] = files[0].get("name") or "file.bin"
        session["html"] = _html_of(session["root"])
        return self._after_action(session, {"screenshot": body.get("screenshot") is not False})

    def _evaluate(self, session: dict[str, Any], body: dict[str, Any]) -> Any:
        script = body.get("script") or body.get("expression") or body.get("js")
        if not script or not isinstance(script, str):
            raise ValueError("script required")
        root = self._scope_root(session, body)
        return _eval_script(script.strip(), session, root)

    def _reap(self) -> None:
        now = _now_ms()
        for sid, session in list(self._sessions.items()):
            if now - session["lastUsed"] > self.idle_ms:
                self._close_session(sid)


def _eval_script(script: str, session: dict[str, Any], root: Node) -> Any:
    if script in {"document.title", "document.title;"}:
        return session["title"]
    if script in {"document.URL", "document.URL;", "location.href", "location.href;"}:
        return session["url"]
    if script in {"document.body.innerText", "document.body.innerText;"}:
        body = body_of(root)
        return body.inner_text if body else ""
    if script in {"document.documentElement.outerHTML", "document.documentElement.innerHTML"}:
        return _html_of(document_element(root))
    m = re_query(script)
    if m:
        sel, prop = m
        if script.strip().startswith("document.querySelectorAll"):
            nodes = query_all(root, sel)
            if prop == "length":
                return len(nodes)
            return [getattr_prop(n, prop) for n in nodes]
        node = query_one(root, sel)
        if node is None:
            return None
        return getattr_prop(node, prop)
    raise RuntimeError(f"http engine cannot run JS: {script[:80]}")


def re_query(script: str) -> tuple[str, str] | None:
    import re as _re

    m = _re.match(
        r"""document\.querySelector(All)?\(\s*(['\"])(.+?)\2\s*\)(?:\.(\w+))?""",
        script.rstrip(";"),
    )
    if not m:
        return None
    return m.group(3), m.group(4) or "innerText"


def getattr_prop(node: Node, prop: str) -> Any:
    if prop in {"innerText", "textContent"}:
        return node.inner_text
    if prop == "innerHTML":
        return node.inner_html
    if prop == "value":
        return node.value
    if prop == "href":
        return node.href
    if prop == "id":
        return node.id
    if prop == "tagName":
        return node.tag.upper()
    return node.attrs.get(prop.lower())


def _html_of(root: Node) -> str:
    from pybroswer.dom import _serialize

    if root.tag == "document":
        return "".join(_serialize(c) if not isinstance(c, str) else c for c in root.children)
    return _serialize(root)


def _now_ms() -> int:
    return int(time.time() * 1000)


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
