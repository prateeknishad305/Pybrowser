from pybroswer import Browser

with Browser.launch() as browser:
    shot = browser.browse("https://example.com", device="desktop")
    print(shot.title, shot.url, shot.status)
    with browser.create_session(device="desktop") as page:
        page.goto("https://example.com")
        print(page.evaluate("document.title"))
