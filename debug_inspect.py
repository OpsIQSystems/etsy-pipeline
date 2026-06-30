"""One-off diagnostic: dump Etsy search + listing page HTML for selector debugging."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 900},
    )
    page = context.new_page()

    print("Fetching search page...")
    page.goto("https://www.etsy.com/search?q=maintenance+log", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    with open("debug_search.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("Saved debug_search.html")

    print("Fetching listing page...")
    page.goto(
        "https://www.etsy.com/listing/4528911071/maintenance-log-for-garden-premium",
        wait_until="domcontentloaded", timeout=30000,
    )
    page.wait_for_timeout(2000)
    page.mouse.wheel(0, 2500)
    page.wait_for_timeout(1500)
    with open("debug_listing.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("Saved debug_listing.html")

    browser.close()
