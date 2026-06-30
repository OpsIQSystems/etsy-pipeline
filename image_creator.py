"""
image_creator.py
Generates Etsy listing mockup images for each product in opportunities.json.
Uses Claude (Opus) to write punchy marketing copy per product, then renders
that copy into hand-crafted HTML/CSS templates via Playwright (screenshot to
PNG at Etsy's recommended 2000x2500 4:5 ratio). No paid image-gen API needed --
full design control via CSS, same approach a human would get from Canva.
Run independently: python image_creator.py
Output: /products/images/<product>_1.png (cover), _2.png (features), _3.png (insight)
"""

import json
import os
import sys

from playwright.sync_api import sync_playwright

import creator

IMAGES_DIR = os.path.join(creator.PRODUCTS_DIR, "images")

IMAGE_COPY_SYSTEM_PROMPT = """You write Etsy listing cover-image copy for Decision Support System \
spreadsheets sold to small service business owners and landlords. Given a product opportunity, \
output a JSON object with exactly these keys:
- display_name: a short, clean product name for use on image graphics, under 40 characters, NOT \
the full keyword-stuffed Etsy title (e.g. "Crew Profit Tracker" not the full SEO title with pipes)
- headline: a short, punchy hook for the main cover image, under 60 characters, phrased as a \
question or bold claim the target customer would feel seen by (e.g. "Which Crew Is Actually \
Making You Money?")
- subheadline: one supporting sentence, under 90 characters, naming the product category \
(e.g. "AI-Explained Decision Dashboard for Field Service Owners")
- feature_bullets: array of exactly 4 short feature/benefit phrases, each under 50 characters, \
for a secondary "what's inside" image
- sample_insight_quote: one realistic example of the AI-generated verdict text this product \
surfaces, under 140 characters, specific and numeric (e.g. Crew 2 generated 22% more profit than \
Crew 1 this week.). Do NOT include quotation marks in this field -- the raw sentence only, no \
surrounding quote characters.
- badge_text: a short trust/positioning badge, under 30 characters (e.g. "AI-Powered Decision Tool")

Respond with ONLY the JSON object. No prose, no markdown fences."""

PALETTE = {
    "navy": "#16243B",
    "navy_light": "#1F3354",
    "accent": "#3DD6B0",
    "accent_dark": "#1FA888",
    "text_light": "#F4F7FB",
    "text_dim": "#AEC0D8",
}

FONT_STACK = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"


def cover_html(headline: str, subheadline: str, badge_text: str, price, title: str) -> str:
    return f"""
    <html><head><style>
      html, body {{ margin:0; padding:0; width:1000px; height:1250px; }}
      .card {{
        width:1000px; height:1250px; box-sizing:border-box;
        background: linear-gradient(160deg, {PALETTE['navy']} 0%, {PALETTE['navy_light']} 70%);
        font-family: {FONT_STACK}; color:{PALETTE['text_light']};
        display:flex; flex-direction:column; justify-content:space-between;
        padding:70px 64px 90px 64px; position:relative; overflow:hidden;
      }}
      .badge {{
        align-self:flex-start; background:{PALETTE['accent']}; color:{PALETTE['navy']};
        font-weight:700; font-size:22px; padding:10px 22px; border-radius:30px;
        letter-spacing:0.5px;
      }}
      .headline {{ font-size:64px; font-weight:800; line-height:1.12; margin-top:50px; max-width:880px; }}
      .sub {{ font-size:30px; color:{PALETTE['text_dim']}; margin-top:28px; max-width:820px; font-weight:400; }}
      .chart {{
        position:absolute; left:64px; right:64px; bottom:280px; height:280px;
        display:flex; align-items:flex-end; gap:28px; opacity:0.92;
      }}
      .bar {{ flex:1; border-radius:10px 10px 0 0; background:linear-gradient(180deg, {PALETTE['accent']} 0%, {PALETTE['accent_dark']} 100%); }}
      .bar.dim {{ background:linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.08) 100%); }}
      .footer {{ display:flex; align-items:center; justify-content:space-between; border-top:2px solid rgba(255,255,255,0.15); padding-top:34px; position:relative; z-index:2; }}
      .price {{ font-size:46px; font-weight:800; color:{PALETTE['accent']}; }}
      .tag {{ font-size:24px; color:{PALETTE['text_dim']}; }}
    </style></head>
    <body>
      <div class="card">
        <div>
          <div class="badge">{badge_text}</div>
          <div class="headline">{headline}</div>
          <div class="sub">{subheadline}</div>
        </div>
        <div class="chart">
          <div class="bar dim" style="height:45%"></div>
          <div class="bar" style="height:78%"></div>
          <div class="bar dim" style="height:38%"></div>
          <div class="bar" style="height:92%"></div>
          <div class="bar dim" style="height:55%"></div>
          <div class="bar" style="height:70%"></div>
        </div>
        <div class="footer">
          <div class="price">${price}</div>
          <div class="tag">Instant Digital Download &middot; Google Sheets &amp; Excel</div>
        </div>
      </div>
    </body></html>
    """


def features_html(title: str, feature_bullets: list) -> str:
    items = "".join(
        f"""<div class="item">
              <div class="check">&#10003;</div>
              <div class="text">{b}</div>
            </div>"""
        for b in feature_bullets
    )
    return f"""
    <html><head><style>
      html, body {{ margin:0; padding:0; width:1000px; height:1250px; }}
      .card {{
        width:1000px; height:1250px; box-sizing:border-box;
        background:{PALETTE['text_light']}; font-family:{FONT_STACK};
        display:flex; flex-direction:column; justify-content:center; padding:80px 70px;
      }}
      .kicker {{ font-size:24px; font-weight:700; color:{PALETTE['accent_dark']}; letter-spacing:1px; text-transform:uppercase; }}
      .title {{ font-size:42px; font-weight:800; color:{PALETTE['navy']}; margin-top:14px; margin-bottom:70px; max-width:860px; line-height:1.2; }}
      .item {{ display:flex; align-items:flex-start; gap:24px; margin-bottom:56px; }}
      .check {{
        flex-shrink:0; width:52px; height:52px; border-radius:50%; background:{PALETTE['accent']};
        color:{PALETTE['navy']}; font-size:28px; font-weight:800; display:flex; align-items:center; justify-content:center;
      }}
      .text {{ font-size:34px; font-weight:600; color:{PALETTE['navy']}; line-height:1.35; padding-top:6px; }}
      .footer {{ margin-top:50px; font-size:22px; color:#7A8AA0; border-top:2px solid #E2E8F0; padding-top:30px; }}
    </style></head>
    <body>
      <div class="card">
        <div class="kicker">What's Inside</div>
        <div class="title">{title}</div>
        {items}
        <div class="footer">Instant Digital Download &middot; Works in Google Sheets &amp; Excel</div>
      </div>
    </body></html>
    """


def insight_html(sample_insight_quote: str, badge_text: str) -> str:
    return f"""
    <html><head><style>
      html, body {{ margin:0; padding:0; width:1000px; height:1250px; }}
      .card {{
        width:1000px; height:1250px; box-sizing:border-box;
        background: linear-gradient(160deg, {PALETTE['navy_light']} 0%, {PALETTE['navy']} 100%);
        font-family:{FONT_STACK}; color:{PALETTE['text_light']};
        display:flex; flex-direction:column; align-items:center; justify-content:center;
        padding:90px 80px; text-align:center;
      }}
      .label {{ font-size:22px; font-weight:700; color:{PALETTE['accent']}; letter-spacing:2px; text-transform:uppercase; margin-bottom:40px; }}
      .quote {{
        font-size:44px; font-weight:700; line-height:1.4; max-width:820px;
        background:rgba(255,255,255,0.06); border-left:6px solid {PALETTE['accent']};
        padding:40px 44px; border-radius:8px;
      }}
      .footer {{ margin-top:56px; font-size:24px; color:{PALETTE['text_dim']}; }}
    </style></head>
    <body>
      <div class="card">
        <div class="label">This Is What The AI Insight Layer Tells You</div>
        <div class="quote">&ldquo;{sample_insight_quote}&rdquo;</div>
        <div class="footer">{badge_text} &middot; Not Just A Spreadsheet</div>
      </div>
    </body></html>
    """


def render_html_to_png(page, html: str, path: str):
    page.set_content(html, wait_until="load")
    page.screenshot(path=path)


def main():
    with open(creator.INPUT_FILE, "r", encoding="utf-8") as f:
        opportunities = json.load(f)

    os.makedirs(IMAGES_DIR, exist_ok=True)
    client = creator.load_anthropic_client()

    print(f"[*] Generating mockup images for {len(opportunities)} products...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page(viewport={"width": 1000, "height": 1250}, device_scale_factor=2)

        built = 0
        for idx, opportunity in enumerate(opportunities, start=1):
            title = opportunity.get("suggested_etsy_title", f"opportunity_{idx}")
            price = opportunity.get("suggested_price", "")
            fname_base = creator.safe_filename(title)
            print(f"[Image set {idx}/{len(opportunities)}] {title}")

            try:
                print("  [-] Requesting image copy from Claude...")
                copy = creator.call_claude_json(
                    client, IMAGE_COPY_SYSTEM_PROMPT,
                    f"Write cover-image copy for this opportunity:\n{json.dumps(opportunity, indent=2)}",
                    max_tokens=1024,
                )

                cover_path = os.path.join(IMAGES_DIR, f"{fname_base}_1_cover.png")
                features_path = os.path.join(IMAGES_DIR, f"{fname_base}_2_features.png")
                insight_path = os.path.join(IMAGES_DIR, f"{fname_base}_3_insight.png")

                display_name = copy.get("display_name") or title
                clean_quote = copy.get("sample_insight_quote", "").strip().strip('"').strip("'")

                render_html_to_png(page, cover_html(
                    copy.get("headline", title), copy.get("subheadline", ""),
                    copy.get("badge_text", "Decision Support Tool"), price, display_name), cover_path)

                render_html_to_png(page, features_html(
                    display_name, copy.get("feature_bullets", [])), features_path)

                render_html_to_png(page, insight_html(
                    clean_quote, copy.get("badge_text", "")), insight_path)

                built += 1
                print(f"  [+] Saved 3 images -> {IMAGES_DIR}\\{fname_base}_*.png\n")

            except Exception as item_err:
                print(f"  [error] Failed to build images for '{title}': {item_err}\n")
                continue

        browser.close()

    print(f"[done] Built image sets for {built}/{len(opportunities)} products.")


if __name__ == "__main__":
    main()
