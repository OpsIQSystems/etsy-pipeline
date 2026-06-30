"""
apify_scraper.py
Replaces scraper.py as the Etsy listings data source. Etsy's bot/CAPTCHA
detection blocks our own Playwright scraper (confirmed via debug_inspect.py)
and also blocked a pay-per-use Apify Actor without residential proxies
(crawlerbros/etsy-scraper). This calls "automation-lab/etsy-scraper" instead,
which uses Apify's RESIDENTIAL proxy pool and got through cleanly in testing.
Pay-per-use pricing, no monthly rental.
Run independently: python apify_scraper.py
Output: listings.csv
"""

import csv
import os
import sys
import time

import requests
from dotenv import load_dotenv

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

ACTOR_ID = "automation-lab~etsy-scraper"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
MAX_ITEMS_PER_KEYWORD = 30
OUTPUT_FILE = "listings.csv"
CSV_FIELDS = [
    "keyword", "title", "price", "rating", "availability",
    "is_digital_download", "shop_id", "listing_url", "listing_id",
]


def load_api_token():
    load_dotenv()
    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        print("[fatal] Missing APIFY_API_TOKEN in .env file.")
        print("        Get one at https://console.apify.com/settings/integrations")
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
            RUN_SYNC_URL,
            params={"token": token},
            json=payload,
            timeout=180,
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
    print("=" * 60)
    print("ETSY COMPETITOR LISTING SCRAPER (via Apify)")
    print("=" * 60)
    token = load_api_token()
    print(f"[*] Keywords to process: {len(KEYWORDS)}")
    print(f"[*] Max items per keyword: {MAX_ITEMS_PER_KEYWORD}")
    print(f"[*] Output file: {OUTPUT_FILE}\n")

    grand_total = 0

    try:
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
                time.sleep(1)  # be polite between Actor calls

    except PermissionError:
        print(f"[fatal] Could not write to {OUTPUT_FILE}. Is it open in another program?")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"[done] Scrape complete. Total listings captured: {grand_total}")
    print(f"[done] Results saved to {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
