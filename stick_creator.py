"""
stick_creator.py  --  Faceless stick-figure "trades humor" shorts.

Per product, Claude writes a short 4-5 panel skit themed to that product's pain
point (gut-feel quoting, money leaks, guessing which job pays), ending on a soft
CTA. Panels are rendered by stickfigure.py and stitched into a vertical MP4.

Output: products/videos/stick_<name>.mp4  +  stick_<name>_caption.txt
Run:    python stick_creator.py            (all)
        python stick_creator.py --only 0   (single, for testing)
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

import creator
import stickfigure as sf
import tts
import ugc_engine as ug

VIDEOS_DIR = os.path.join(creator.PRODUCTS_DIR, "videos")
SCRIPTS_DIR = os.path.join(VIDEOS_DIR, "_scripts")
ALLOWED_POSES = set(sf.POSES.keys())
ALLOWED_PROPS = {"money", "calc", "none", "", None}

SKIT_SYSTEM_PROMPT = """You write SHORT, funny faceless stick-figure skits for \
TikTok / Reels aimed at small service-business owners (HVAC, landscaping, pool, \
roofing, plumbing, pest control, cleaning, contractors). The joke must land the \
relatable pain that the given product solves, then flip to the smart move.

Return ONLY a JSON object:
- panels: array of 4-5 panels. Each panel:
    - caption: top text, <= 22 characters per natural line, max ~6 words. The \
narration/setup or punchline. Plain, funny, specific to the trade.
    - pose: ONE of exactly these: neutral, shrug, sweat, facepalm, think, point, flex, dead
    - bubble: OPTIONAL short speech line the figure says, <= 18 characters. Omit if none.
    - prop: OPTIONAL one of: money, calc, none. Use calc when showing the smart tool, \
money when showing profit/loss. Omit or "none" otherwise.
    - accent: true ONLY on the funniest punchline panel, else false.
  Structure: panel 1 sets up the dumb status quo (pose sweat/shrug/think), \
middle panel is the painful punchline (facepalm/dead, accent:true), then the flip \
to the confident smart version (flex/point with calc), final panel a soft CTA.
- caption: the post caption, funny, <= 180 chars, at most 2 emojis.
- hashtags: array of 8-12 lowercase hashtags without the # sign (mix trade niche + broad).

Keep all text free of quotation marks. Be genuinely funny, not corny. No markdown."""


def clean(s):
    return (s or "").strip().strip('"').strip("'")


def build_skit(client, opportunity, fname_base):
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    cache = os.path.join(SCRIPTS_DIR, f"stick_{fname_base}.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    skit = creator.call_claude_json(
        client, SKIT_SYSTEM_PROMPT,
        f"Write the stick-figure skit for this product:\n{json.dumps(opportunity, indent=2)}",
        max_tokens=1024,
    )
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(skit, f, indent=2)
    return skit


def make_one(page, client, opportunity, tmpdir):
    title = opportunity.get("suggested_etsy_title", "product")
    fname_base = creator.safe_filename(title)
    skit = build_skit(client, opportunity, fname_base)

    panels = skit.get("panels", [])[:5]
    assemble_list = []
    for i, panel in enumerate(panels):
        pose = panel.get("pose", "neutral")
        if pose not in ALLOWED_POSES:
            pose = "neutral"
        prop = panel.get("prop")
        if prop not in ALLOWED_PROPS:
            prop = None
        if prop in ("none", ""):
            prop = None
        caption = clean(panel.get("caption"))
        bubble = clean(panel.get("bubble")) or None
        svg = sf.panel_svg(caption, pose, bubble=bubble,
                           prop=prop, accent=bool(panel.get("accent")))
        png = os.path.join(tmpdir, f"stick_{fname_base}__{i}.png")
        sf.render_panel(page, svg, png)
        # one consistent narrator reads the setup; speaks the bubble line too
        narration = caption + (f". {bubble}" if bubble else "")
        audio = tts.narrate(narration, tts.STICK_VOICE)
        # last panel lingers; punchline a touch longer
        dur = 3.0 if i == len(panels) - 1 else (2.4 if panel.get("accent") else 2.0)
        assemble_list.append((png, dur, False, audio))  # no zoom: keeps line art crisp

    out_mp4 = os.path.join(VIDEOS_DIR, f"stick_{fname_base}.mp4")
    ug.assemble(assemble_list, out_mp4, xfade=0.25)

    tags = skit.get("hashtags", []) or []
    hashtag_line = " ".join("#" + t.lstrip("#").replace(" ", "") for t in tags)
    with open(os.path.join(VIDEOS_DIR, f"stick_{fname_base}_caption.txt"), "w",
              encoding="utf-8") as f:
        f.write(clean(skit.get("caption")) + "\n\n" + hashtag_line + "\n")
    return out_mp4


def main():
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    with open(creator.INPUT_FILE, "r", encoding="utf-8") as f:
        opportunities = json.load(f)
    if "--only" in sys.argv:
        i = int(sys.argv[sys.argv.index("--only") + 1])
        opportunities = [opportunities[i]]

    client = creator.load_anthropic_client()
    tmpdir = os.path.join(VIDEOS_DIR, "_stick_scenes")
    os.makedirs(tmpdir, exist_ok=True)

    built = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": sf.WIDTH, "height": sf.HEIGHT},
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
    print(f"\n[done] built {built}/{len(opportunities)} stick-figure shorts -> {VIDEOS_DIR}")


if __name__ == "__main__":
    main()
