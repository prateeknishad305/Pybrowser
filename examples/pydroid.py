from pybroswer import Browser

with Browser.launch() as browser:
    print(browser.health())
    shot = browser.browse("https://example.com", device="mobile")
    print(shot.title, shot.url)

    with browser.create_session(device="mobile") as page:
        page.goto("https://example.com")
        print(page.evaluate("document.title"))
        page.click("a")
        print(page.html()[:400])
