# pybroswer

Python browser for **PyDroid**. No Chromium, Playwright, or PC host is required on the phone.

`Browser.launch()` fetches pages with httpx and parses HTML. The same API also works with remote Chromium.

## Install (PyDroid)

```bash
pip install httpx
pip install https://github.com/prateeknishad305/Pybrowser/archive/refs/heads/master.zip
```

If that fails, install httpx first, then:

```bash
pip install git+https://github.com/prateeknishad305/Pybrowser.git
```

Import name:

```python
from pybroswer import Browser
```

`from pybrowser import Browser` also works.

Check:

```python
import pybroswer
print(pybroswer.__version__, pybroswer.__file__)
```

## PyDroid usage

```python
from pybroswer import Browser

with Browser.launch() as browser:
    shot = browser.browse("https://example.com")
    print(shot.title, shot.url, shot.text)

    with browser.create_session(device="mobile") as page:
        page.goto("https://example.com")
        print(page.evaluate("document.title"))
        page.click("a")
        page.type("hello", selector="input[name=q]")
        page.press("Enter")
        print(page.html()[:500])
```

`Browser()` with no URL also starts the local HTTP engine.

## Optional: PC Chromium

If you want real Chromium on a PC:

```bash
pip install "pybroswer[chromium]"
playwright install chromium
python -m pybroswer serve --port 5173
```

From PyDroid:

```python
from pybroswer import Browser
with Browser.connect("http://192.168.1.10:5173") as browser:
    ...
```

In-process on PC: `Browser.launch(engine="chromium")`.

## Limits (phone HTTP engine)

- JS-heavy SPAs are not rendered (you get the HTML the server sent)
- Screenshot is a 1x1 placeholder PNG
- `evaluate` only supports simple `document.title` / `querySelector` expressions
- Iframe contents are not fetched separately
- Click coordinates (`x, y`) require Chromium

Forms, links, type/press/select, cookies, and redirects work.

## API

| Method | |
|--------|--|
| `Browser.launch()` | local HTTP engine (PyDroid default) |
| `Browser.launch(engine="chromium")` | Playwright Chromium (PC) |
| `Browser.connect(url)` | remote REST |
| `browser.browse(url)` | one-shot open |
| `page.goto` / `click` / `type` / `press` / `select` | session actions |
| `page.evaluate("document.title")` | read page |
| `page.html()` / `page.inspect(selector)` | DOM |
