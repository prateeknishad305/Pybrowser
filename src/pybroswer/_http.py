from __future__ import annotations

from typing import Any, Protocol

import httpx

from pybroswer.exceptions import ActionFailed, ApiError, SessionNotFound


class Transport(Protocol):
    base_url: str

    def close(self) -> None: ...

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any: ...


class HttpTransport:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 60.0,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._owns = client is None
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/json", **(headers or {})},
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        response = self._client.request(method, path, json=json, params=params)
        if response.status_code == 404:
            payload = _safe_json(response)
            message = _error_message(payload, response)
            if "session" in message.lower():
                raise SessionNotFound(message, status_code=404, payload=payload)
            raise ApiError(message, status_code=404, payload=payload)
        if response.status_code >= 400:
            payload = _safe_json(response)
            raise ApiError(_error_message(payload, response), status_code=response.status_code, payload=payload)
        if not expect_json:
            return response.content
        if not response.content:
            return {}
        ctype = response.headers.get("content-type", "")
        if "application/json" not in ctype:
            return response.content
        data = response.json()
        if isinstance(data, dict) and data.get("ok") is False and data.get("error"):
            raise ActionFailed(str(data["error"]), status_code=response.status_code, payload=data)
        return data


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        return {"error": response.text}
    return data if isinstance(data, dict) else {"error": data}


def _error_message(payload: dict[str, Any], response: httpx.Response) -> str:
    return str(payload.get("error") or response.reason_phrase or f"HTTP {response.status_code}")
