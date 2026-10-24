from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "mobile": {
        "device": "mobile",
        "userAgent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1"
        ),
        "viewport": {"width": 390, "height": 844},
        "isMobile": True,
        "hasTouch": True,
    },
    "mobile-ios": {
        "device": "mobile-ios",
        "userAgent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1"
        ),
        "viewport": {"width": 390, "height": 844},
        "isMobile": True,
        "hasTouch": True,
    },
    "mobile-android": {
        "device": "mobile-android",
        "userAgent": (
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.6668.100 Mobile Safari/537.36"
        ),
        "viewport": {"width": 412, "height": 915},
        "isMobile": True,
        "hasTouch": True,
    },
    "desktop": {
        "device": "desktop",
        "userAgent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.6668.100 Safari/537.36"
        ),
        "viewport": {"width": 1366, "height": 768},
        "isMobile": False,
        "hasTouch": False,
    },
    "desktop-mac": {
        "device": "desktop-mac",
        "userAgent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/129.0.6668.100 Safari/537.36"
        ),
        "viewport": {"width": 1440, "height": 900},
        "isMobile": False,
        "hasTouch": False,
    },
}


def resolve_device(opts: dict[str, Any] | None = None) -> dict[str, Any]:
    opts = opts or {}
    key = str(opts.get("device") or opts.get("ua") or opts.get("profile") or "mobile").lower()
    preset = PRESETS.get(key) or PRESETS["mobile"]
    viewport = {
        "width": int(opts.get("width") or preset["viewport"]["width"]),
        "height": int(opts.get("height") or preset["viewport"]["height"]),
    }
    return {
        "device": preset["device"],
        "userAgent": opts.get("userAgent") or preset["userAgent"],
        "viewport": viewport,
        "isMobile": preset["isMobile"],
        "hasTouch": preset["hasTouch"],
    }


def list_presets() -> list[dict[str, Any]]:
    return [
        {
            "device": p["device"],
            "userAgent": p["userAgent"],
            "viewport": p["viewport"],
            "isMobile": p["isMobile"],
        }
        for p in PRESETS.values()
    ]


def timeout_of(body: dict[str, Any] | None, fallback: int = 15000) -> int:
    if not body:
        return fallback
    raw = body.get("timeout", body.get("wait"))
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return fallback
    return int(n) if n > 0 else fallback


def public_url(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https", "about"}:
        return None
    return url
