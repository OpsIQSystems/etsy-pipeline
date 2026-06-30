"""
extract_demos.py  --  Precompute real "simulated use" demo data for every
product in ONE LibreOffice session (fast), caching to products/videos/_demos.json.
ugc_creator.py reads this cache to render the demo scene without needing soffice
at video-build time.

Run: python extract_demos.py
"""
import json
import os
import shutil
import tempfile

import creator
import simulate_buyer as sb
import simulate_use as su

OUT = os.path.join(creator.PRODUCTS_DIR, "videos", "_demos.json")


def main():
    with open(creator.INPUT_FILE, encoding="utf-8") as f:
        opportunities = json.load(f)

    tmp = tempfile.mkdtemp(prefix="demos_")
    index = {}  # staged copy path -> fname_base
    for idx, opp in enumerate(opportunities):
        fname_base = creator.safe_filename(opp["suggested_etsy_title"])
        src = os.path.join(creator.PRODUCTS_DIR, f"{fname_base}.xlsx")
        if not os.path.exists(src):
            continue
        dst = os.path.join(tmp, f"prod{idx:02d}.xlsx")
        shutil.copyfile(src, dst)
        index[dst] = (fname_base, src)

    print(f"[*] recalculating {len(index)} workbooks in one LibreOffice session...")
    proc = sb.start_soffice(os.path.join(tmp, "prof"))
    try:
        print("   ", sb.batch_recalc(tmp))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    demos = {}
    for dst, (fname_base, src) in index.items():
        try:
            data = su.extract_from_pair(src, dst)
            demos[fname_base] = data
            v = (data.get("verdict") or ["", ""])[1]
            print(f"  [+] {fname_base[:42]:42} verdict: {v[:50]}")
        except Exception as e:
            print(f"  [error] {fname_base[:42]}: {e}")

    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(demos, f, indent=2)
    print(f"\n[done] wrote demo data for {len(demos)} products -> {OUT}")


if __name__ == "__main__":
    main()
