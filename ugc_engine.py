"""
ugc_engine.py  --  Shared, self-built (no paid services) video tooling.

Two responsibilities:
  1. render_scene(): turn an HTML/CSS scene into a 1080x1920 PNG via Playwright.
  2. assemble(): stitch a list of (png, seconds, motion) into a vertical MP4
     with gentle Ken-Burns zoom + crossfades, using moviepy 2.x + the ffmpeg
     binary bundled by imageio-ffmpeg. No ImageMagick, no external services.

Vertical 1080x1920 = the native TikTok / YouTube Shorts / Reels canvas.
All on-screen text is baked into the HTML scenes (avoids font/ImageMagick deps).
"""
import base64
import os

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
from moviepy.audio.AudioClip import CompositeAudioClip
from moviepy.video.fx import CrossFadeIn, Resize

WIDTH, HEIGHT = 1080, 1920

PALETTE = {
    "navy": "#0E1B2E",
    "navy2": "#16273F",
    "accent": "#3DD6B0",
    "accent2": "#1FA888",
    "amber": "#F5B400",
    "text": "#F4F7FB",
    "dim": "#9DB2CE",
}

FONT_STACK = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
              "'Helvetica Neue',Arial,sans-serif")


def _frame(inner_css, body_html, bg=None):
    bg = bg or f"linear-gradient(160deg,{PALETTE['navy']} 0%,{PALETTE['navy2']} 100%)"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden;font-family:{FONT_STACK};}}
.stage{{width:{WIDTH}px;height:{HEIGHT}px;background:{bg};color:{PALETTE['text']};
  display:flex;flex-direction:column;justify-content:center;align-items:center;
  text-align:center;padding:120px 90px;position:relative;}}
.kicker{{font-size:38px;letter-spacing:6px;text-transform:uppercase;color:{PALETTE['accent']};
  font-weight:800;margin-bottom:40px;}}
.big{{font-size:104px;font-weight:900;line-height:1.04;letter-spacing:-1px;}}
.mid{{font-size:64px;font-weight:800;line-height:1.15;}}
.sub{{font-size:46px;font-weight:500;color:{PALETTE['dim']};line-height:1.35;margin-top:36px;}}
.accent{{color:{PALETTE['accent']};}}
.amber{{color:{PALETTE['amber']};}}
.pill{{display:inline-block;background:{PALETTE['accent']};color:{PALETTE['navy']};
  font-weight:900;font-size:44px;padding:22px 46px;border-radius:60px;margin-top:60px;}}
.footer{{position:absolute;bottom:90px;left:0;right:0;font-size:40px;color:{PALETTE['dim']};
  font-weight:600;}}
{inner_css}
</style></head><body><div class="stage">{body_html}</div></body></html>"""


def hook_scene(hook):
    body = f'<div class="kicker">For service businesses</div><div class="big">{hook}</div>'
    return _frame("", body)


def problem_scene(line):
    body = (f'<div class="kicker amber">The problem</div>'
            f'<div class="mid">{line}</div>')
    return _frame("", body,
                  bg=f"linear-gradient(160deg,#2A1530 0%,{PALETTE['navy2']} 100%)")


def _data_uri(image_path):
    # Inline as base64 -- file:// resources are blocked from a set_content page.
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def solution_scene(line, image_path):
    src = _data_uri(image_path)
    inner = """.shot{width:760px;border-radius:28px;box-shadow:0 30px 90px rgba(0,0,0,.55);
      border:1px solid rgba(255,255,255,.08);margin-bottom:50px;}"""
    body = (f'<img class="shot" src="{src}"/>'
            f'<div class="mid">{line}</div>')
    return _frame(inner, body)


def insight_scene(quote):
    inner = """.card{background:rgba(61,214,176,.12);border:2px solid #3DD6B0;border-radius:30px;
      padding:70px 60px;}.q{font-size:58px;font-weight:700;line-height:1.3;}"""
    body = (f'<div class="kicker">Built-in AI insight</div>'
            f'<div class="card"><div class="q">{quote}</div></div>')
    return _frame(inner, body)


def cta_scene(cta, price, shop):
    body = (f'<div class="kicker accent">Get it on Etsy</div>'
            f'<div class="big">{cta}</div>'
            f'<div class="pill">{price}</div>'
            f'<div class="footer">{shop}</div>')
    return _frame("", body)


def render_scene(page, html, out_path):
    page.set_content(html, wait_until="load")
    page.screenshot(path=out_path)


def assemble(scenes, out_path, fps=30, xfade=0.5, tail=0.45):
    """scenes: list of either
         (png_path, duration_seconds, zoom_bool)                 -> silent, or
         (png_path, min_duration, zoom_bool, audio_path_or_None) -> voiced.
    When an audio path is given, the scene duration becomes
    max(min_duration, narration_length + tail) and the narration is laid under
    the scene. Audio is concatenated to match the (overlapping) video timeline."""
    clips = []
    audio_segments = []
    timeline = 0.0
    has_audio = False
    for i, scene in enumerate(scenes):
        if len(scene) == 4:
            png, min_dur, zoom, audio = scene
        else:
            png, min_dur, zoom = scene
            audio = None

        narr = None
        dur = min_dur
        if audio and os.path.exists(audio):
            narr = AudioFileClip(audio)
            dur = max(min_dur, narr.duration + tail)
            has_audio = True

        clip = ImageClip(png).with_duration(dur)
        if zoom:
            clip = clip.with_effects([Resize(lambda t, d=dur: 1.0 + 0.06 * (t / d))])
        if i > 0:
            clip = clip.with_effects([CrossFadeIn(xfade)])
        clips.append(clip)

        # place narration at this scene's start on the global timeline; the
        # -xfade overlap means each scene begins xfade earlier than its raw sum
        start = timeline - (xfade if i > 0 else 0)
        if narr is not None:
            audio_segments.append(narr.with_start(max(0.0, start) + 0.12))
        timeline = (start if i > 0 else 0) + dur

    video = concatenate_videoclips(clips, method="compose", padding=-xfade)
    if has_audio and audio_segments:
        video = video.with_audio(CompositeAudioClip(audio_segments))
    video.write_videofile(
        out_path, fps=fps, codec="libx264",
        audio=has_audio, audio_codec="aac" if has_audio else None,
        preset="medium", ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None,
    )
    video.close()
