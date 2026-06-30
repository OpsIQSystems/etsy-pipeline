"""One-off runner: generate mockup images only for opportunities 8-12 (the 5
that were missed in the first image_creator.py pass)."""
import json
import os

from playwright.sync_api import sync_playwright

import creator
import image_creator

with open(creator.INPUT_FILE, "r", encoding="utf-8") as f:
    all_opportunities = json.load(f)

new_opportunities = all_opportunities[8:13]

os.makedirs(image_creator.IMAGES_DIR, exist_ok=True)
client = creator.load_anthropic_client()

print(f"[*] Generating mockup images for {len(new_opportunities)} products...\n")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1000, "height": 1250}, device_scale_factor=2)

    built = 0
    for idx, opportunity in enumerate(new_opportunities, start=1):
        title = opportunity.get("suggested_etsy_title", f"opportunity_{idx}")
        price = opportunity.get("suggested_price", "")
        fname_base = creator.safe_filename(title)
        print(f"[Image set {idx}/{len(new_opportunities)}] {title}")

        try:
            print("  [-] Requesting image copy from Claude...")
            copy = creator.call_claude_json(
                client, image_creator.IMAGE_COPY_SYSTEM_PROMPT,
                f"Write cover-image copy for this opportunity:\n{json.dumps(opportunity, indent=2)}",
                max_tokens=1024,
            )

            cover_path = os.path.join(image_creator.IMAGES_DIR, f"{fname_base}_1_cover.png")
            features_path = os.path.join(image_creator.IMAGES_DIR, f"{fname_base}_2_features.png")
            insight_path = os.path.join(image_creator.IMAGES_DIR, f"{fname_base}_3_insight.png")

            display_name = copy.get("display_name") or title
            clean_quote = copy.get("sample_insight_quote", "").strip().strip('"').strip("'")

            image_creator.render_html_to_png(page, image_creator.cover_html(
                copy.get("headline", title), copy.get("subheadline", ""),
                copy.get("badge_text", "Decision Support Tool"), price, display_name), cover_path)

            image_creator.render_html_to_png(page, image_creator.features_html(
                display_name, copy.get("feature_bullets", [])), features_path)

            image_creator.render_html_to_png(page, image_creator.insight_html(
                clean_quote, copy.get("badge_text", "")), insight_path)

            built += 1
            print(f"  [+] Saved 3 images -> {image_creator.IMAGES_DIR}\\{fname_base}_*.png\n")

        except Exception as item_err:
            print(f"  [error] Failed to build images for '{title}': {item_err}\n")
            continue

    browser.close()

print(f"[done] Built image sets for {built}/{len(new_opportunities)} products.")
