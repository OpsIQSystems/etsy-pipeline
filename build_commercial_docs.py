"""Regenerate ONLY the PDF guide and Etsy listing copy for the Commercial
analyzer (reflecting the upgraded NOI model with capital reserve + management
fee). Deliberately does NOT rebuild the workbook -- the live .xlsx has been
hand-enhanced and must not be overwritten by a fresh Claude spec."""
import json
import os

import creator
from build_commercial import COMMERCIAL


def main():
    client = creator.load_anthropic_client()
    opp = COMMERCIAL
    fname = creator.safe_filename(opp["suggested_etsy_title"])
    pdf_path = os.path.join(creator.PRODUCTS_DIR, f"{fname}_guide.pdf")
    listing_path = os.path.join(creator.LISTINGS_DIR, f"{fname}.txt")

    print("[-] Requesting refreshed spec (for the guide) from Claude...")
    spec = creator.call_claude_json(
        client, creator.SPEC_SYSTEM_PROMPT,
        f"Design the dashboard for this opportunity:\n{json.dumps(opp, indent=2)}",
        max_tokens=8192,
    )
    print("[-] Requesting refreshed Etsy listing copy from Claude...")
    listing_copy = creator.call_claude_json(
        client, creator.LISTING_SYSTEM_PROMPT,
        f"Write Etsy listing copy for this opportunity:\n{json.dumps(opp, indent=2)}",
        max_tokens=2048,
    )

    print(f"[-] Rebuilding PDF guide -> {pdf_path}")
    creator.build_pdf_guide(spec, opp, pdf_path)
    print(f"[-] Rewriting listing copy -> {listing_path}")
    creator.build_listing_txt(listing_copy, opp, listing_path)
    print("[done] guide + listing refreshed (workbook left untouched).")


if __name__ == "__main__":
    main()
