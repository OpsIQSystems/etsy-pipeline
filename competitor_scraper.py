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

# Reddit OAuth2 credentials — set these in Railway env vars
# Create a free "script" app at https://www.reddit.com/prefs/apps
REDDIT_CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME      = os.environ.get("REDDIT_USERNAME", "")
REDDIT_PASSWORD      = os.environ.get("REDDIT_PASSWORD", "")
# Unique User-Agent required by Reddit API TOS
_REDDIT_UA = "EtsyPipeline/1.0 by u/OpsIQSystems"

# ---------------------------------------------------------------------------
# Reddit — OAuth2 API (free, 100 req/min, no CAPTCHA)
# ---------------------------------------------------------------------------

TRADE_SUBREDDITS = [
    "HVAC", "plumbing", "electricians", "Roofing", "Construction",
    "Contractor", "smallbusiness", "Entrepreneur",
]

_reddit_token: dict = {}  # cache: {"access_token": "...", "expires_at": timestamp}


def _get_reddit_token() -> str:
    """Get or refresh Reddit OAuth2 access token."""
    import time as _time
    now = _time.time()
    if _reddit_token.get("access_token") and now < _reddit_token.get("expires_at", 0) - 60:
        return _reddit_token["access_token"]

    if not REDDIT_CLIENT_ID:
        return ""

    auth = requests.auth.HTTPBasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
    data = {"grant_type": "password", "username": REDDIT_USERNAME, "password": REDDIT_PASSWORD}
    r = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=auth, data=data,
        headers={"User-Agent": _REDDIT_UA},
        timeout=15,
    )
    if r.status_code == 200:
        tok = r.json()
        _reddit_token["access_token"] = tok["access_token"]
        _reddit_token["expires_at"] = now + tok.get("expires_in", 3600)
        return tok["access_token"]
    print(f"[reddit] token error: {r.status_code} {r.text[:200]}")
    return ""


def scrape_reddit(subreddits: list[str] | None = None, limit: int = 25, sort: str = "hot") -> list[dict]:
    """
    Fetch top posts from trade subreddits.
    Prefers OAuth2 API if creds set; falls back to Playwright (real browser).
    """
    subs = subreddits or TRADE_SUBREDDITS

    # Try OAuth2 first (fastest, if creds are configured)
    token = _get_reddit_token()
    if token:
        results = []
        headers = {"Authorization": f"bearer {token}", "User-Agent": _REDDIT_UA}
        for sub in subs:
            url = f"https://oauth.reddit.com/r/{sub}/{sort}.json?limit={limit}&raw_json=1"
            try:
                r = requests.get(url, headers=headers, timeout=15)
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
                time.sleep(random.uniform(0.3, 0.8))
            except Exception as e:
                print(f"[reddit] r/{sub}: {e}")
        return results

    # Fallback: Playwright real browser (no credentials needed)
    return _scrape_reddit_playwright(subs, limit, sort)


def _scrape_reddit_playwright(subs: list[str], limit: int, sort: str) -> list[dict]:
    """Scrape Reddit using a real Playwright browser — bypasses API auth requirement."""
    from playwright.sync_api import sync_playwright
    import json as _json

    results = []
    with sync_playwright() as p:
        browser, ctx = _new_browser_context(p)
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        for sub in subs:
            url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit={limit}&raw_json=1"
            try:
                # Use route to fetch JSON directly (avoids HTML rendering overhead)
                response = page.request.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"}
                )
                if response.status == 200:
                    data = response.json()
                    for p_item in data.get("data", {}).get("children", []):
                        d = p_item.get("data", {})
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
                    print(f"[reddit] r/{sub}: {len(data.get('data',{}).get('children',[]))} posts")
                else:
                    print(f"[reddit] r/{sub}: HTTP {response.status}")
                time.sleep(random.uniform(0.5, 1.0))
            except Exception as e:
                print(f"[reddit] r/{sub}: {e}")

        browser.close()
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
    Scrape a competitor Etsy shop: listings + reviews.
    Uses Playwright page.evaluate() to query the live React-rendered DOM.
    """
    from playwright.sync_api import sync_playwright

    shop_name = shop_url.rstrip("/").split("/shop/")[-1].split("/")[0]
    result = {"shop": shop_name, "listings": [], "reviews": [], "stats": {}}

    with sync_playwright() as p:
        browser, ctx = _new_browser_context(p)
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")

        # --- Listings ---
        try:
            page.goto(f"https://www.etsy.com/shop/{shop_name}", timeout=35000)
            _solve_cloudflare(page)
            # Wait for listing cards to render
            try:
                page.wait_for_selector("[data-listing-id], .v2-listing-card", timeout=10000)
            except Exception:
                page.wait_for_timeout(4000)

            data = page.evaluate(f"""
                () => {{
                    const out = {{ stats: {{}}, listings: [] }};

                    // Sales / rating stats from header
                    document.querySelectorAll('span, p, div').forEach(el => {{
                        const t = el.innerText || '';
                        if (/\\d[,\\d]* sales/i.test(t) && t.length < 60)
                            out.stats.sales_text = t.trim();
                    }});

                    // Listing cards
                    const cards = document.querySelectorAll('[data-listing-id]');
                    cards.forEach(card => {{
                        if (out.listings.length >= {max_listings}) return;
                        const title = card.querySelector('h3, [class*="title"]')?.innerText?.trim() || '';
                        const price = card.querySelector('[class*="currency"], [class*="price"]')?.innerText?.trim() || '';
                        const link  = card.querySelector('a[href*="/listing/"]')?.href || '';
                        const rating = card.querySelector('[aria-label*="star"], [title*="star"]')
                                          ?.getAttribute('aria-label') || '';
                        if (title) out.listings.push({{ title, price, url: link.split('?')[0], rating }});
                    }});
                    return out;
                }}
            """)
            result["stats"]    = data.get("stats", {})
            result["listings"] = data.get("listings", [])
            print(f"[etsy] {shop_name} listings: {len(result['listings'])}")
        except Exception as e:
            print(f"[etsy] listings {shop_name}: {e}")

        # --- Reviews ---
        try:
            page.goto(f"https://www.etsy.com/shop/{shop_name}/reviews", timeout=35000)
            _solve_cloudflare(page)
            try:
                page.wait_for_selector("[data-review-region], [class*='review']", timeout=10000)
            except Exception:
                page.wait_for_timeout(4000)

            reviews = page.evaluate(f"""
                () => {{
                    const out = [];
                    // Try multiple selectors Etsy uses for reviews
                    const containers = document.querySelectorAll(
                        '[data-review-region], [class*="ReviewsList"] > *, .review-cart'
                    );
                    containers.forEach(el => {{
                        if (out.length >= {max_reviews}) return;
                        // Review body text
                        const body = el.querySelector(
                            'p[class*="body"], [class*="review-text"], p'
                        )?.innerText?.trim() || '';
                        // Stars from aria-label
                        const starEl = el.querySelector('[aria-label*="out of"], [aria-label*="star"]');
                        const stars = starEl?.getAttribute('aria-label')?.match(/\\d/)?.[0] || '';
                        // Linked product
                        const itemEl = el.querySelector('a[href*="/listing/"]');
                        const item = itemEl?.innerText?.trim() || '';
                        const itemUrl = itemEl?.href?.split('?')[0] || '';
                        if (body.length > 10)
                            out.push({{ stars, text: body.slice(0, 400), item, item_url: itemUrl }});
                    }});

                    // Fallback: grab all <p> tags that look like review text
                    if (out.length === 0) {{
                        document.querySelectorAll('p').forEach(p => {{
                            if (out.length >= {max_reviews}) return;
                            const t = p.innerText?.trim() || '';
                            if (t.length > 30 && t.length < 600 && !t.includes('{{'))
                                out.push({{ stars: '', text: t.slice(0, 400), item: '', item_url: '' }});
                        }});
                    }}
                    return out;
                }}
            """)
            result["reviews"] = reviews or []
            print(f"[etsy] {shop_name} reviews: {len(result['reviews'])}")
        except Exception as e:
            print(f"[etsy] reviews {shop_name}: {e}")

        browser.close()

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
