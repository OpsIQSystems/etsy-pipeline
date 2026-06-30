"""
make_etsy_videos.py  --  Build SHORT, SILENT, Etsy-spec listing videos.

Etsy listing videos must be 5-15s, silent (played muted), vertical/square.
This builds a ~12s silent "watch it work" clip per product from the real
simulated-use demo (inputs fill in -> verdict reveals), reusing the cached
demo data in products/videos/_demos.json. No audio, no voiceover.

Output: products/videos/etsy/<name>.mp4
Run:    python make_etsy_videos.py
"""
import json
import os

from playwright.sync_api import sync_playwright

import creator
import simulate_use as su
import ugc_engine as ug

DEMOS_FILE = os.path.join(creator.PRODUCTS_DIR, "videos", "_demos.json")
OUT_DIR = os.path.join(creator.PRODUCTS_DIR, "videos", "etsy")


def main():
    with open(creator.INPUT_FILE, encoding="utf-8") as f:
        opportunities = json.load(f)
    with open(DEMOS_FILE, encoding="utf-8") as f:
        demos = json.load(f)

    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = os.path.join(OUT_DIR, "_frames")
    os.makedirs(tmp, exist_ok=True)

    built = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": ug.WIDTH, "height": ug.HEIGHT},
                                device_scale_factor=1)
        for idx, opp in enumerate(opportunities):
            title = opp.get("suggested_etsy_title", f"opportunity_{idx}")
            fname_base = creator.safe_filename(title)
            data = demos.get(fname_base)
            if not data or not data.get("verdict"):
                print(f"[skip] no demo data: {title[:50]}")
                continue
            print(f"[{idx+1}/{len(opportunities)}] {title[:55]}")
            display = (data.get("display") or title.split("|")[0]).strip()
            price = str(opp.get("suggested_price", "")).strip()
            if price and not price.startswith("$"):
                price = "$" + price

            # intro card (silent, longer hold)
            intro_png = os.path.join(tmp, f"etsy_{fname_base}_intro.png")
            ug.render_scene(page, ug.hook_scene("Watch it make the call for you"), intro_png)

            # the real "fill in -> verdict" demo
            demo = su.build_use_frames(page, data, tmp, f"etsy_{fname_base}")
            # hold the final verdict frame longer so the buyer can read it
            if demo:
                png, dur, zoom = demo[-1]
                demo[-1] = (png, max(dur, 3.6), zoom)

            # outro CTA card
            outro_png = os.path.join(tmp, f"etsy_{fname_base}_cta.png")
            ug.render_scene(page, ug.cta_scene("Instant download", price or "On Etsy",
                                               display), outro_png)

            frames = [(intro_png, 2.4, True)] + demo + [(outro_png, 3.0, True)]
            out = os.path.join(OUT_DIR, f"{fname_base}.mp4")
            ug.assemble(frames, out, xfade=0.4)
            # guard: confirm it actually rendered to a real file
            if os.path.getsize(out) < 5000:
                print(f"   [warn] output looks empty ({os.path.getsize(out)} bytes)")
            built += 1
            print(f"   -> {out}  ({os.path.getsize(out)} bytes)")
        browser.close()

    print(f"\n[done] built {built} silent Etsy listing videos -> {OUT_DIR}")
    print("Etsy spec: 1080x1920, silent, ~10-13s each. Upload in the Photo & Video section.")


if __name__ == "__main__":
    main()
