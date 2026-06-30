"""
package_listings.py  --  Bundle selected products into ready-to-list "kits" for
fast MANUAL Etsy listing (until the API app is approved).

Each kit folder gets:
  - the .xlsx tool and the _guide.pdf  (the digital files buyers download)
  - the 3 mockup images, renamed 1/2/3 for upload order
  - LISTING_INFO.txt : copy-paste-ready Title / Price / Description / Tags +
    the exact Etsy field settings (type, who made, etc.)

Run: python package_listings.py
"""
import json
import os
import shutil

import creator
import lister  # reuse its listing-txt parser

# Build kits for ALL products (indices into opportunities.json)
PICKS = list(range(19))
KITS_DIR = os.path.join(creator.PRODUCTS_DIR, "listing_kits")
IMAGES_DIR = os.path.join(creator.PRODUCTS_DIR, "images")


def short(title):
    base = title.split("|")[0].strip()
    return "".join(c if c.isalnum() else "_" for c in base).strip("_")[:40]


def main():
    with open(creator.INPUT_FILE, encoding="utf-8") as f:
        opps = json.load(f)
    os.makedirs(KITS_DIR, exist_ok=True)

    for n, idx in enumerate(PICKS, start=1):
        opp = opps[idx]
        title = opp["suggested_etsy_title"]
        fbase = creator.safe_filename(title)
        sn = short(title)
        kit = os.path.join(KITS_DIR, f"{idx:02d}_{sn}")
        os.makedirs(kit, exist_ok=True)

        # digital deliverables
        xlsx = os.path.join(creator.PRODUCTS_DIR, f"{fbase}.xlsx")
        pdf = os.path.join(creator.PRODUCTS_DIR, f"{fbase}_guide.pdf")
        for src in (xlsx, pdf):
            if os.path.exists(src):
                shutil.copy(src, os.path.join(kit, os.path.basename(src)))

        # images in upload order
        for i, suf in enumerate(["_1_cover.png", "_2_features.png", "_3_insight.png"], start=1):
            src = os.path.join(IMAGES_DIR, fbase + suf)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(kit, f"image_{i}.png"))

        # listing copy
        data = lister.parse_listing_txt(os.path.join(creator.LISTINGS_DIR, f"{fbase}.txt"))
        price = opp.get("suggested_price", data.get("price", ""))
        info = os.path.join(kit, "LISTING_INFO.txt")
        with open(info, "w", encoding="utf-8") as f:
            f.write("=" * 64 + "\n")
            f.write(f"ETSY LISTING KIT  ({n} of {len(PICKS)})\n")
            f.write("=" * 64 + "\n\n")
            f.write("--- TITLE (copy/paste) ---\n")
            f.write(data["title"] + "\n\n")
            f.write(f"--- PRICE ---\n${price}\n\n")
            f.write("--- DESCRIPTION (copy/paste) ---\n")
            f.write(data["description"] + "\n\n")
            f.write("--- TAGS (13, paste one at a time or comma-separated) ---\n")
            f.write(", ".join(data["tags"]) + "\n\n")
            f.write("--- ETSY FIELD SETTINGS ---\n")
            f.write("Listing type:        Digital (an instant download)\n")
            f.write("Who made it:         I did\n")
            f.write("What is it:          A finished product\n")
            f.write("When did you make it: 2020-2026 (Made to order is NOT for digital)\n")
            f.write("Category:            search 'Spreadsheet' or 'Templates'\n")
            f.write("Quantity:            (auto for digital)\n")
            f.write("Renewal:             Automatic\n")
            f.write("Digital files:       upload the .xlsx AND the _guide.pdf in this folder\n")
            f.write("Photos:              upload image_1, image_2, image_3 (in order)\n")
        print(f"[kit {n}] {kit}")

    print(f"\n[done] {len(PICKS)} listing kits -> {KITS_DIR}")


if __name__ == "__main__":
    main()
