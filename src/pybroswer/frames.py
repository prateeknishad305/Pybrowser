from __future__ import annotations

from typing import Any


def frame_query(body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    return {
        "frame": body.get("frame"),
        "frameSelector": body.get("frameSelector") or body.get("iframe") or body.get("frameCss"),
        "frameName": body.get("frameName") or body.get("name"),
        "frameUrl": body.get("frameUrl"),
    }


def list_frames(page: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    frames = page.frames
    main = page.main_frame
    for index, frame in enumerate(frames):
        parent = frame.parent_frame
        out.append(
            {
                "index": index,
                "name": frame.name or "",
                "url": frame.url,
                "parentUrl": parent.url if parent else None,
                "isMain": frame == main,
            }
        )
    return out


def resolve_scope(page: Any, body: dict[str, Any] | None = None) -> dict[str, Any]:
    q = frame_query(body)
    if q["frameSelector"]:
        return {"kind": "locator", "root": page.frame_locator(q["frameSelector"]), "frame": q}
    frames = page.frames
    frame = page.main_frame
    raw = q["frame"]
    if isinstance(raw, int) and 0 <= raw < len(frames):
        frame = frames[raw]
    elif isinstance(raw, str) and raw.isdigit() and int(raw) < len(frames):
        frame = frames[int(raw)]
    if q["frameName"]:
        named = page.frame(name=q["frameName"])
        if named:
            frame = named
    if q["frameUrl"]:
        by_url = page.frame(url=q["frameUrl"])
        if by_url:
            frame = by_url
    if q["frameSelector"] or q["frameName"] or q["frameUrl"] or q["frame"] is not None:
        return {"kind": "frame", "root": frame, "frame": q}
    return {"kind": "page", "root": page, "frame": q}


def wait_locator(scope: dict[str, Any], selector: str, timeout: int, state: str = "visible") -> Any:
    if not selector:
        raise ValueError("selector required")
    if scope["kind"] == "locator":
        loc = scope["root"].locator(selector)
        loc.wait_for(state=state, timeout=timeout)
        return loc
    scope["root"].wait_for_selector(selector, state=state, timeout=timeout)
    return scope["root"].locator(selector)


def eval_target(page: Any, body: dict[str, Any] | None = None) -> Any:
    body = body or {}
    if body.get("frameSelector"):
        handle = page.query_selector(body["frameSelector"])
        frame = handle.content_frame() if handle else None
        if not frame:
            raise RuntimeError("frame not found for frameSelector")
        return frame
    if body.get("frameName"):
        named = page.frame(name=body["frameName"])
        if named:
            return named
    if body.get("frameUrl"):
        by_url = page.frame(url=body["frameUrl"])
        if by_url:
            return by_url
    frames = page.frames
    if isinstance(body.get("frame"), int) and 0 <= body["frame"] < len(frames):
        return frames[body["frame"]]
    return page
