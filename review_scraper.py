"""
FILE 2: review_scraper.py
Reads listings.csv (from scraper.py) and visits each listing page to pull
reviews, flagging ones that mention common complaint language.
Run independently: python review_scraper.py
Output: reviews.csv
"""

import csv
import random
import sys
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

INPUT_FILE = "listings.csv"
OUTPUT_FILE = "reviews.csv"
CSV_FIELDS = ["listing_url", "shop_name", "star_rating", "review_text", "review_date", "flagged", "flag_reasons"]

FLAG_KEYWORDS = [
    "missing", "wrong", "broken", "confusing", "incomplete", "wish",
    "needed", "lacking", "complicated", "manual", "no instructions",
    "doesnt work", "doesn't work", "outdated",
]


def human_delay(min_s=3, max_s=7):
    time.sleep(random.uniform(min_s, max_s))


def load_listing_urls(path: str):
    urls = []
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("listing_url", "").strip()
                shop_name = row.get("shop_name", "").strip()
                if url:
                    urls.append((url, shop_name))
    except FileNotFoundError:
        print(f"[fatal] {path} not found. Run scraper.py first to generate it.")
        sys.exit(1)
    return urls


def flag_review(text: str):
    lowered = text.lower()
    hits = [kw for kw in FLAG_KEYWORDS if kw in lowered]
    return (len(hits) > 0, ", ".join(hits))


def parse_star_rating(rating_tag):
    if not rating_tag:
        return ""
    aria = rating_tag.get("aria-label", "") or rating_tag.get("title", "")
    for token in aria.split():
        try:
            return float(token)
        except ValueError:
            continue
    return ""


def extract_reviews_from_html(html: str):
    soup = BeautifulSoup(html, "html.parser")
    reviews = []

    review_blocks = soup.select("div[data-review-region], li.review, div.review-card")
    if not review_blocks:
        review_blocks = soup.select("[id^='review-']")

    for block in review_blocks:
        try:
            rating_tag = block.select_one("[aria-label*='out of 5 stars'], .stars-svg")
            star_rating = parse_star_rating(rating_tag)

            text_tag = block.select_one("p[id^='review-preview'], p.wt-text-truncate, p")
            review_text = text_tag.get_text(strip=True) if text_tag else ""
            if not review_text:
                continue

            date_tag = block.select_one("p.wt-text-caption, span.wt-text-caption")
            review_date = date_tag.get_text(strip=True) if date_tag else ""

            flagged, flag_reasons = flag_review(review_text)

            reviews.append({
                "star_rating": star_rating,
                "review_text": review_text,
                "review_date": review_date,
                "flagged": flagged,
                "flag_reasons": flag_reasons,
            })
        except Exception as item_err:
            print(f"    [warn] skipped a review block: {item_err}")
            continue

    return reviews


def scrape_listing_reviews(page, url: str):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except PlaywrightTimeoutError:
        print(f"    [error] Timed out loading {url}")
        return []
    except Exception as nav_err:
        print(f"    [error] Navigation failed for {url}: {nav_err}")
        return []

    human_delay(2, 4)

    # Reviews are sometimes lazy-loaded; scroll down a bit to trigger loading.
    try:
        page.mouse.wheel(0, 1800)
        human_delay(1, 2)
    except Exception:
        pass

    try:
        html = page.content()
    except Exception as content_err:
        print(f"    [error] Could not read page content for {url}: {content_err}")
        return []

    return extract_reviews_from_html(html)


def main():
    print("=" * 60)
    print("ETSY REVIEW SCRAPER")
    print("=" * 60)

    listing_urls = load_listing_urls(INPUT_FILE)
    print(f"[*] Loaded {len(listing_urls)} listing URLs from {INPUT_FILE}\n")

    if not listing_urls:
        print("[done] Nothing to scrape, listings.csv was empty.")
        return

    total_reviews = 0
    total_flagged = 0

    try:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
            writer.writeheader()

            with sync_playwright() as p:
                print("[*] Launching headless Chromium...")
                browser = p.chromium.launch(headless=True, channel="msedge")
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1366, "height": 900},
                )
                page = context.new_page()

                for idx, (url, shop_name) in enumerate(listing_urls, start=1):
                    print(f"[Listing {idx}/{len(listing_urls)}] {url}")
                    reviews = scrape_listing_reviews(page, url)

                    for r in reviews:
                        r["listing_url"] = url
                        r["shop_name"] = shop_name
                        writer.writerow(r)
                        total_reviews += 1
                        if r["flagged"]:
                            total_flagged += 1
                    csv_file.flush()

                    print(f"    [+] Captured {len(reviews)} reviews ({sum(1 for r in reviews if r['flagged'])} flagged)")
                    human_delay(3, 7)

                browser.close()

    except PermissionError:
        print(f"[fatal] Could not write to {OUTPUT_FILE}. Is it open in another program?")
        sys.exit(1)
    except Exception as fatal_err:
        print(f"[fatal] Unexpected error: {fatal_err}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"[done] Total reviews captured: {total_reviews}")
    print(f"[done] Total flagged (pain-point) reviews: {total_flagged}")
    print(f"[done] Results saved to {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
