from pybroswer import Browser

with Browser.launch() as browser:
    health = browser.health()
    print("health", health.ok, health.engine, health.sessions)
    shot = browser.browse("https://example.com", device="desktop")
    print(shot.title, shot.url)
    with browser.create_session(device="desktop") as page:
        page.goto("https://example.com")
        print(page.evaluate("document.title"))
        print(page.frames())
