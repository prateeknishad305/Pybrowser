from __future__ import annotations

import httpx

from pybroswer import Browser
from pybroswer.dom import parse_html, query_one
from pybroswer.http_engine import HttpEngine


HTML_HOME = """
<html>
  <head><title>Home</title></head>
  <body>
    <h1>Hello</h1>
    <a id="go" href="/next">Next</a>
    <form id="search" action="/find" method="GET">
      <input name="q" id="q" />
      <button type="submit" id="ok">Go</button>
    </form>
    <select name="country" id="country">
      <option value="US">United States</option>
      <option value="IN">India</option>
    </select>
    <iframe name="stripe_checkout" src="/frame"></iframe>
  </body>
</html>
"""

HTML_NEXT = "<html><head><title>Next</title></head><body><p>arrived</p></body></html>"
HTML_FIND = "<html><head><title>Find</title></head><body><p>q=hello</p></body></html>"


def _client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in {"/", "/home"}:
            return httpx.Response(200, text=HTML_HOME, headers={"content-type": "text/html"})
        if path == "/next":
            return httpx.Response(200, text=HTML_NEXT, headers={"content-type": "text/html"})
        if path == "/find":
            return httpx.Response(200, text=HTML_FIND, headers={"content-type": "text/html"})
        return httpx.Response(404, text="nope")

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.com", follow_redirects=True)


def test_dom_query():
    root = parse_html(HTML_HOME)
    assert query_one(root, "h1").inner_text == "Hello"
    assert query_one(root, "#go").href == "/next"
    assert query_one(root, "input[name=q]") is not None
    assert query_one(root, "a#go") is not None


def test_launch_http_engine_browse_and_click():
    engine = HttpEngine(client=_client())
    with Browser(engine=engine) as browser:
        health = browser.health()
        assert health.ok and health.engine == "http"
        shot = browser.browse("https://example.com/")
        assert shot.title == "Home"
        assert "Hello" in shot.text
        page = browser.session(shot.session_id)
        clicked = page.click("#go")
        assert clicked.title == "Next"
        assert page.evaluate("document.title") == "Next"


def test_type_press_select_inspect():
    engine = HttpEngine(client=_client())
    with Browser(engine=engine) as browser:
        with browser.create_session() as page:
            page.goto("https://example.com/")
            page.type("hello", selector="#q")
            info = page.inspect("#q")
            assert info.value == "hello"
            page.press("Enter", selector="#q")
            assert page.evaluate("document.title") == "Find"
            page.goto("https://example.com/")
            selected = page.select("#country", value="IN")
            assert selected.selected == ["IN"]
            frames = page.frames()
            assert frames[0].is_main
            assert any(f.name == "stripe_checkout" for f in frames)


def test_browser_launch_default_is_http():
    browser = Browser.launch()
    try:
        health = browser.health()
        assert health.engine == "http"
        assert health.ok
    finally:
        browser.close()
