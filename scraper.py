"""
FILE 1: scraper.py
Scrapes Etsy search results for competitor listings across a fixed keyword set.
Run independently: python scraper.py
Output: listings.csv
"""

import csv
import random
import re
import sys
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

KEYWORDS = [
    "property management template",
    "landlord tracker",
    "maintenance log",
    "tenant checklist",
    "rental spreadsheet",
    "work order template",
    "rent tracker google sheets",
    "field service business dashboard",
    "crew profit tracker",
    "technician scorecard",
    "HVAC business spreadsheet",
    "landscaping KPI tracker",
    "service business dashboard",
    "small business operations template",
    "job cost calculator",
    "route profitability tracker",
    "crew performance dashboard",
    "technician KPI tracker",
    "field ops scorecard",
    "service company profit tracker",
    "contractor business dashboard",
    "equipment maintenance tracker",
]

PAGES_PER_KEYWORD = 5
OUTPUT_FILE = "listings.csv"
CSV_FIELDS = [
    "keyword", "page", "title", "price", "review_count", "tags",
    "shop_name", "listing_url", "description_snippet", "sales_estimate",
]


def human_delay(min_s=3, max_s=7):
    """Random human-like pause between page actions."""
    delay = random.uniform(min_s, max_s)
    time.sleep(delay)


def build_search_url(keyword: str, page: int) -> str:
    q = quote_plus(keyword)
    if page <= 1:
        return f"https://www.etsy.com/search?q={q}"
    return f"https://www.etsy.com/search?q={q}&page={page}"


def parse_sales_estimate(text: str):
    """Etsy shows things like '1,234 sales' near shop name on some listing cards."""
    if not text:
        return ""
    match = re.search(r"([\d,]+)\s+sales", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(",", "")
    return ""


def parse_review_count(text: str):
    if not text:
        return ""
    match = re.search(r"([\d,]+)", text)
    if match:
        return match.group(1).replace(",", "")
    return ""


def extract_listings_from_html(html: str, keyword: str, page: int):
    """Parse an Etsy search results page into listing dicts."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    cards = soup.select("div.v2-listing-card, li.wt-list-unstyled div[data-listing-id]")
    if not cards:
        # Fallback: any anchor pointing at a listing page
        cards = soup.select("a[href*='/listing/']")

    seen_urls = set()
    for card in cards:
        try:
            link_tag = card if card.name == "a" else card.select_one("a[href*='/listing/']")
            if not link_tag or not link_tag.get("href"):
                continue
            listing_url = link_tag["href"].split("?")[0]
            if listing_url in seen_urls:
                continue
            seen_urls.add(listing_url)

            title_tag = card.select_one("h3, [data-listing-card-title]") or link_tag
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                title = link_tag.get("title", "").strip()

            price_tag = card.select_one(".currency-value, .wt-text-title-larger")
            price = price_tag.get_text(strip=True) if price_tag else ""

            review_tag = card.select_one(".wt-text-caption, [aria-label*='reviews']")
            review_count = parse_review_count(review_tag.get_text(strip=True) if review_tag else "")

            shop_tag = card.select_one(".wt-text-caption.wt-display-inline-block, .text-gray, [data-shop-name]")
            shop_name = shop_tag.get_text(strip=True) if shop_tag else ""

            desc_tag = card.select_one("p")
            description_snippet = desc_tag.get_text(strip=True)[:200] if desc_tag else ""

            sales_estimate = parse_sales_estimate(card.get_text(" ", strip=True))

            tag_candidates = card.select("[data-tag], .tag")
            tags = ", ".join(t.get_text(strip=True) for t in tag_candidates) if tag_candidates else ""

            results.append({
                "keyword": keyword,
                "page": page,
                "title": title,
                "price": price,
                "review_count": review_count,
                "tags": tags,
                "shop_name": shop_name,
                "listing_url": listing_url,
                "description_snippet": description_snippet,
                "sales_estimate": sales_estimate,
            })
        except Exception as item_err:
            print(f"    [warn] skipped a card due to parse error: {item_err}")
            continue

    return results


def scrape_keyword(page, keyword: str, writer, csv_file):
    print(f"\n[*] Searching keyword: '{keyword}'")
    total_for_keyword = 0

    for page_num in range(1, PAGES_PER_KEYWORD + 1):
        url = build_search_url(keyword, page_num)
        print(f"  [-] Page {page_num}/{PAGES_PER_KEYWORD} -> {url}")

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightTimeoutError:
            print(f"    [error] Timed out loading page {page_num} for '{keyword}', skipping.")
            continue
        except Exception as nav_err:
            print(f"    [error] Navigation failed: {nav_err}")
            continue

        human_delay(2, 4)  # let dynamic content settle

        try:
            html = page.content()
        except Exception as content_err:
            print(f"    [error] Could not read page content: {content_err}")
            continue

        listings = extract_listings_from_html(html, keyword, page_num)
        if not listings:
            print(f"    [warn] No listings parsed on page {page_num}. Etsy may have changed markup or blocked the request.")

        for listing in listings:
            writer.writerow(listing)
        csv_file.flush()

        total_for_keyword += len(listings)
        print(f"    [+] Extracted {len(listings)} listings (running total for keyword: {total_for_keyword})")

        human_delay(3, 7)  # human-like delay between page actions

    return total_for_keyword


def main():
    print("=" * 60)
    print("ETSY COMPETITOR LISTING SCRAPER")
    print("=" * 60)
    print(f"[*] Keywords to process: {len(KEYWORDS)}")
    print(f"[*] Pages per keyword: {PAGES_PER_KEYWORD}")
    print(f"[*] Output file: {OUTPUT_FILE}\n")

    grand_total = 0

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

                for idx, keyword in enumerate(KEYWORDS, start=1):
                    print(f"\n[Keyword {idx}/{len(KEYWORDS)}]")
                    try:
                        count = scrape_keyword(page, keyword, writer, csv_file)
                        grand_total += count
                    except Exception as kw_err:
                        print(f"  [error] Failed on keyword '{keyword}': {kw_err}")
                        continue

                    human_delay(4, 8)  # extra pause between keywords

                browser.close()

    except PermissionError:
        print(f"[fatal] Could not write to {OUTPUT_FILE}. Is it open in another program?")
        sys.exit(1)
    except Exception as fatal_err:
        print(f"[fatal] Unexpected error: {fatal_err}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"[done] Scrape complete. Total listings captured: {grand_total}")
    print(f"[done] Results saved to {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
