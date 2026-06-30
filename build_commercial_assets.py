"""Build images + silent Etsy listing video for the Commercial analyzer, then
package a ready-to-list kit folder. Reuses the same engines as the rest."""
import json
import os
import shutil

from playwright.sync_api import sync_playwright

import creator
import image_creator
import simulate_use as su
import ugc_engine as ug
from build_commercial import COMMERCIAL

FNAME = creator.safe_filename(COMMERCIAL["suggested_etsy_title"])
KIT = os.path.join(creator.PRODUCTS_DIR, "listing_kits", "19_Commercial_Real_Estate_Deal_Analyzer")
ETSY_VID_DIR = os.path.join(creator.PRODUCTS_DIR, "videos", "etsy")


def main():
    os.makedirs(image_creator.IMAGES_DIR, exist_ok=True)
    os.makedirs(ETSY_VID_DIR, exist_ok=True)
    os.makedirs(KIT, exist_ok=True)
    client = creator.load_anthropic_client()

    price = f"${COMMERCIAL['suggested_price']}"   # for video CTA pill
    img_price = str(COMMERCIAL['suggested_price'])  # cover_html adds its own $
    demo = su.demo_data(os.path.join(creator.PRODUCTS_DIR, f"{FNAME}.xlsx"))

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel="msedge")

        # ---- 3 product images ----
        pg = b.new_page(viewport={"width": 1000, "height": 1250}, device_scale_factor=2)
        copy = creator.call_claude_json(
            client, image_creator.IMAGE_COPY_SYSTEM_PROMPT,
            f"Write cover-image copy for this opportunity:\n{json.dumps(COMMERCIAL, indent=2)}",
            max_tokens=1024,
        )
        display_name = copy.get("display_name") or COMMERCIAL["suggested_etsy_title"].split("|")[0]
        clean_quote = copy.get("sample_insight_quote", "").strip().strip('"').strip("'")
        c1 = os.path.join(image_creator.IMAGES_DIR, f"{FNAME}_1_cover.png")
        c2 = os.path.join(image_creator.IMAGES_DIR, f"{FNAME}_2_features.png")
        c3 = os.path.join(image_creator.IMAGES_DIR, f"{FNAME}_3_insight.png")
        image_creator.render_html_to_png(pg, image_creator.cover_html(
            copy.get("headline", display_name), copy.get("subheadline", ""),
            copy.get("badge_text", "Decision Support Tool"), img_price, display_name), c1)
        image_creator.render_html_to_png(pg, image_creator.features_html(
            display_name, copy.get("feature_bullets", [])), c2)
        image_creator.render_html_to_png(pg, image_creator.insight_html(
            clean_quote, copy.get("badge_text", "")), c3)
        print("[+] 3 images built")

        # ---- silent Etsy listing video (intro + live demo + outro) ----
        vpg = b.new_page(viewport={"width": ug.WIDTH, "height": ug.HEIGHT}, device_scale_factor=1)
        tmp = os.path.join(ETSY_VID_DIR, "_frames")
        os.makedirs(tmp, exist_ok=True)
        intro = os.path.join(tmp, f"{FNAME}_intro.png")
        outro = os.path.join(tmp, f"{FNAME}_cta.png")
        ug.render_scene(vpg, ug.hook_scene("Watch it make the call for you"), intro)
        frames = su.build_use_frames(vpg, demo, tmp, FNAME)
        if frames:
            png, dur, zoom = frames[-1]
            frames[-1] = (png, max(dur, 3.6), zoom)
        ug.render_scene(vpg, ug.cta_scene("Instant download", price, demo.get("display", display_name)), outro)
        allf = [(intro, 2.4, True)] + frames + [(outro, 3.0, True)]
        out_vid = os.path.join(ETSY_VID_DIR, f"{FNAME}.mp4")
        ug.assemble(allf, out_vid, xfade=0.4)
        print(f"[+] Etsy video built ({os.path.getsize(out_vid)} bytes)")
        b.close()

    # ---- package kit ----
    for i, suf in enumerate(["_1_cover.png", "_2_features.png", "_3_insight.png"], 1):
        shutil.copy(os.path.join(image_creator.IMAGES_DIR, FNAME + suf),
                    os.path.join(KIT, f"image_{i}.png"))
    shutil.copy(os.path.join(creator.PRODUCTS_DIR, f"{FNAME}.xlsx"), os.path.join(KIT, f"{FNAME}.xlsx"))
    shutil.copy(os.path.join(creator.PRODUCTS_DIR, f"{FNAME}_guide.pdf"), os.path.join(KIT, f"{FNAME}_guide.pdf"))
    shutil.copy(os.path.join(ETSY_VID_DIR, f"{FNAME}.mp4"), os.path.join(KIT, "listing_video.mp4"))
    # listing info
    data = __import__("lister").parse_listing_txt(os.path.join(creator.LISTINGS_DIR, f"{FNAME}.txt"))
    with open(os.path.join(KIT, "LISTING_INFO.txt"), "w", encoding="utf-8") as f:
        f.write("COMMERCIAL REAL ESTATE DEAL ANALYZER - LISTING KIT\n" + "="*55 + "\n\n")
        f.write("--- TITLE ---\n" + data["title"] + "\n\n")
        f.write(f"--- PRICE ---\n${COMMERCIAL['suggested_price']}\n\n")
        f.write("--- DESCRIPTION ---\n" + data["description"] + "\n\n")
        f.write("--- TAGS (13) ---\n" + ", ".join(data["tags"]) + "\n\n")
        f.write("--- SETTINGS ---\nDigital | Personal Finance Templates | 2020-2026 | I did | Finished product | AI generator | Qty 999 | Auto-renew\n")
    print(f"\n[done] Kit packaged -> {KIT}")
    print("contents:", sorted(os.listdir(KIT)))


if __name__ == "__main__":
    main()
