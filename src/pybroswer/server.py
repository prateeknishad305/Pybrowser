from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from pybroswer.engine import ChromiumEngine


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


class _Handler(BaseHTTPRequestHandler):
    engine: ChromiumEngine

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _handle(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        body: dict[str, Any] = {}
        if raw:
            try:
                parsed_body = json.loads(raw.decode("utf-8"))
                if isinstance(parsed_body, dict):
                    body = parsed_body
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json"}, "json")
                return
        params = {k: v[-1] if v else "" for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
        status, payload, kind = self.engine.handle(self.command, parsed.path, body, params)
        self._send(status, payload, kind)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send(self, status: int, payload: Any, kind: str) -> None:
        if kind == "png":
            data = payload if isinstance(payload, bytes) else bytes(payload)
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if kind == "html":
            data = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class BrowserServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 5173,
        *,
        engine: ChromiumEngine | None = None,
        headless: bool = True,
        max_sessions: int = 5,
    ) -> None:
        self.host = host
        self.port = port
        self.engine = engine or ChromiumEngine(headless=headless, max_sessions=max_sessions)
        self._httpd: HTTPServer | None = None

    @property
    def url(self) -> str:
        host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"http://{host}:{self.port}"

    @property
    def lan_url(self) -> str:
        return f"http://{local_ip()}:{self.port}"

    def start(self) -> None:
        self.engine.start()
        handler = type("Handler", (_Handler,), {"engine": self.engine})
        self._httpd = HTTPServer((self.host, self.port), handler)
        self.port = self._httpd.server_address[1]

    def serve_forever(self) -> None:
        if not self._httpd:
            self.start()
        assert self._httpd is not None
        print(f"pybroswer Chromium on {self.lan_url}")
        print(f"PyDroid: Browser.connect('{self.lan_url}')")
        try:
            self._httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        self.engine.stop()


def serve(host: str = "0.0.0.0", port: int = 5173, *, headless: bool = True) -> None:
    BrowserServer(host=host, port=port, headless=headless).serve_forever()
