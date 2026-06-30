"""
bestseller_scraper.py
Scrapes Etsy's highest-volume proven-bestseller digital-download categories
via the automation-lab/etsy-scraper Apify actor (RESIDENTIAL proxies).
Output: bestseller_listings.csv  (separate from the existing shop's listings.csv)
"""

import csv
import os
import sys
import time

import requests
from dotenv import load_dotenv

KEYWORDS = [
    "digital planner",
    "budget template",
    "wedding template",
    "wedding invitation template",
    "resume template",
    "instagram template",
    "social media templates",
    "canva template",
    "habit tracker",
    "meal planner",
    "birthday invitation template",
    "business planner",
    "printable wall art",
    "savings tracker",
    "baby shower invitation",
    "menu template",
    "powerpoint template",
    "christmas planner",
]

ACTOR_ID = "automation-lab~etsy-scraper"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
MAX_ITEMS_PER_KEYWORD = 25
OUTPUT_FILE = "bestseller_listings.csv"
CSV_FIELDS = [
    "keyword", "title", "price", "rating", "availability",
    "is_digital_download", "shop_id", "listing_url", "listing_id", "position",
]


def load_api_token():
    load_dotenv()
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        print("[fatal] Missing APIFY_API_TOKEN in .env file.")
        sys.exit(1)
    return token


def normalize_item(item: dict, keyword: str) -> dict:
    return {
        "keyword": keyword,
        "title": item.get("name", ""),
        "price": item.get("price", ""),
        "rating": item.get("rating", ""),
        "availability": item.get("availability", ""),
        "is_digital_download": item.get("isDigitalDownload", ""),
        "shop_id": item.get("shopId", ""),
        "listing_url": item.get("url", ""),
        "listing_id": item.get("listingId", ""),
        "position": item.get("position", ""),
    }


def scrape_keyword(token: str, keyword: str):
    print(f"\n[*] Requesting Apify Actor run for keyword: '{keyword}'")
    payload = {
        "searchQuery": keyword,
        "maxItems": MAX_ITEMS_PER_KEYWORD,
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"],
            "apifyProxyCountry": "US",
        },
    }
    try:
        response = requests.post(
            RUN_SYNC_URL, params={"token": token}, json=payload, timeout=180,
        )
    except requests.RequestException as req_err:
        print(f"  [error] Request failed for '{keyword}': {req_err}")
        return []

    if response.status_code not in (200, 201):
        print(f"  [error] Apify returned status {response.status_code}: {response.text[:300]}")
        return []

    try:
        items = response.json()
    except ValueError:
        print("  [error] Could not parse Apify response as JSON.")
        return []

    print(f"  [+] Received {len(items)} items for '{keyword}'")
    return [normalize_item(item, keyword) for item in items]


def main():
    token = load_api_token()
    print(f"[*] Keywords: {len(KEYWORDS)} | Max/keyword: {MAX_ITEMS_PER_KEYWORD}")
    grand_total = 0
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for idx, keyword in enumerate(KEYWORDS, start=1):
            print(f"\n[Keyword {idx}/{len(KEYWORDS)}]")
            rows = scrape_keyword(token, keyword)
            for row in rows:
                writer.writerow(row)
            csv_file.flush()
            grand_total += len(rows)
            time.sleep(1)
    print(f"\n[done] Total listings captured: {grand_total} -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
