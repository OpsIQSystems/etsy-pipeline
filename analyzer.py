"""
FILE 4: analyzer.py
Reads listings.csv, reviews.csv, and reddit_pain_points.csv, then asks
Claude (claude-sonnet-4-6) to identify the top 5 product opportunities
for small service businesses, framed as Decision Support Systems.
Run independently: python analyzer.py
Output: opportunities.json
"""

import csv
import json
import os
import sys

from anthropic import Anthropic
from dotenv import load_dotenv

MODEL_NAME = "claude-sonnet-4-6"  # CRITICAL: never use opus

LISTINGS_FILE = "listings.csv"
REVIEWS_FILE = "reviews.csv"
REDDIT_FILE = "reddit_pain_points.csv"
OUTPUT_FILE = "opportunities.json"

MAX_ROWS_PER_SOURCE = 150  # keep prompt size sane

SYSTEM_PROMPT = """You are an operations intelligence analyst. You work for a company that \
builds Decision Support Systems for small service businesses (property management, HVAC, \
landscaping, pool service, cleaning, roofing, pest control, plumbing, contractors). These \
products are NOT templates -- they explain what decisions to make, not just display data. \
Example outputs the products should be able to generate: \
"Crew 2 generated 22% more profit than Crew 1" and "Truck 4 has exceeded replacement economics."

You will be given:
1. A sample of competing Etsy listings (titles, prices, review counts, tags, descriptions)
2. A sample of reviews on those listings, flagged where they mention complaints
3. A sample of Reddit posts/comments from small service business owners discussing pain points

Identify the TOP 5 product opportunities for small service businesses. For EACH opportunity, output:
- what_exists_and_flaws: what currently exists on Etsy and its concrete flaws
- what_to_build: what to build that is meaningfully better
- ai_explanation_value: how an AI explanation layer adds value beyond raw numbers
- suggested_price: a number between 29 and 149
- suggested_etsy_title: a keyword-optimized title under 140 characters
- target_customer: a specific persona, e.g. "HVAC business owner with 3-8 trucks"
- score: an integer 1-10 rating the opportunity's strength

Respond with ONLY a JSON array of 5 objects using exactly those keys. No prose, no markdown fences."""


def load_csv_rows(path: str, max_rows: int):
    rows = []
    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(row)
    except FileNotFoundError:
        print(f"[warn] {path} not found, continuing without it.")
    return rows


def load_anthropic_client():
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("[fatal] Missing ANTHROPIC_API_KEY in .env file.")
        print("        Get a key at https://console.anthropic.com/settings/keys")
        sys.exit(1)
    try:
        return Anthropic(api_key=api_key)
    except Exception as client_err:
        print(f"[fatal] Could not initialize Anthropic client: {client_err}")
        sys.exit(1)


def build_user_prompt(listings, reviews, reddit_rows):
    payload = {
        "etsy_listings_sample": listings,
        "etsy_reviews_sample": reviews,
        "reddit_pain_points_sample": reddit_rows,
    }
    return (
        "Here is the research data collected from Etsy and Reddit. "
        "Analyze it and return the top 5 product opportunities as instructed.\n\n"
        f"{json.dumps(payload, indent=2, default=str)}"
    )


def extract_json_array(raw_text: str):
    """Claude is instructed to return raw JSON, but strip fences defensively."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def main():
    print("=" * 60)
    print("OPPORTUNITY ANALYZER (Claude API)")
    print("=" * 60)

    print(f"[*] Loading source data (max {MAX_ROWS_PER_SOURCE} rows per file)...")
    listings = load_csv_rows(LISTINGS_FILE, MAX_ROWS_PER_SOURCE)
    reviews = load_csv_rows(REVIEWS_FILE, MAX_ROWS_PER_SOURCE)
    reddit_rows = load_csv_rows(REDDIT_FILE, MAX_ROWS_PER_SOURCE)

    print(f"  [-] listings.csv: {len(listings)} rows")
    print(f"  [-] reviews.csv: {len(reviews)} rows")
    print(f"  [-] reddit_pain_points.csv: {len(reddit_rows)} rows")

    if not listings and not reviews and not reddit_rows:
        print("[fatal] No source data found. Run scraper.py, review_scraper.py, and reddit_scraper.py first.")
        sys.exit(1)

    client = load_anthropic_client()
    print(f"\n[*] Sending data to {MODEL_NAME} for analysis...")

    user_prompt = build_user_prompt(listings, reviews, reddit_rows)

    try:
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as api_err:
        print(f"[fatal] Claude API call failed: {api_err}")
        sys.exit(1)

    raw_text = "".join(block.text for block in response.content if hasattr(block, "text"))

    try:
        opportunities = extract_json_array(raw_text)
    except json.JSONDecodeError as parse_err:
        print(f"[fatal] Could not parse Claude's response as JSON: {parse_err}")
        print("---- raw response ----")
        print(raw_text)
        sys.exit(1)

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(opportunities, f, indent=2)
    except PermissionError:
        print(f"[fatal] Could not write to {OUTPUT_FILE}. Is it open in another program?")
        sys.exit(1)

    print(f"\n[+] Received {len(opportunities)} opportunities from Claude.")
    for i, opp in enumerate(opportunities, start=1):
        title = opp.get("suggested_etsy_title", "Untitled")
        score = opp.get("score", "?")
        print(f"  {i}. [{score}/10] {title}")

    print("\n" + "=" * 60)
    print(f"[done] Opportunities saved to {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
