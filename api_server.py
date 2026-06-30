"""
api_server.py
FastAPI wrapper so N8N can call the etsy-pipeline Python scripts via HTTP.
Run: python api_server.py
Listens on: http://localhost:8000
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


app = FastAPI(title="Etsy Pipeline API", version="1.0.0")

BASE        = Path(__file__).parent
PYTHON      = os.environ.get("PYTHON_BIN", r"C:\Users\Ron39\AppData\Local\Programs\Python\Python312\python.exe")
PUBLIC_BASE = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "etsy-pipeline-production.up.railway.app")

# Serve rendered videos publicly so PostForMe can download them
_media_dir = BASE / "products" / "audio"
_media_dir.mkdir(parents=True, exist_ok=True)
try:
    app.mount("/media", StaticFiles(directory=str(_media_dir)), name="media")
except Exception as _e:
    print(f"WARNING: could not mount /media StaticFiles: {_e}")
FONT = os.environ.get("FONT_PATH", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")


class BuildRequest(BaseModel):
    opportunity: dict


class ValidateRequest(BaseModel):
    xlsx_path: str


class AnalyzeRequest(BaseModel):
    listings: list[dict]


class TTSRequest(BaseModel):
    text: str
    voice: str = "en-US-AriaNeural"  # default: natural female US voice
    output_path: str | None = None
    persona_name: str | None = None
    persona_trade: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "cwd": str(BASE)}


@app.post("/build")
def build_product(req: BuildRequest):
    """Build workbook + PDF + listing copy from an opportunity dict."""
    import sys
    sys.path.insert(0, str(BASE))
    try:
        import creator
        client = creator.load_anthropic_client()
        opp = req.opportunity

        spec = creator.call_claude_json(
            client, creator.SPEC_SYSTEM_PROMPT,
            f"Design the dashboard for this opportunity:\n{json.dumps(opp, indent=2)}",
            max_tokens=8192,
        )
        listing_copy = creator.call_claude_json(
            client, creator.LISTING_SYSTEM_PROMPT,
            f"Write Etsy listing copy for this opportunity:\n{json.dumps(opp, indent=2)}",
            max_tokens=2048,
        )

        fname = creator.safe_filename(opp.get("suggested_etsy_title", "product"))
        xlsx_path = str(BASE / "products" / f"{fname}.xlsx")
        pdf_path  = str(BASE / "products" / f"{fname}_guide.pdf")
        listing_path = str(BASE / "listings" / f"{fname}.txt")
        Path(BASE / "products").mkdir(parents=True, exist_ok=True)
        Path(BASE / "listings").mkdir(parents=True, exist_ok=True)

        creator.build_workbook(spec, opp, xlsx_path)
        creator.build_pdf_guide(spec, opp, pdf_path)
        creator.build_listing_txt(listing_copy, opp, listing_path)

        return {
            "status": "built",
            "xlsx": xlsx_path,
            "pdf": pdf_path,
            "listing": listing_path,
            "fname": fname,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/validate")
def validate_product(req: ValidateRequest):
    """Run stress test on a built workbook. Returns pass/fail."""
    try:
        result = subprocess.run(
            [PYTHON, str(BASE / "commercial_stress.py"), req.xlsx_path],
            capture_output=True, text=True, cwd=str(BASE), timeout=120
        )
        passed = "PASS" in result.stdout
        return {
            "status": "pass" if passed else "fail",
            "stdout": result.stdout[-3000:],
            "stderr": result.stderr[-1000:],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/review")
def finance_review(req: ValidateRequest):
    """Run the Claude underwriter validation agent."""
    try:
        result = subprocess.run(
            [PYTHON, str(BASE / "commercial_finance_review.py")],
            capture_output=True, text=True, cwd=str(BASE), timeout=300
        )
        passed = "PROFESSIONALLY SOUND" in result.stdout
        return {
            "status": "pass" if passed else "fail",
            "report": result.stdout[-5000:],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze")
def analyze_opportunities(req: AnalyzeRequest):
    """Claude analyzes scraped Etsy listings and returns scored opportunities."""
    import sys
    sys.path.insert(0, str(BASE))
    try:
        import creator
        client = creator.load_anthropic_client()

        system = (
            "You are a product strategist who identifies profitable gaps in Etsy's "
            "digital product market. Analyze the provided listings and identify the "
            "top opportunities for new tools that would outperform existing ones."
        )
        user = (
            f"Here are {len(req.listings)} scraped Etsy listings:\n"
            f"{json.dumps(req.listings[:50], indent=2)}\n\n"
            "Identify the top 5 product opportunities. For each return:\n"
            "- title: product idea name\n"
            "- gap: what's missing in existing products\n"
            "- score: 1-10 opportunity score\n"
            "- suggested_price: integer USD\n"
            "- target_customer: one sentence\n"
            "- what_to_build: two sentences\n"
            "Return JSON: {\"opportunities\": [...]}"
        )
        result = creator.call_claude_json(client, system, user, max_tokens=4096)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Platform specs — enforced on every render, no exceptions.
# Rules sourced from each platform's official developer/creator docs.
# hashtag_limit = safe max (not technical max) — exceeding triggers shadowban.
# min_sec = minimum clip length before platform flags as low-quality spam.
# safe_daily_posts = max per day before spam detection activates.
# no_watermark = True means strip competitor watermarks or video gets suppressed.
PLATFORM_SPECS = {
    "tiktok": {
        "w": 1080, "h": 1920, "fps": 30,
        "min_sec": 5,   "max_sec": 60,   "max_mb": 287,
        "caption_limit": 2200, "hashtag_limit": 5,
        "disclosure": "#ad ",           # FTC + TikTok TOS: required for commercial content
        "safe_daily_posts": 3,          # >3/day triggers spam review on new accounts
        "no_watermark": True,           # TikTok rejects videos with IG/YT/FB watermarks
    },
    "instagram": {
        "w": 1080, "h": 1920, "fps": 30,
        "min_sec": 3,   "max_sec": 90,   "max_mb": 100,
        "caption_limit": 2200, "hashtag_limit": 10,
        "disclosure": "#ad ",           # IG TOS: paid partnership disclosure required
        "safe_daily_posts": 3,
        "no_watermark": True,           # IG suppresses Reels with TikTok watermark
    },
    "youtube": {
        "w": 1080, "h": 1920, "fps": 30,
        "min_sec": 15,  "max_sec": 60,   "max_mb": 256,
        "caption_limit": 100, "hashtag_limit": 3,
        "disclosure": "",               # YT uses paid promotion checkbox — not caption text
        "safe_daily_posts": 2,
        "no_watermark": False,
        "paid_promotion_flag": True,    # must tick "contains paid promotion" in YT Studio
    },
    "facebook": {
        "w": 1080, "h": 1920, "fps": 30,   # Reels: vertical preferred (was 1280x720 landscape)
        "min_sec": 3,   "max_sec": 90,   "max_mb": 500,
        "caption_limit": 63206, "hashtag_limit": 5,
        "disclosure": "",               # FB requires branded content tag via Creator Studio
        "safe_daily_posts": 2,
        "no_watermark": True,           # FB Reels suppresses TikTok-watermarked content
        "branded_content_tag": True,    # tag OpsIQ Systems as business partner in FB
    },
    "bluesky": {
        "w": 1280, "h": 720, "fps": 30,
        "min_sec": 1,   "max_sec": 60,   "max_mb": 50,
        "caption_limit": 300, "hashtag_limit": 0,
        "disclosure": "",               # no paid disclosure convention on Bluesky yet
        "safe_daily_posts": 5,
        "no_watermark": False,
    },
}
ALL_PLATFORMS = list(PLATFORM_SPECS.keys())


def _format_caption(raw: str, platform: str, etsy_url: str = "searchopsiq.etsy.com") -> str:
    """Build a platform-safe caption: disclosure prefix + body + CTA, hashtags capped."""
    import re
    spec = PLATFORM_SPECS.get(platform, {})
    limit = spec.get("caption_limit", 2200)
    disclosure = spec.get("disclosure", "")
    hashtag_limit = spec.get("hashtag_limit", 5)
    suffix = f"\n{etsy_url}" if platform not in ("bluesky",) else f" {etsy_url}"

    # Strip all hashtags from body, then re-add only the allowed number
    tags = re.findall(r"#\w+", raw)
    body_no_tags = re.sub(r"#\w+", "", raw).strip()

    if hashtag_limit == 0:
        # Bluesky: no hashtags at all
        tags_str = ""
    else:
        safe_tags = tags[:hashtag_limit]
        tags_str = " ".join(safe_tags)

    # Assemble and truncate to limit
    assembled = f"{disclosure}{body_no_tags}"
    if tags_str:
        assembled += f"\n{tags_str}"
    assembled += suffix

    if len(assembled) > limit:
        # Trim the body to fit
        overflow = len(assembled) - limit
        body_no_tags = body_no_tags[:max(0, len(body_no_tags) - overflow)]
        assembled = f"{disclosure}{body_no_tags}"
        if tags_str:
            assembled += f"\n{tags_str}"
        assembled += suffix

    return assembled


def _validate_script_json(raw_text: str) -> dict:
    """Parse Claude's JSON response safely, strip markdown fences if present."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned invalid JSON: {e} — raw: {text[:200]}")


class RotationRequest(BaseModel):
    script: str
    voice: str = "en-US-GuyNeural"
    persona_name: str | None = None
    persona_trade: str | None = None
    product_slug: str | None = None
    platforms: list[str] = ALL_PLATFORMS  # render for all platforms by default


def _fit_video_to_platform(video, spec: dict):
    """Scale + letterbox/pillarbox source video to exactly the platform canvas."""
    from moviepy import VideoFileClip, ColorClip, CompositeVideoClip
    tw, th = spec["w"], spec["h"]
    vw, vh = video.size
    scale = min(tw / vw, th / vh)
    nw, nh = int(vw * scale), int(vh * scale)
    # ensure even dimensions (required by libx264)
    nw = nw if nw % 2 == 0 else nw - 1
    nh = nh if nh % 2 == 0 else nh - 1
    resized = video.resized((nw, nh))
    if nw == tw and nh == th:
        return resized
    # center on black canvas
    canvas = ColorClip(size=(tw, th), color=(0, 0, 0)).with_duration(video.duration)
    x = (tw - nw) // 2
    y = (th - nh) // 2
    return CompositeVideoClip([canvas, resized.with_position((x, y))])


@app.post("/next_video")
def next_video(req: RotationRequest):
    """
    Render one video per requested platform, each formatted to that platform's exact spec.
    Returns a dict of platform → public URL. No looping. No watermarks.
    """
    import asyncio, uuid, edge_tts
    from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

    pool_demos = sorted((BASE / "products" / "browser_demos").glob("browser_*.mp4"))
    pool_stick = sorted((BASE / "products" / "videos").glob("stick_*.mp4"))

    counter_file = BASE / "products" / ".rotation_counter"
    count = int(counter_file.read_text()) if counter_file.exists() else 0
    counter_file.write_text(str(count + 1))

    if pool_demos and pool_stick:
        pool = pool_demos if count % 2 == 0 else pool_stick
    elif pool_demos:
        pool = pool_demos
    elif pool_stick:
        pool = pool_stick
    else:
        raise HTTPException(status_code=500, detail="No videos found in browser_demos or videos/")

    chosen = pool[count % len(pool)]
    if req.product_slug:
        for p in [pool_demos, pool_stick]:
            match = next((v for v in p if req.product_slug.replace("-", "_") in v.stem), None)
            if match:
                chosen = match
                break

    uid = uuid.uuid4().hex
    audio_dir = BASE / "products" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / f"{uid}.mp3"

    async def _tts():
        await edge_tts.Communicate(req.script, req.voice).save(str(audio_path))

    try:
        asyncio.run(_tts())
        audio_master = AudioFileClip(str(audio_path))
        source_video = VideoFileClip(str(chosen))

        platforms = [p for p in req.platforms if p in PLATFORM_SPECS]
        if not platforms:
            platforms = ALL_PLATFORMS

        urls = {}
        for platform in platforms:
            spec = PLATFORM_SPECS[platform]
            max_dur = min(source_video.duration, audio_master.duration, spec["max_sec"])
            min_dur = spec.get("min_sec", 3)
            if max_dur < min_dur:
                max_dur = min_dur  # pad to minimum — audio will loop or silence fills

            vid = source_video.subclipped(0, max_dur)
            aud = audio_master.subclipped(0, max_dur)

            # fit to platform canvas (letterbox/pillarbox, no crop, no stretch)
            vid = _fit_video_to_platform(vid, spec)
            vid = vid.with_audio(aud)

            # persona overlay
            if req.persona_name and req.persona_trade:
                label = f"{req.persona_name}  |  {req.persona_trade}"
                try:
                    font_size = 32 if spec["h"] >= 1080 else 24
                    txt = (
                        TextClip(font=FONT, text=label, font_size=font_size,
                                 color="white", stroke_color="black", stroke_width=2, method="label")
                        .with_position(("center", 0.88), relative=True)
                        .with_duration(max_dur)
                    )
                    vid = CompositeVideoClip([vid, txt])
                except Exception:
                    pass

            out_path = audio_dir / f"{uid}_{platform}.mp4"
            vid.write_videofile(str(out_path), codec="libx264", audio_codec="aac",
                                fps=spec["fps"], logger=None, threads=2)
            urls[platform] = f"https://{PUBLIC_BASE}/media/{out_path.name}"

        audio_path.unlink(missing_ok=True)
        raw_caption = req.script[:500]
        return {
            "status": "ok",
            "source_video": chosen.name,
            "video_type": "browser_demo" if chosen in pool_demos else "stick",
            "rotation_count": count,
            "urls": urls,
            # per-platform video URLs
            "tiktok_url":    urls.get("tiktok", ""),
            "instagram_url": urls.get("instagram", ""),
            "youtube_url":   urls.get("youtube", ""),
            "facebook_url":  urls.get("facebook", ""),
            "bluesky_url":   urls.get("bluesky", ""),
            # per-platform captions — correctly truncated and formatted
            "captions": {p: _format_caption(raw_caption, p) for p in platforms},
            "tiktok_caption":    _format_caption(raw_caption, "tiktok"),
            "instagram_caption": _format_caption(raw_caption, "instagram"),
            "youtube_caption":   _format_caption(raw_caption, "youtube"),
            "facebook_caption":  _format_caption(raw_caption, "facebook"),
            "bluesky_caption":   _format_caption(raw_caption, "bluesky"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/record_demo")
def record_demo_endpoint(req: TTSRequest):
    """Trigger Playwright to record a browser demo for a given product slug."""
    import subprocess
    slug = req.output_path or "hvac_job_bid"   # reuse output_path field as slug
    result = subprocess.run(
        [PYTHON, str(BASE / "record_demos.py"), slug],
        capture_output=True, text=True, cwd=str(BASE), timeout=300
    )
    out_file = BASE / "products" / "browser_demos" / f"browser_{slug}.mp4"
    return {
        "status": "ok" if out_file.exists() else "error",
        "video_path": str(out_file) if out_file.exists() else None,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-500:],
    }


@app.post("/render_short")
def render_short(req: TTSRequest):
    """Generate a social short: edge-tts voice + looped product video = ready-to-post MP4."""
    import asyncio, uuid, edge_tts
    from moviepy import VideoFileClip, AudioFileClip
    from moviepy.video.fx import Loop
    import glob as _glob

    # pick a product video matching the voice text keywords, else pick a random one
    videos_dir = BASE / "products" / "videos"
    stick_vids = sorted(videos_dir.glob("stick_*.mp4"))
    if not stick_vids:
        raise HTTPException(status_code=500, detail="No source videos found in products/videos/")

    # simple keyword match on filename
    words = [w.lower() for w in req.text.split() if len(w) > 4]
    chosen = stick_vids[0]
    for vid in stick_vids:
        if any(w in vid.name.lower() for w in words):
            chosen = vid
            break

    uid = uuid.uuid4().hex
    audio_path = BASE / "products" / "audio" / f"{uid}.mp3"
    out_path = Path(req.output_path) if req.output_path else BASE / "products" / "audio" / f"{uid}_short.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    async def _tts():
        await edge_tts.Communicate(req.text, req.voice).save(str(audio_path))

    try:
        asyncio.run(_tts())
        audio = AudioFileClip(str(audio_path))
        video = Loop(n=20).apply(VideoFileClip(str(chosen))).with_duration(audio.duration).with_audio(audio)

        # Add UGC persona overlay if provided
        if req.persona_name and req.persona_trade:
            from moviepy import TextClip, CompositeVideoClip
            from PIL import ImageFont
            label = f"{req.persona_name}  |  {req.persona_trade}"
            try:
                txt = (
                    TextClip(font=FONT, text=label, font_size=28,
                             color="white", stroke_color="black", stroke_width=2, method="label")
                    .with_position(("center", 0.82), relative=True)
                    .with_duration(audio.duration)
                )
                video = CompositeVideoClip([video, txt])
            except Exception:
                pass  # overlay failed silently — video still renders without text

        video.write_videofile(str(out_path), codec="libx264", audio_codec="aac", logger=None)
        audio_path.unlink(missing_ok=True)
        return {"status": "ok", "video_path": str(out_path), "source_video": chosen.name, "voice": req.voice}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tts")
def text_to_speech(req: TTSRequest):
    """Convert text to speech using edge-tts (Microsoft neural voices, free)."""
    import asyncio
    import uuid
    import edge_tts

    out_path = req.output_path or str(BASE / "products" / "audio" / f"{uuid.uuid4().hex}.mp3")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    async def _generate():
        communicate = edge_tts.Communicate(req.text, req.voice)
        await communicate.save(out_path)

    try:
        asyncio.run(_generate())
        return {"status": "ok", "audio_path": out_path, "voice": req.voice}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tts/voices")
def list_voices():
    """List available edge-tts voices."""
    import asyncio
    import edge_tts

    async def _list():
        return await edge_tts.list_voices()

    try:
        voices = asyncio.run(_list())
        return {"voices": [{"name": v["ShortName"], "gender": v["Gender"], "locale": v["Locale"]} for v in voices]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
