"""
make_branding.py  --  Generate a clean, on-brand Etsy shop ICON (and a matching
banner) for OpsIQSystems, using the same free Playwright HTML/CSS -> PNG approach
as the product images. No paid design tools.

Etsy crops the shop icon to a circle, so the icon is full-bleed with the mark
centered. Outputs:
  products/branding/shop_icon.png    (1000x1000, Etsy wants 500x500 min square)
  products/branding/shop_banner.png  (2400x600, Etsy "big banner")
"""
import os

from playwright.sync_api import sync_playwright

OUT = os.path.join("products", "branding")
NAVY = "#0E1B2E"
NAVY2 = "#1B3357"
ACCENT = "#3DD6B0"
ACCENT2 = "#1FA888"
TEXT = "#F4F7FB"
DIM = "#9DB2CE"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif"


def icon_html():
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:500px;height:500px;font-family:{FONT}}}
.stage{{width:500px;height:500px;
  background:radial-gradient(120% 120% at 30% 20%,{NAVY2} 0%,{NAVY} 70%);
  display:flex;flex-direction:column;align-items:center;justify-content:center;color:{TEXT}}}
.bars{{display:flex;align-items:flex-end;gap:14px;height:120px;margin-bottom:26px}}
.bar{{width:34px;border-radius:8px 8px 0 0;background:linear-gradient(180deg,{ACCENT},{ACCENT2})}}
.b1{{height:48px;opacity:.55}}.b2{{height:84px;opacity:.78}}.b3{{height:120px}}
.check{{position:absolute;}}
.mark{{position:relative}}
.tick{{position:absolute;right:-6px;top:-14px;width:60px;height:60px;border-radius:50%;
  background:{ACCENT};display:flex;align-items:center;justify-content:center;
  box-shadow:0 8px 24px rgba(0,0,0,.35)}}
.tick svg{{width:34px;height:34px}}
.word{{font-weight:900;font-size:74px;letter-spacing:2px;line-height:1}}
.word .iq{{color:{ACCENT}}}
.tag{{margin-top:10px;font-size:23px;letter-spacing:7px;color:{DIM};font-weight:700;text-transform:uppercase}}
</style></head><body><div class="stage">
  <div class="mark">
    <div class="bars"><div class="bar b1"></div><div class="bar b2"></div><div class="bar b3"></div></div>
    <div class="tick"><svg viewBox="0 0 24 24" fill="none"><path d="M5 13l4 4L19 7"
      stroke="{NAVY}" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
  </div>
  <div class="word">OPS<span class="iq">IQ</span></div>
  <div class="tag">Systems</div>
</div></body></html>"""


def banner_html():
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1200px;height:300px;font-family:{FONT}}}
.stage{{width:1200px;height:300px;
  background:linear-gradient(110deg,{NAVY} 0%,{NAVY2} 100%);
  display:flex;align-items:center;padding:0 80px;color:{TEXT};position:relative;overflow:hidden}}
.bars{{display:flex;align-items:flex-end;gap:12px;height:120px;margin-right:46px}}
.bar{{width:30px;border-radius:7px 7px 0 0;background:linear-gradient(180deg,{ACCENT},{ACCENT2})}}
.b1{{height:46px;opacity:.55}}.b2{{height:82px;opacity:.78}}.b3{{height:120px}}
.word{{font-weight:900;font-size:60px;letter-spacing:1px}}.word .iq{{color:{ACCENT}}}
.sub{{font-size:26px;color:{DIM};font-weight:600;margin-top:8px;letter-spacing:.3px}}
.glow{{position:absolute;right:-120px;top:-120px;width:420px;height:420px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(61,214,176,.18),transparent)}}
</style></head><body><div class="stage">
  <div class="glow"></div>
  <div class="bars"><div class="bar b1"></div><div class="bar b2"></div><div class="bar b3"></div></div>
  <div><div class="word">OPS<span class="iq">IQ</span> Systems</div>
  <div class="sub">Decision tools that tell you what to do, and why</div></div>
</div></body></html>"""


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, channel="msedge")
        # icon 500x500 @2x -> 1000x1000
        pg = b.new_page(viewport={"width": 500, "height": 500}, device_scale_factor=2)
        pg.set_content(icon_html(), wait_until="load")
        pg.screenshot(path=os.path.join(OUT, "shop_icon.png"))
        # banner 1200x300 @2x -> 2400x600
        pg2 = b.new_page(viewport={"width": 1200, "height": 300}, device_scale_factor=2)
        pg2.set_content(banner_html(), wait_until="load")
        pg2.screenshot(path=os.path.join(OUT, "shop_banner.png"))
        b.close()
    print("[done] ->", os.path.join(OUT, "shop_icon.png"), "and shop_banner.png")


if __name__ == "__main__":
    main()
