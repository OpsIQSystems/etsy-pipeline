"""
competitor_scraper.py
Replaces Apify actors for Reddit, TikTok, and Etsy competitor scraping.

Uses:
  - Reddit JSON API  — free, no auth, no CAPTCHA
  - Playwright + CapSolver — handles Cloudflare Turnstile / hCaptcha for TikTok & Etsy

Set env var CAPSOLVER_API_KEY to enable CAPTCHA solving (optional — Playwright
alone handles most pages without hitting a CAPTCHA).
"""

import json
import os
import random
import time

import requests

CAPSOLVER_KEY = os.environ.get("CAPSOLVER_API_KEY", "")

# ---------------------------------------------------------------------------
# Reddit — public JSON API, zero cost, zero CAPTCHA
# ---------------------------------------------------------------------------

_REDDIT_UA = "Mozilla/5.0 (compatible; EtsyPipeline/1.0)"

TRADE_SUBREDDITS = [
    "HVAC", "plumbing", "electricians", "Roofing", "Construction",
    "Contractor", "smallbusiness", "Entrepreneur",
]


def scrape_reddit(subreddits: list[str] | None = None, limit: int = 25, sort: str = "hot") -> list[dict]:
    """Fetch top posts from trade subreddits via Reddit JSON API."""
    subs = subreddits or TRADE_SUBREDDITS
    results = []
    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit={limit}"
        try:
            r = requests.get(url, headers={"User-Agent": _REDDIT_UA}, timeout=15)
            if r.status_code == 200:
                for p in r.json().get("data", {}).get("children", []):
                    d = p.get("data", {})
                    results.append({
                        "source": "reddit",
                        "subreddit": sub,
                        "title": d.get("title", ""),
                        "score": d.get("score", 0),
                        "comments": d.get("num_comments", 0),
                        "upvote_ratio": d.get("upvote_ratio", 0),
                        "flair": d.get("link_flair_text", ""),
                        "text": d.get("selftext", "")[:500],
                        "url": f"https://reddit.com{d.get('permalink', '')}",
                        "created_utc": d.get("created_utc", 0),
                    })
            time.sleep(random.uniform(0.5, 1.2))
        except Exception as e:
            print(f"[reddit] r/{sub}: {e}")
    return results


# ---------------------------------------------------------------------------
# CapSolver — called only when a CAPTCHA is detected on page
# ---------------------------------------------------------------------------

def _solve_cloudflare(page) -> bool:
    """Detect Cloudflare Turnstile and solve it via CapSolver API. Returns True if solved."""
    if not CAPSOLVER_KEY:
        return False
    try:
        has_cf = page.evaluate("""
            () => !!document.querySelector(
                'iframe[src*="challenges.cloudflare.com"], [data-ray-id]'
            )
        """)
        if not has_cf:
            return False

        # Extract sitekey from page
        site_key = page.evaluate("""
            () => {
                const el = document.querySelector('[data-sitekey]');
                return el ? el.getAttribute('data-sitekey') : '0x4AAAAAAAC3IhnrYSXfzwTw';
            }
        """)

        resp = requests.post("https://api.capsolver.com/createTask", json={
            "clientKey": CAPSOLVER_KEY,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": page.url,
                "websiteKey": site_key,
            }
        }, timeout=30)
        task_id = resp.json().get("taskId")
        if not task_id:
            return False

        for _ in range(30):
            time.sleep(2)
            res = requests.post("https://api.capsolver.com/getTaskResult", json={
                "clientKey": CAPSOLVER_KEY,
                "taskId": task_id,
            }, timeout=15).json()
            if res.get("status") == "ready":
                token = res["solution"]["token"]
                page.evaluate("""
                    (tok) => {
                        const inp = document.querySelector(
                            '[name="cf-turnstile-response"],[name="g-recaptcha-response"]'
                        );
                        if (inp) inp.value = tok;
                        const form = document.querySelector('form');
                        if (form) form.submit();
                    }
                """, token)
                page.wait_for_load_state("networkidle", timeout=15000)
                print("[capsolver] Cloudflare solved ✓")
                return True
    except Exception as e:
        print(f"[capsolver] {e}")
    return False


def _new_browser_context(playwright):
    """Launch a stealthy Chromium context."""
    browser = playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
        ]
    )
    ctx = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )
    return browser, ctx


# ---------------------------------------------------------------------------
# TikTok — Playwright + optional CapSolver
# ---------------------------------------------------------------------------

TIKTOK_HASHTAGS = [
    "hvaclife", "plumberlife", "electricianlife", "constructionlife",
    "contractorlife", "tradeslife", "tradesman", "smallbusiness",
]


def scrape_tiktok(hashtags: list[str] | None = None, limit: int = 20) -> list[dict]:
    """Scrape TikTok trending videos by hashtag."""
    from playwright.sync_api import sync_playwright
    tags = hashtags or TIKTOK_HASHTAGS
    results = []

    with sync_playwright() as p:
        browser, ctx = _new_browser_context(p)
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        for tag in tags:
            try:
                page.goto(f"https://www.tiktok.com/tag/{tag}", timeout=30000)
                _solve_cloudflare(page)
                page.wait_for_timeout(random.randint(2500, 4000))

                videos = page.evaluate("""
                    () => {
                        const out = [];
                        document.querySelectorAll(
                            '[data-e2e="challenge-item"], .css-1as5cen-DivWrapper'
                        ).forEach(el => {
                            const a = el.querySelector('a[href*="/video/"]');
                            const views = el.querySelector('[data-e2e="video-views"]');
                            const desc = el.querySelector('[data-e2e="video-desc"]');
                            out.push({
                                url: a ? a.href : '',
                                views: views ? views.innerText.trim() : '',
                                description: desc ? desc.innerText.trim() : '',
                            });
                        });
                        return out;
                    }
                """) or []

                for v in videos[:limit]:
                    if v.get("url"):
                        results.append({
                            "source": "tiktok",
                            "hashtag": tag,
                            "url": v["url"],
                            "views": v.get("views", ""),
                            "description": v.get("description", ""),
                        })
                print(f"[tiktok] #{tag}: {len(videos)} videos")
                time.sleep(random.uniform(2, 4))
            except Exception as e:
                print(f"[tiktok] #{tag}: {e}")

        browser.close()
    return results


# ---------------------------------------------------------------------------
# Etsy competitor shop — listings + reviews
# ---------------------------------------------------------------------------

def scrape_etsy_competitor(shop_url: str, max_listings: int = 20, max_reviews: int = 30) -> dict:
    """
    Scrape a competitor Etsy shop: their listings and recent reviews.
    shop_url: https://www.etsy.com/shop/ShopName
    """
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup

    shop_name = shop_url.rstrip("/").split("/shop/")[-1].split("/")[0]
    result = {"shop": shop_name, "listings": [], "reviews": [], "stats": {}}

    with sync_playwright() as p:
        browser, ctx = _new_browser_context(p)
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        # Listings
        try:
            page.goto(f"https://www.etsy.com/shop/{shop_name}", timeout=30000)
            _solve_cloudflare(page)
            page.wait_for_timeout(random.randint(2000, 3500))
            soup = BeautifulSoup(page.content(), "html.parser")

            # Sales count from page header
            for el in soup.select(".wt-text-body-02, .shop-home-header-stats"):
                txt = el.get_text(strip=True)
                if "sale" in txt.lower():
                    result["stats"]["sales_text"] = txt[:100]
                    break

            # Listing cards
            for card in soup.select("li[data-listing-id], li.wt-list-unstyled")[:max_listings]:
                title_el = card.select_one("h3, .v2-listing-card__title, [data-listing-id] h3")
                price_el = card.select_one(".currency-value, .wt-text-title-01")
                link_el = card.select_one("a[href*='/listing/']")
                reviews_el = card.select_one(".wt-text-caption, [title*='star']")
                if title_el:
                    result["listings"].append({
                        "title": title_el.get_text(strip=True),
                        "price": price_el.get_text(strip=True) if price_el else "",
                        "url": link_el["href"].split("?")[0] if link_el else "",
                        "rating_snippet": reviews_el.get_text(strip=True) if reviews_el else "",
                    })
        except Exception as e:
            print(f"[etsy] listings for {shop_name}: {e}")

        # Reviews
        try:
            page.goto(f"https://www.etsy.com/shop/{shop_name}/reviews", timeout=30000)
            _solve_cloudflare(page)
            page.wait_for_timeout(random.randint(2000, 3500))
            soup = BeautifulSoup(page.content(), "html.parser")

            for review in soup.select(".wt-grid__item-xs-12 .wt-display-flex-xs, [data-review-region]")[:max_reviews]:
                stars_el = review.select_one("[aria-label*='star'], .wt-star-rating, [class*='star']")
                body_el = review.select_one(
                    "p.wt-text-body-01, .wt-content-toggle__body, [data-review-text]"
                )
                item_el = review.select_one("a[href*='/listing/']")
                text = body_el.get_text(strip=True) if body_el else ""
                if text:
                    result["reviews"].append({
                        "stars": (stars_el.get("aria-label", "") or "").split(" ")[0] if stars_el else "",
                        "text": text[:400],
                        "item": item_el.get_text(strip=True) if item_el else "",
                        "item_url": item_el["href"].split("?")[0] if item_el else "",
                    })
        except Exception as e:
            print(f"[etsy] reviews for {shop_name}: {e}")

        browser.close()

    print(f"[etsy] {shop_name}: {len(result['listings'])} listings, {len(result['reviews'])} reviews")
    return result


# ---------------------------------------------------------------------------
# Combined runner — called by /scrape API endpoint
# ---------------------------------------------------------------------------

def run_all(config: dict) -> dict:
    """
    Run scrapers based on config dict. All keys optional.

    Keys:
      reddit_subreddits  list[str]   — defaults to TRADE_SUBREDDITS
      reddit_limit       int         — posts per subreddit (default 25)
      reddit_sort        str         — "hot"|"new"|"top" (default "hot")
      tiktok_hashtags    list[str]   — defaults to TIKTOK_HASHTAGS
      tiktok_limit       int         — videos per hashtag (default 20)
      etsy_competitors   list[str]   — list of shop URLs to scrape
      skip_reddit        bool        — set True to skip Reddit
      skip_tiktok        bool        — set True to skip TikTok
    """
    results: dict = {}

    if not config.get("skip_reddit"):
        results["reddit"] = scrape_reddit(
            subreddits=config.get("reddit_subreddits"),
            limit=config.get("reddit_limit", 25),
            sort=config.get("reddit_sort", "hot"),
        )
        print(f"[scraper] Reddit total: {len(results['reddit'])} posts")

    if not config.get("skip_tiktok"):
        results["tiktok"] = scrape_tiktok(
            hashtags=config.get("tiktok_hashtags"),
            limit=config.get("tiktok_limit", 20),
        )
        print(f"[scraper] TikTok total: {len(results['tiktok'])} videos")

    if config.get("etsy_competitors"):
        results["etsy_competitors"] = []
        for shop_url in config["etsy_competitors"]:
            data = scrape_etsy_competitor(shop_url)
            results["etsy_competitors"].append(data)

    return results


if __name__ == "__main__":
    import sys
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    out = run_all(cfg)
    print(json.dumps(out, indent=2, default=str))
