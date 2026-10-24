from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None, parent: Node | None = None) -> None:
        self.tag = tag.lower()
        self.attrs = {k.lower(): v for k, v in (attrs or {}).items()}
        self.children: list[Node | str] = []
        self.parent = parent

    @property
    def id(self) -> str:
        return self.attrs.get("id", "")

    @property
    def name(self) -> str:
        return self.attrs.get("name", "")

    @property
    def type(self) -> str:
        return self.attrs.get("type", "")

    @property
    def classes(self) -> set[str]:
        return {c for c in self.attrs.get("class", "").split() if c}

    @property
    def href(self) -> str | None:
        return self.attrs.get("href")

    @property
    def value(self) -> str:
        if "value" in self.attrs:
            return self.attrs["value"]
        if self.tag == "textarea":
            return self.inner_text
        return ""

    @value.setter
    def value(self, text: str) -> None:
        self.attrs["value"] = text
        if self.tag in {"textarea", "option"}:
            self.children = [text]

    @property
    def inner_text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in {"script", "style"}:
                parts.append(child.inner_text)
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    @property
    def inner_html(self) -> str:
        return "".join(_serialize(c) for c in self.children)

    def descendants(self) -> list[Node]:
        out: list[Node] = []
        for child in self.children:
            if isinstance(child, Node):
                out.append(child)
                out.extend(child.descendants())
        return out

    def form(self) -> Node | None:
        node: Node | None = self
        while node is not None:
            if node.tag == "form":
                return node
            node = node.parent
        return None


def _serialize(node: Node | str) -> str:
    if isinstance(node, str):
        return node
    attrs = "".join(f' {k}="{v}"' for k, v in node.attrs.items())
    if node.tag in VOID:
        return f"<{node.tag}{attrs}>"
    return f"<{node.tag}{attrs}>{''.join(_serialize(c) for c in node.children)}</{node.tag}>"


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent = self._stack[-1]
        node = Node(tag, {k: v or "" for k, v in attrs}, parent)
        parent.children.append(node)
        if tag.lower() not in VOID:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID:
            return
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    parser = _Parser()
    parser.feed(html or "")
    parser.close()
    return parser.root


def document_element(root: Node) -> Node:
    for child in root.children:
        if isinstance(child, Node) and child.tag == "html":
            return child
    return root


def title_of(root: Node) -> str:
    for node in root.descendants():
        if node.tag == "title":
            return node.inner_text
    return ""


def body_of(root: Node) -> Node | None:
    for node in root.descendants():
        if node.tag == "body":
            return node
    return None


_ATTR_RE = re.compile(
    r"\[([^\s\]=~|^$*]+)\s*(?:([~|^$*]?=)\s*(?:\"([^\"]*)\"|'([^']*)'|([^\]]+)))?\]"
)
_SIMPLE_RE = re.compile(r"([a-zA-Z][\w:-]*|\*)|#([\w-]+)|\.([\w-]+)|(\[[^\]]+\])")


def query_all(root: Node, selector: str) -> list[Node]:
    selector = (selector or "").strip()
    if not selector:
        return []
    found: list[Node] = []
    seen: set[int] = set()
    for group in selector.split(","):
        for node in _query_group(root, group.strip()):
            key = id(node)
            if key not in seen:
                seen.add(key)
                found.append(node)
    return found


def query_one(root: Node, selector: str) -> Node | None:
    nodes = query_all(root, selector)
    return nodes[0] if nodes else None


def _query_group(root: Node, selector: str) -> list[Node]:
    parts = re.split(r"\s*(>|\s+)\s*", selector.strip())
    parts = [p for p in parts if p and p.strip()]
    combinators: list[str] = []
    simples: list[str] = []
    expect = "simple"
    for part in parts:
        if part in {">"}:
            combinators.append(part)
            expect = "simple"
            continue
        if expect == "simple":
            if simples:
                combinators.append(" ")
            simples.append(part)
            expect = "combo"
        else:
            combinators.append(" ")
            simples.append(part)
    if not simples:
        return []
    matches = [n for n in _all_nodes(root) if _match_simple(n, simples[0])]
    for combo, simple in zip(combinators, simples[1:]):
        nxt: list[Node] = []
        seen: set[int] = set()
        for node in matches:
            candidates = node.children if combo == ">" else node.descendants()
            for child in candidates:
                if isinstance(child, Node) and _match_simple(child, simple) and id(child) not in seen:
                    seen.add(id(child))
                    nxt.append(child)
        matches = nxt
    return matches


def _all_nodes(root: Node) -> list[Node]:
    return [root, *root.descendants()]


def _match_simple(node: Node, simple: str) -> bool:
    tag = None
    nid = None
    classes: list[str] = []
    attrs: list[tuple[str, str | None, str | None]] = []
    pos = 0
    for m in _SIMPLE_RE.finditer(simple):
        if m.start() != pos:
            return False
        pos = m.end()
        if m.group(1):
            tag = m.group(1).lower()
        elif m.group(2):
            nid = m.group(2)
        elif m.group(3):
            classes.append(m.group(3))
        else:
            am = _ATTR_RE.match(m.group(4))
            if not am:
                return False
            op = am.group(2)
            val = am.group(3) or am.group(4) or am.group(5)
            if val:
                val = val.strip()
            attrs.append((am.group(1).lower(), op, val))
    if pos != len(simple):
        return False
    if tag and tag != "*" and node.tag != tag:
        return False
    if nid is not None and node.id != nid:
        return False
    if any(cls not in node.classes for cls in classes):
        return False
    for name, op, val in attrs:
        actual = node.attrs.get(name)
        if op is None:
            if actual is None:
                return False
            continue
        if actual is None:
            return False
        if op == "=" and actual != val:
            return False
        if op == "~=" and val not in actual.split():
            return False
        if op == "|=" and actual != val and not actual.startswith(f"{val}-"):
            return False
        if op == "^=" and not actual.startswith(val or ""):
            return False
        if op == "$=" and not actual.endswith(val or ""):
            return False
        if op == "*=" and (val or "") not in actual:
            return False
    return True


def form_fields(form: Node) -> dict[str, str]:
    data: dict[str, str] = {}
    for node in form.descendants():
        if node.tag not in {"input", "textarea", "select"}:
            continue
        name = node.name
        if not name:
            continue
        if node.tag == "input" and node.type in {"submit", "button", "image", "reset", "file"}:
            continue
        if node.tag == "input" and node.type in {"checkbox", "radio"} and "checked" not in node.attrs:
            continue
        if node.tag == "select":
            selected = None
            first = None
            for opt in node.descendants():
                if opt.tag != "option":
                    continue
                if first is None:
                    first = opt.attrs.get("value", opt.inner_text)
                if "selected" in opt.attrs:
                    selected = opt.attrs.get("value", opt.inner_text)
                    break
            data[name] = selected if selected is not None else (first or "")
            continue
        data[name] = node.value
    return data


def form_action(form: Node, base: str) -> tuple[str, str]:
    method = (form.attrs.get("method") or "GET").upper()
    action = form.attrs.get("action") or base
    return method, urljoin(base, action)


def frames_of(root: Node, page_url: str) -> list[dict[str, Any]]:
    out = [{"index": 0, "name": "", "url": page_url, "parentUrl": None, "isMain": True}]
    i = 1
    for node in root.descendants():
        if node.tag != "iframe":
            continue
        src = node.attrs.get("src") or ""
        out.append(
            {
                "index": i,
                "name": node.attrs.get("name") or node.id,
                "url": urljoin(page_url, src) if src else "",
                "parentUrl": page_url,
                "isMain": False,
            }
        )
        i += 1
    return out


def inspect_node(node: Node) -> dict[str, Any]:
    return {
        "tag": node.tag.upper(),
        "id": node.id,
        "name": node.name or None,
        "type": node.type or None,
        "value": node.value,
        "text": node.inner_text[:2000],
        "href": node.href,
        "visible": True,
        "rect": {"x": 0, "y": 0, "width": 0, "height": 0, "top": 0, "right": 0, "bottom": 0, "left": 0},
    }
