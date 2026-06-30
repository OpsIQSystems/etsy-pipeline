"""
FILE 6: lister.py
Reads /products and /listings, shows each product + listing copy for human
review, and ONLY on explicit y/n approval pushes the listing to Etsy via the
official Etsy Open API v3. Never auto-posts.
Run independently: python lister.py
Output: posted_listings.csv (append log)
"""

import csv
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

PRODUCTS_DIR = "products"
LISTINGS_DIR = "listings"
LOG_FILE = "posted_listings.csv"
LOG_FIELDS = ["timestamp", "product_name", "listing_id", "listing_url", "status"]

ETSY_API_BASE = "https://api.etsy.com/v3/application"


def load_etsy_credentials():
    load_dotenv()
    api_key = os.getenv("ETSY_API_KEY")
    shop_id = os.getenv("ETSY_SHOP_ID")
    if not api_key or not shop_id:
        print("[fatal] Missing ETSY_API_KEY or ETSY_SHOP_ID in .env file.")
        print("        Create an app and get keys at https://www.etsy.com/developers/your-account")
        sys.exit(1)
    return api_key, shop_id


def parse_listing_txt(path: str) -> dict:
    """Parse the .txt listing copy produced by creator.py back into fields."""
    data = {"title": "", "price": "", "description": "", "tags": []}
    section = None
    desc_lines = []

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("TITLE:"):
                section = "title"
                continue
            if stripped.startswith("PRICE:"):
                data["price"] = stripped.replace("PRICE:", "").replace("$", "").strip()
                section = None
                continue
            if stripped.startswith("DESCRIPTION:"):
                section = "description"
                continue
            if stripped.startswith("TAGS:"):
                section = "tags"
                continue
            if stripped.startswith("TARGET CUSTOMER:") or stripped.startswith("OPPORTUNITY SCORE:"):
                section = None
                continue

            if section == "title" and stripped:
                data["title"] = stripped
                section = None
            elif section == "description":
                desc_lines.append(line.rstrip("\n"))
            elif section == "tags" and stripped.startswith("-"):
                data["tags"].append(stripped.lstrip("- ").strip())

    data["description"] = "\n".join(desc_lines).strip()
    return data


def find_product_pairs():
    """Match each listing .txt with its corresponding product files in /products."""
    pairs = []
    if not os.path.isdir(LISTINGS_DIR):
        return pairs

    for fname in sorted(os.listdir(LISTINGS_DIR)):
        if not fname.endswith(".txt"):
            continue
        base = fname[:-4]
        listing_path = os.path.join(LISTINGS_DIR, fname)
        xlsx_path = os.path.join(PRODUCTS_DIR, f"{base}.xlsx")
        pdf_path = os.path.join(PRODUCTS_DIR, f"{base}_guide.pdf")
        pairs.append({
            "name": base,
            "listing_txt": listing_path,
            "xlsx": xlsx_path if os.path.exists(xlsx_path) else None,
            "pdf": pdf_path if os.path.exists(pdf_path) else None,
        })
    return pairs


def display_for_review(name: str, listing_data: dict, xlsx_path, pdf_path):
    print("\n" + "-" * 60)
    print(f"PRODUCT: {name}")
    print("-" * 60)
    print(f"Workbook file: {xlsx_path or '[missing]'}")
    print(f"PDF guide file: {pdf_path or '[missing]'}")
    print(f"\nTitle: {listing_data['title']}")
    print(f"Price: ${listing_data['price']}")
    print(f"Tags ({len(listing_data['tags'])}): {', '.join(listing_data['tags'])}")
    print(f"\nDescription:\n{listing_data['description'][:1000]}")
    if len(listing_data["description"]) > 1000:
        print("...[truncated for display]...")
    print("-" * 60)


def post_to_etsy(api_key: str, shop_id: str, listing_data: dict):
    """Create a draft listing on Etsy via the official Open API v3."""
    url = f"{ETSY_API_BASE}/shops/{shop_id}/listings"
    headers = {"x-api-key": api_key}

    try:
        price_value = float(listing_data["price"]) if listing_data["price"] else 29.0
    except ValueError:
        price_value = 29.0

    payload = {
        "quantity": 999,
        "title": listing_data["title"][:140],
        "description": listing_data["description"],
        "price": price_value,
        "who_made": "i_did",
        "when_made": "made_to_order",
        "taxonomy_id": 0,
        "tags": listing_data["tags"][:13],
        "is_digital": True,
        "type": "download",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as req_err:
        print(f"  [error] Etsy API request failed: {req_err}")
        return None


def append_log(row: dict):
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def main():
    print("=" * 60)
    print("ETSY LISTER (human-approval required, official Etsy API)")
    print("=" * 60)

    api_key, shop_id = load_etsy_credentials()
    pairs = find_product_pairs()

    if not pairs:
        print(f"[done] No listing files found in /{LISTINGS_DIR}. Run creator.py first.")
        return

    print(f"[*] Found {len(pairs)} product(s) to review.\n")

    posted = 0
    skipped = 0

    for pair in pairs:
        try:
            listing_data = parse_listing_txt(pair["listing_txt"])
        except Exception as parse_err:
            print(f"[error] Could not parse {pair['listing_txt']}: {parse_err}")
            continue

        display_for_review(pair["name"], listing_data, pair["xlsx"], pair["pdf"])

        answer = input("\nPost this listing to Etsy? [y/n]: ").strip().lower()
        if answer != "y":
            print("  [-] Skipped (no approval given).")
            skipped += 1
            append_log({
                "timestamp": datetime.now().isoformat(),
                "product_name": pair["name"],
                "listing_id": "",
                "listing_url": "",
                "status": "skipped",
            })
            continue

        print("  [-] Approved. Posting to Etsy via official API...")
        result = post_to_etsy(api_key, shop_id, listing_data)

        if result and "listing_id" in result:
            listing_id = result["listing_id"]
            listing_url = result.get("url", f"https://www.etsy.com/listing/{listing_id}")
            print(f"  [+] Posted successfully. Listing ID: {listing_id}")
            append_log({
                "timestamp": datetime.now().isoformat(),
                "product_name": pair["name"],
                "listing_id": listing_id,
                "listing_url": listing_url,
                "status": "posted",
            })
            posted += 1
        else:
            print("  [error] Posting failed, see error above.")
            append_log({
                "timestamp": datetime.now().isoformat(),
                "product_name": pair["name"],
                "listing_id": "",
                "listing_url": "",
                "status": "failed",
            })

    print("\n" + "=" * 60)
    print(f"[done] Posted: {posted} | Skipped: {skipped} | Total reviewed: {len(pairs)}")
    print(f"[done] Log saved to {LOG_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
