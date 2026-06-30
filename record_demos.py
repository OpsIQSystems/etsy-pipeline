"""
record_demos.py
Record a browser demo video for every product in product_configs.py.
Uses Playwright to animate the simulator_template.html with each product's
config injected, then renders the recording + UGC voiceover into a final MP4.

Usage:
  python record_demos.py              # record all products
  python record_demos.py hvac_job_bid # record one by slug
"""
import asyncio
import json
import sys
import shutil
from pathlib import Path

import edge_tts
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx import Loop
from playwright.async_api import async_playwright

from product_configs import PRODUCTS, PRODUCT_MAP

BASE        = Path(__file__).parent
TEMPLATE    = BASE / "simulator_template.html"
DEMOS_DIR   = BASE / "products" / "browser_demos"
AUDIO_TMP   = BASE / "products" / "audio"
STICK_DIR   = BASE / "products" / "videos"
FONT        = r"C:\Windows\Fonts\arialbd.ttf"
RECORD_SIZE = {"width": 720, "height": 960}   # vertical 3:4 — good for Shorts/Reels
RECORD_SECS = 22   # capture one full animation cycle


UGC_SCRIPTS = {
    "hvac_job_bid":              "I lost thirty two hundred dollars on a job and didn't even know it. Pricing HVAC in my head for twelve years. Then I found this calculator on Etsy — twenty bucks. Put my last job through it. I'd been undercharging by twelve percent on every install. Next bid, quoted eighty four hundred. Got the job. Cleared over two grand profit. It's in my bio. Just get it.",
    "crew_profit_tracker":       "I had three trucks running and had no idea which one was actually making money. Thought they were all good. This tracker showed me Truck 2 was running at forty-four percent margin and Truck 1 was at nineteen. Cut Truck 1's route, added a job to Truck 2. Made an extra eight hundred a week doing nothing different. Link in bio.",
    "rental_property_dashboard": "I almost passed on a deal because the numbers looked tight. Ran it through this dashboard — cap rate of five point eight, cash-on-cash of seven-two, breaks even at seventy-four percent occupancy. I bought it. Cash flows positive every single month. Twenty bucks on Etsy. Link in my bio.",
    "commercial_real_estate":    "I was about to make an offer on a strip center and my lender kills it — DSCR too low, they said. I had no idea what that even meant. Found this analyzer, it checks DSCR automatically. Now I screen every deal before I even call a broker. Saved me from a bad offer last month. Link in bio.",
    "equipment_replacement":     "My tech quoted me thirty-two hundred to fix a unit. I ran it through this tool. Eleven-year-old unit, failure risk at eight out of ten, three-year repair cost would've been sixty-five hundred. New unit is ninety-eight hundred. Replace it wins by five hundred and zero breakdown risk. Stopped guessing. Link in bio.",
    "tenant_retention":          "My property manager said to let my tenant go and re-rent at market rate. This tool said turning that unit would cost seventy-three fifty in vacancy and rehab — I wouldn't break even for six months. Renewed the lease at a hundred more a month. Saved almost two grand in year one. Link in bio.",
    "property_repair_replace":   "Twenty-two year old roof, contractor says four-eight to patch it. This tool showed me three-year repair total of sixty-five hundred versus replacing now at eighteen-five. With the failure risk at eight out of ten and rental income on the line, replace wins. Pulled the trigger. No more emergency calls. Link in bio.",
    "airbnb_str":                "I was listing on VRBO only because the fees looked lower. This tool compared actual net revenue head to head. Airbnb clears three thousand one eighty-six a month versus twenty-nine forty on VRBO — almost two hundred fifty more every single month. Switched platforms. Link in bio.",
    "cash_flow_stress_test":     "Everyone said my triplex couldn't survive a bad vacancy stretch. This stress test ran it at twenty-five percent vacancy — still cash flows positive at two-eighty a month. Then it showed me a refi scenario that adds eight hundred fifteen. I refinanced. Sleeping better now. Link in bio.",
    "recurring_customer_profitability": "I had a client I was about to drop because they felt like a lot of work. This tracker showed me they're generating thirteen thousand five hundred sixty a year at forty-seven percent margin. They're my highest margin account. I almost fired my best client. Link in bio.",
    "seasonal_cash_flow":        "Every winter I was scrambling. Didn't know how much cash I actually needed to survive the slow months. This planner showed me the gap — nine thousand one hundred forty-eight short. I laid off two guys for eight weeks, rebuilt the reserve. First time in four years I didn't borrow money in January. Link in bio.",
    "quote_to_close":            "I was spending money on four different lead sources and had no idea which ones were working. This tracker showed me Google LSA was closing at sixty-eight percent with an eighteen-to-one ROI. Everything else was noise. Cut two channels. Doubled LSA. Revenue went up. Link in bio.",
    "service_business_expansion": "My shop was at ninety-four percent capacity and I kept saying no to jobs. This calculator showed hiring one more tech breaks even in month four and nets eighty-four grand by month twelve. Hired him. Best decision I made this year. Link in bio.",
    "technician_profitability":  "I thought my best tech was my most profitable. He wasn't. This scorecard showed he was running three callbacks a month — almost a thousand dollars in rework cost drag. Coached him on the root cause. Callbacks dropped to zero. Margin jumped back up. Link in bio.",
    "materials_markup":          "I just found out I've been losing seven thousand dollars a year on refrigerant alone. I was marking it up thirty-five percent. Industry average is sixty. This tool showed me line by line where my markup was leaking. Fixed it in one afternoon. Link in bio.",
    "marketing_roi":             "I was spending twelve hundred a month on Facebook ads and thought they weren't working. This calculator showed me a nineteen-to-one return on ad spend with a cost per customer of eighty-five bucks. I was measuring it wrong the whole time. Scaled it up. Link in bio.",
    "service_area_density":      "I used to take every job no matter where it was. This tool showed me jobs over thirty miles out were running below forty percent margin after drive time. Started declining or adding a fuel surcharge. Revenue stayed the same, profit went up. Link in bio.",
    "price_increase":            "I hadn't raised my rates in three years and was scared to lose customers. This calculator showed me I could go from ninety-five to a hundred ten and only lose eight percent of jobs max — and I'd still net four grand more a month. Raised rates. Lost two clients. Made more money. Link in bio.",
    "callback_rework":           "Seven callbacks last month. I thought it was no big deal — free fixes, keep customers happy. This tool showed me the real cost: over seven thousand dollars in direct cost and displaced revenue. Ninety-two thousand a year. I started tracking root causes immediately. Link in bio.",
    "real_estate_deal_comparison": "I was comparing two properties in my head and making myself crazy. Put both in this tool — cap rate, cash-on-cash, everything side by side. Deal A cleared my target by over a percent. Deal B didn't. Offer in on Deal A by noon. Link in bio.",
}


async def record_one(slug: str, pw) -> Path | None:
    cfg = PRODUCT_MAP.get(slug)
    if not cfg:
        print(f"  [!] slug not found: {slug}")
        return None

    DEMOS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_TMP.mkdir(parents=True, exist_ok=True)
    out_path = DEMOS_DIR / f"browser_{slug}.mp4"

    if out_path.exists():
        print(f"  [skip] {slug} — already recorded")
        return out_path

    print(f"  [→] Recording: {cfg['title']}")

    # ── 1. Generate voiceover ──────────────────────────────────────────────
    script = UGC_SCRIPTS.get(slug, f"This is the {cfg['title']}. Built for trades and real estate pros who are done guessing. Link in bio.")
    audio_path = AUDIO_TMP / f"ugc_{slug}.mp3"
    communicate = edge_tts.Communicate(script, "en-US-GuyNeural")
    await communicate.save(str(audio_path))

    # ── 2. Record browser animation via Playwright ─────────────────────────
    raw_webm = AUDIO_TMP / f"raw_{slug}.webm"
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(
        viewport=RECORD_SIZE,
        record_video_dir=str(AUDIO_TMP),
        record_video_size=RECORD_SIZE,
    )
    page = await ctx.new_page()

    template_url = f"file:///{TEMPLATE.as_posix()}"
    await page.goto(template_url)

    # Inject product config
    config_js = json.dumps({
        "title":        cfg["title"],
        "tagline":      cfg["tagline"],
        "inputs":       cfg["inputs"],
        "outputs":      cfg["outputs"],
        "verdict":      cfg["verdict"],
        "verdict_type": cfg["verdict_type"],
        "profit":       cfg["profit"],
    })
    await page.evaluate(f"window.__PRODUCT_CONFIG__ = {config_js}; run();")
    await asyncio.sleep(RECORD_SECS)

    video_path_obj = await page.video.path()
    await ctx.close()
    await browser.close()

    shutil.move(str(video_path_obj), str(raw_webm))

    # ── 3. Composite: browser recording + voiceover + persona overlay ──────
    audio  = AudioFileClip(str(audio_path))
    video  = VideoFileClip(str(raw_webm))

    # loop or trim browser recording to match audio length
    if video.duration < audio.duration:
        video = Loop(n=10).apply(video).with_duration(audio.duration)
    else:
        video = video.subclipped(0, audio.duration)

    video = video.with_audio(audio)

    # Persona overlay
    try:
        persona_label = cfg.get("persona", "")
        if persona_label:
            txt = (
                TextClip(font=FONT, text=persona_label, font_size=26,
                         color="white", stroke_color="black", stroke_width=2, method="label")
                .with_position(("center", 0.85), relative=True)
                .with_duration(audio.duration)
            )
            video = CompositeVideoClip([video, txt])
    except Exception as e:
        print(f"    [overlay skipped] {e}")

    video.write_videofile(str(out_path), codec="libx264", audio_codec="aac",
                          logger=None, threads=2)
    raw_webm.unlink(missing_ok=True)
    audio_path.unlink(missing_ok=True)

    print(f"  [✓] Saved: {out_path.name}")
    return out_path


async def main(slugs=None):
    targets = [PRODUCT_MAP[s] for s in slugs if s in PRODUCT_MAP] if slugs else PRODUCTS
    print(f"Recording {len(targets)} product demo(s)...\n")
    async with async_playwright() as pw:
        for cfg in targets:
            try:
                await record_one(cfg["slug"], pw)
            except Exception as e:
                print(f"  [ERROR] {cfg['slug']}: {e}")
    print("\nDone.")


if __name__ == "__main__":
    slugs = sys.argv[1:] or None
    asyncio.run(main(slugs))
