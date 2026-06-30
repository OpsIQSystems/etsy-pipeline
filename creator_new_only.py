"""One-off runner: build products only for the 3 newly-added 'beat the leader'
opportunities (indices 5, 6, 7) without re-spending tokens rebuilding the
original 5 that already succeeded."""
import json
import os

import creator

with open(creator.INPUT_FILE, "r", encoding="utf-8") as f:
    all_opportunities = json.load(f)

new_opportunities = all_opportunities[8:13]

os.makedirs(creator.PRODUCTS_DIR, exist_ok=True)
os.makedirs(creator.LISTINGS_DIR, exist_ok=True)

client = creator.load_anthropic_client()
print(f"[*] Building {len(new_opportunities)} new opportunities only...\n")

built = 0
for idx, opportunity in enumerate(new_opportunities, start=1):
    title = opportunity.get("suggested_etsy_title", f"opportunity_{idx}")
    print(f"[Product {idx}/{len(new_opportunities)}] {title}")
    try:
        print("  [-] Requesting dashboard spec from Claude...")
        spec = creator.call_claude_json(
            client, creator.SPEC_SYSTEM_PROMPT,
            f"Design the dashboard for this opportunity:\n{json.dumps(opportunity, indent=2)}",
            max_tokens=8192,
        )
        print("  [-] Requesting Etsy listing copy from Claude...")
        listing_copy = creator.call_claude_json(
            client, creator.LISTING_SYSTEM_PROMPT,
            f"Write Etsy listing copy for this opportunity:\n{json.dumps(opportunity, indent=2)}",
            max_tokens=2048,
        )

        fname_base = creator.safe_filename(title)
        xlsx_path = os.path.join(creator.PRODUCTS_DIR, f"{fname_base}.xlsx")
        pdf_path = os.path.join(creator.PRODUCTS_DIR, f"{fname_base}_guide.pdf")
        listing_path = os.path.join(creator.LISTINGS_DIR, f"{fname_base}.txt")

        print(f"  [-] Building workbook -> {xlsx_path}")
        creator.build_workbook(spec, opportunity, xlsx_path)
        print(f"  [-] Building PDF guide -> {pdf_path}")
        creator.build_pdf_guide(spec, opportunity, pdf_path)
        print(f"  [-] Writing listing copy -> {listing_path}")
        creator.build_listing_txt(listing_copy, opportunity, listing_path)

        built += 1
        print("  [+] Done.\n")
    except Exception as item_err:
        print(f"  [error] Failed to build product for '{title}': {item_err}\n")
        continue

print(f"[done] Built {built}/{len(new_opportunities)} new products.")
