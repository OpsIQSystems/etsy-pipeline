"""
ugc_creator.py  --  Faceless UGC video generator for the product catalog.

For each product it:
  1. Asks Claude (Opus) for a short-form video SCRIPT: a scroll-stopping hook,
     a relatable trade pain point, a solution line, the AI-insight punchline
     (the differentiator), a CTA, plus the ready-to-paste post caption and
     hashtags for TikTok / YT Shorts / Reels.
  2. Renders 5 branded vertical scenes (Playwright) -- reusing the product's
     existing mockup image for the "solution" scene.
  3. Assembles them into a 1080x1920 MP4 with Ken-Burns motion + crossfades
     (moviepy + bundled ffmpeg). No music baked in -- you add trending audio
     in-app, which is what the algorithm rewards.
  4. Writes a caption .txt (post text + hashtags) next to the MP4.

Output: products/videos/<name>.mp4  and  <name>_caption.txt
Run:    python ugc_creator.py                 (all products)
        python ugc_creator.py --only 0         (single product index, for testing)
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

import creator
import simulate_use as su
import tts
import ugc_engine as ug

VIDEOS_DIR = os.path.join(creator.PRODUCTS_DIR, "videos")
IMAGES_DIR = os.path.join(creator.PRODUCTS_DIR, "images")
SCRIPTS_DIR = os.path.join(VIDEOS_DIR, "_scripts")
DEMOS_FILE = os.path.join(VIDEOS_DIR, "_demos.json")
SHOP_NAME = "OperationsIntel on Etsy"   # placeholder shop handle for the CTA

# Real "simulated use" demo data (verdicts/inputs), precomputed by extract_demos.py
try:
    with open(DEMOS_FILE, encoding="utf-8") as _f:
        DEMOS = json.load(_f)
except Exception:
    DEMOS = {}


def _spoken_verdict(text):
    """Make a verdict string read naturally in TTS."""
    return (text.replace("/yr", " per year").replace("/mo", " per month")
                .replace(" - ", ": ").replace("-", " ").strip())

SCRIPT_SYSTEM_PROMPT = """You are a short-form video scriptwriter for faceless \
TikTok / YouTube Shorts / Instagram Reels ads selling a spreadsheet decision \
tool to owners of small service businesses (HVAC, landscaping, pool, cleaning, \
roofing, pest control, plumbing, contractors) and real-estate investors.

Return ONLY a JSON object with these keys:
- hook: a 4-9 word scroll-stopping opening line. Punchy, specific, no hashtags. \
Spoken like one tradesperson to another. Example style: "You're losing money on \
every callback."
- problem_line: one sentence naming the painful, relatable status quo (guessing, \
gut feel, messy notebook). <= 14 words.
- solution_line: one sentence on what the tool does. <= 12 words. Plain English.
- insight_line: the AI-insight punchline that shows the tool THINKS, not just \
stores data. One concrete sentence. Do NOT use quotation marks. <= 18 words.
- cta_line: 3-6 words. Action. Example: "Stop guessing. Start knowing."
- caption: the post caption (1-2 sentences + a soft CTA). Friendly, no emojis spam \
(at most 2 emojis). <= 200 characters.
- hashtags: array of 8-12 lowercase hashtags WITHOUT the # sign, mixing the trade \
niche and broad reach (e.g. "smallbusiness", "hvaclife", "contractor"). No spaces.

Keep every line free of straight or curly quotation marks. No markdown."""


def build_script(client, opportunity, fname_base):
    """Generate the script once and cache it so rebuilds (e.g. voice swaps)
    don't re-spend tokens."""
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    cache = os.path.join(SCRIPTS_DIR, f"{fname_base}.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    script = creator.call_claude_json(
        client, SCRIPT_SYSTEM_PROMPT,
        f"Write the video script for this product:\n{json.dumps(opportunity, indent=2)}",
        max_tokens=1024,
    )
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(script, f, indent=2)
    return script


def pick_image(fname_base):
    """Prefer the features image, then cover, for the solution scene."""
    for suffix in ("_2_features.png", "_1_cover.png", "_3_insight.png"):
        p = os.path.join(IMAGES_DIR, fname_base + suffix)
        if os.path.exists(p):
            return p
    return None


def clean(s):
    return (s or "").strip().strip('"').strip("'").replace("\n", " ")


def make_one(page, client, opportunity, tmpdir):
    title = opportunity.get("suggested_etsy_title", "product")
    fname_base = creator.safe_filename(title)
    price = str(opportunity.get("suggested_price", "")).strip()
    if price and not price.startswith("$"):
        price = "$" + price

    script = build_script(client, opportunity, fname_base)
    hook = clean(script.get("hook"))
    problem = clean(script.get("problem_line"))
    solution = clean(script.get("solution_line"))
    insight = clean(script.get("insight_line"))
    cta = clean(script.get("cta_line"))

    img = pick_image(fname_base)
    assemble_list = []

    def add(name, html, dur, zoom, line):
        png = os.path.join(tmpdir, f"{fname_base}__{name}.png")
        ug.render_scene(page, html, png)
        audio = tts.narrate(line, tts.PRODUCT_VOICE) if line else None
        assemble_list.append((png, dur, zoom, audio))

    add("hook", ug.hook_scene(hook), 2.6, True, hook)
    add("problem", ug.problem_scene(problem), 2.8, True, problem)

    # HERO: live "simulated use" of the real product, if we have demo data
    demo = DEMOS.get(fname_base)
    if demo and demo.get("verdict"):
        frames = su.build_use_frames(page, demo, tmpdir, fname_base)
        for i, (png, dur, zoom) in enumerate(frames):
            line = None
            if i == 0:
                line = solution  # script's plain-English "what it does" line
            elif i == len(frames) - 1:
                line = _spoken_verdict(demo["verdict"][1])  # speak the real verdict
            assemble_list.append((png, dur, zoom,
                                  tts.narrate(line, tts.PRODUCT_VOICE) if line else None))
    elif img:
        add("solution", ug.solution_scene(solution, img), 3.4, True, solution)
    else:
        add("solution", ug.hook_scene(solution), 3.0, True, solution)

    add("insight", ug.insight_scene(insight), 3.6, False, insight)
    add("cta", ug.cta_scene(cta, price or "On Etsy", SHOP_NAME), 3.0, True,
        f"{cta}. Find it on Etsy.")

    out_mp4 = os.path.join(VIDEOS_DIR, f"{fname_base}.mp4")
    ug.assemble(assemble_list, out_mp4)

    caption_path = os.path.join(VIDEOS_DIR, f"{fname_base}_caption.txt")
    tags = script.get("hashtags", []) or []
    hashtag_line = " ".join("#" + t.lstrip("#").replace(" ", "") for t in tags)
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(clean(script.get("caption")) + "\n\n" + hashtag_line + "\n")

    return out_mp4


def main():
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    with open(creator.INPUT_FILE, "r", encoding="utf-8") as f:
        opportunities = json.load(f)

    if "--only" in sys.argv:
        i = int(sys.argv[sys.argv.index("--only") + 1])
        opportunities = [opportunities[i]]

    client = creator.load_anthropic_client()
    tmpdir = os.path.join(VIDEOS_DIR, "_scenes")
    os.makedirs(tmpdir, exist_ok=True)

    built = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": ug.WIDTH, "height": ug.HEIGHT},
                                device_scale_factor=1)
        for idx, opp in enumerate(opportunities, start=1):
            title = opp.get("suggested_etsy_title", f"opportunity_{idx}")
            print(f"[{idx}/{len(opportunities)}] {title[:60]}")
            try:
                out = make_one(page, client, opp, tmpdir)
                built += 1
                print(f"  [+] {out}")
            except Exception as e:
                print(f"  [error] {e}")
        browser.close()

    print(f"\n[done] built {built}/{len(opportunities)} videos -> {VIDEOS_DIR}")


if __name__ == "__main__":
    main()
