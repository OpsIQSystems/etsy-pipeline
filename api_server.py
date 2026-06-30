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


# ---------------------------------------------------------------------------
# /render_video  — 3-type B-roll flash-cut renderer with Pexels footage
# ---------------------------------------------------------------------------

PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

# Search terms per video type and trade — pulled from script keywords
TRADE_BROLL_TERMS = {
    "hvac": ["HVAC technician", "air conditioning repair", "hvac contractor"],
    "plumbing": ["plumber working", "pipe installation", "plumbing repair"],
    "electrical": ["electrician working", "electrical panel", "wiring installation"],
    "roofing": ["roofer working", "roof installation", "roofing contractor"],
    "construction": ["construction worker", "building contractor", "construction site"],
    "default": ["contractor working", "tradesman job site", "construction crew"],
}

HUMOR_BROLL_TERMS = [
    "construction worker funny moment",
    "tradesman job site",
    "contractor tools",
    "plumber working",
    "electrician working",
    "roofer working",
]


def _pexels_fetch_videos(query: str, count: int = 4, orientation: str = "portrait") -> list[str]:
    """Fetch up to `count` Pexels video download URLs for a search query."""
    import requests
    if not PEXELS_KEY:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": query, "per_page": count * 2, "orientation": orientation, "size": "medium"},
            timeout=15,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        urls = []
        for v in videos:
            # prefer HD file, fall back to SD
            files = sorted(v.get("video_files", []), key=lambda f: f.get("width", 0), reverse=True)
            for f in files:
                if f.get("link") and f.get("width", 0) >= 720:
                    urls.append(f["link"])
                    break
            if len(urls) >= count:
                break
        return urls
    except Exception:
        return []


def _download_clip(url: str, dest: Path) -> bool:
    import requests
    try:
        r = requests.get(url, timeout=30, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        return True
    except Exception:
        return False


def _flash_cut_broll(clip_paths: list[Path], total_dur: float, spec: dict):
    """Stack B-roll clips in fast cuts to fill total_dur seconds, fitted to platform spec.
    Returns (composed_clip, source_clips_to_close_after_render).
    Caller MUST close source_clips after write_videofile completes.
    """
    from moviepy import VideoFileClip, concatenate_videoclips, ColorClip
    segments = []
    source_clips = []
    remaining = total_dur
    idx = 0
    while remaining > 0.5 and idx < len(clip_paths) * 3:
        src = clip_paths[idx % len(clip_paths)]
        try:
            clip = VideoFileClip(str(src))
            cut_len = min(clip.duration, min(remaining, 3.5))
            if cut_len < 0.5:
                clip.close()
                idx += 1
                continue
            start = max(0, (clip.duration - cut_len) / 2)
            seg = _fit_video_to_platform(clip.subclipped(start, start + cut_len), spec)
            seg = seg.without_audio()
            segments.append(seg)
            source_clips.append(clip)
            remaining -= cut_len
        except Exception:
            pass
        idx += 1
    if not segments:
        return ColorClip(size=(spec["w"], spec["h"]), color=(0, 0, 0)).with_duration(total_dur), []
    return concatenate_videoclips(segments, method="compose"), source_clips


class RenderVideoRequest(BaseModel):
    script: str
    video_type: str = "humor"          # "humor" | "ugc_product" | "ugc_casestudy"
    hook: str | None = None
    persona_name: str | None = None
    persona_trade: str | None = None
    product_name: str | None = None
    case_study_data: dict | None = None  # e.g. {"job_value": 14200, "profit": 2800}
    voice: str = "en-US-GuyNeural"
    platforms: list[str] = ALL_PLATFORMS
    broll_query: str | None = None     # override Pexels search term


_jobs: dict = {}  # job_id → {"status": "pending"|"done"|"error", "result": ...}


def _run_render_job(job_id: str, req: "RenderVideoRequest"):
    """Runs in a background thread. Updates _jobs[job_id] when done."""
    try:
        result = _render_video_sync(req)
        _jobs[job_id] = {"status": "done", "result": result}
    except Exception as e:
        _jobs[job_id] = {"status": "error", "error": str(e)}


@app.get("/render_video/{job_id}")
def render_video_status(job_id: str):
    """Poll for render job completion."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/render_video")
def render_video(req: RenderVideoRequest, background_tasks=None):
    """
    Flash-cut B-roll renderer. 3 video types:
      humor       — scraped trade humor, pure entertainment, no product mention
      ugc_product — first-person story: pain point → Etsy tool solved it
      ugc_casestudy — shows real numbers / simulated tool use with case study data
    Starts render in background. Returns job_id. Poll GET /render_video/{job_id} for result.
    """
    import uuid, threading
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "pending"}
    t = threading.Thread(target=_run_render_job, args=(job_id, req), daemon=True)
    t.start()
    return {"status": "pending", "job_id": job_id, "poll_url": f"https://{PUBLIC_BASE}/render_video/{job_id}"}


def _get_word_timestamps(text: str, voice: str) -> tuple[bytes, list[dict]]:
    """Run edge-tts and collect audio bytes + per-word timestamps."""
    import asyncio, edge_tts

    audio_chunks: list[bytes] = []
    words: list[dict] = []

    async def _stream():
        comm = edge_tts.Communicate(text, voice)
        async for event in comm.stream():
            if event["type"] == "audio":
                audio_chunks.append(event["data"])
            elif event["type"] == "WordBoundary":
                words.append({
                    "word":  event["text"],
                    "start": event["offset"] / 10_000_000,
                    "end":   (event["offset"] + event["duration"]) / 10_000_000,
                })

    asyncio.run(_stream())
    return b"".join(audio_chunks), words


def _build_caption_clips(words: list[dict], max_dur: float, spec: dict) -> list:
    """
    TikTok-style animated captions: 3-word groups, word-by-word yellow highlight.
    Renders each state as a full-frame RGB image (no alpha compositing issues).
    Dark pill background behind text ensures visibility on any footage.
    """
    from PIL import Image, ImageDraw, ImageFont
    from moviepy import ImageClip
    import numpy as np

    if not words:
        return []

    W, H = spec["w"], spec["h"]
    FONT_SIZE = max(80, W // 12)   # big — TikTok style
    STROKE = 5
    PAD_X, PAD_Y = 28, 18
    WORD_GAP = 16
    GROUP = 3

    try:
        pil_font = ImageFont.truetype(FONT, FONT_SIZE)
    except Exception:
        pil_font = ImageFont.load_default()

    def _measure(text):
        dummy = Image.new("RGB", (1, 1))
        d = ImageDraw.Draw(dummy)
        bb = d.textbbox((0, 0), text, font=pil_font, stroke_width=STROKE)
        return bb[2] - bb[0], bb[3] - bb[1]

    def _render_group_frame(group_words, highlight_idx):
        """Render a full W×H frame with the caption group, one word highlighted."""
        sizes = [_measure(w["word"]) for w in group_words]
        total_text_w = sum(s[0] for s in sizes) + WORD_GAP * (len(sizes) - 1)
        text_h = max(s[1] for s in sizes)

        pill_w = total_text_w + PAD_X * 2
        pill_h = text_h + PAD_Y * 2

        # Full frame, black background (will be used as overlay mask via RGBA)
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Caption zone: 65% down the frame
        cap_cx = W // 2
        cap_cy = int(H * 0.65)
        pill_x0 = cap_cx - pill_w // 2
        pill_y0 = cap_cy - pill_h // 2
        pill_x1 = pill_x0 + pill_w
        pill_y1 = pill_y0 + pill_h

        # Dark semi-transparent background pill
        draw.rounded_rectangle(
            [pill_x0, pill_y0, pill_x1, pill_y1],
            radius=pill_h // 2,
            fill=(0, 0, 0, 185)
        )

        # Draw each word
        x = pill_x0 + PAD_X
        y = pill_y0 + PAD_Y
        for wi, w in enumerate(group_words):
            color = (255, 220, 0) if wi == highlight_idx else (255, 255, 255)
            draw.text(
                (x, y), w["word"], font=pil_font,
                fill=color, stroke_width=STROKE, stroke_fill=(0, 0, 0, 255)
            )
            x += sizes[wi][0] + WORD_GAP

        return np.array(frame)

    clips = []
    for gi in range(0, len(words), GROUP):
        group = words[gi: gi + GROUP]
        t_start = group[0]["start"]
        t_end   = group[-1]["end"]
        if t_start >= max_dur:
            break
        t_end = min(t_end, max_dur)

        for wi, w in enumerate(group):
            w_start = max(w["start"], t_start)
            w_end   = min(w["end"], t_end, max_dur)
            if w_end - w_start < 0.05:
                continue

            arr = _render_group_frame(group, wi)
            clip = (
                ImageClip(arr, is_mask=False)
                .with_start(w_start)
                .with_duration(w_end - w_start)
            )
            clips.append(clip)

    return clips


def _render_video_sync(req: "RenderVideoRequest"):
    """Actual render logic — runs in background thread."""
    import uuid, requests, tempfile
    from moviepy import AudioFileClip, AudioClip, CompositeVideoClip, CompositeAudioClip
    import io

    uid = uuid.uuid4().hex
    audio_dir = BASE / "products" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp())

    # 1. TTS with word timestamps
    audio_bytes, word_timestamps = _get_word_timestamps(req.script, req.voice)
    audio_path = audio_dir / f"{uid}.mp3"
    audio_path.write_bytes(audio_bytes)
    audio_master = AudioFileClip(str(audio_path))
    total_dur = min(audio_master.duration, 58)

    # 2. Background music — download a royalty-free lo-fi track
    music_path = BASE / "products" / "audio" / "bg_music.mp3"
    if not music_path.exists():
        MUSIC_URL = "https://www.chosic.com/wp-content/uploads/2021/07/Lofi-Study-original-chosic.com_.mp3"
        try:
            r = requests.get(MUSIC_URL, timeout=20, stream=True)
            if r.status_code == 200:
                music_path.write_bytes(r.content)
        except Exception:
            pass

    # 3. Pexels B-roll
    if req.broll_query:
        query = req.broll_query
    elif req.video_type == "humor":
        import random
        query = random.choice(HUMOR_BROLL_TERMS)
    else:
        trade = (req.persona_trade or "").lower()
        terms = next((v for k, v in TRADE_BROLL_TERMS.items() if k in trade), TRADE_BROLL_TERMS["default"])
        query = terms[0]

    clip_urls = _pexels_fetch_videos(query, count=6, orientation="portrait")
    if not clip_urls:
        clip_urls = _pexels_fetch_videos(query, count=6, orientation="landscape")

    if not clip_urls:
        local_pool = (
            sorted((BASE / "products" / "browser_demos").glob("browser_*.mp4")) +
            sorted((BASE / "products" / "videos").glob("stick_*.mp4"))
        )
        clip_paths = local_pool[:6] if local_pool else []
    else:
        clip_paths = []
        for i, url in enumerate(clip_urls):
            dest = tmp_dir / f"broll_{i}.mp4"
            if _download_clip(url, dest):
                clip_paths.append(dest)

    if not clip_paths:
        raise HTTPException(status_code=500, detail="No B-roll clips available")

    platforms = [p for p in req.platforms if p in PLATFORM_SPECS] or ALL_PLATFORMS
    urls = {}
    captions = {}

    for platform in platforms:
        spec = PLATFORM_SPECS[platform]
        max_dur = min(total_dur, spec["max_sec"])

        # 4. Flash-cut B-roll
        broll, broll_sources = _flash_cut_broll(clip_paths, max_dur, spec)
        broll = broll.with_duration(max_dur)

        # 5. Mix audio: TTS voice + soft background music
        voice_aud = audio_master.subclipped(0, max_dur)
        try:
            if music_path.exists():
                from moviepy import AudioFileClip as AFC
                music_clip = AFC(str(music_path)).subclipped(0, max_dur).with_effects(
                    [__import__('moviepy').audio.fx.MultiplyVolume(0.12)]
                )
                mixed = CompositeAudioClip([voice_aud, music_clip])
            else:
                mixed = voice_aud
        except Exception:
            mixed = voice_aud

        vid = broll.with_audio(mixed)

        # 6. Animated word-by-word captions
        overlays = [vid]
        try:
            caption_clips = _build_caption_clips(word_timestamps, max_dur, spec)
            overlays.extend(caption_clips)
        except Exception:
            pass

        # 7. Hook text — big bold top overlay, first 3.5 seconds
        hook_text = req.hook or req.script[:60]
        try:
            from moviepy import TextClip
            hook_clip = (
                TextClip(font=FONT, text=hook_text, font_size=max(42, spec["w"] // 22),
                         color="white", stroke_color="black", stroke_width=4,
                         method="caption", size=(spec["w"] - 40, None))
                .with_position(("center", 0.06), relative=True)
                .with_duration(min(3.5, max_dur))
            )
            overlays.append(hook_clip)
        except Exception:
            pass

        # 8. Persona bar — bottom strip
        if req.persona_name and req.persona_trade:
            try:
                from moviepy import TextClip
                label = f"{req.persona_name}  ·  {req.persona_trade}"
                name_clip = (
                    TextClip(font=FONT, text=label, font_size=32, color="white",
                             stroke_color="black", stroke_width=2, method="label")
                    .with_position(("center", 0.92), relative=True)
                    .with_duration(max_dur)
                )
                overlays.append(name_clip)
            except Exception:
                pass

        # 9. Case study card
        if req.video_type == "ugc_casestudy" and req.case_study_data:
            try:
                from moviepy import TextClip
                lines = [f"{k.replace('_',' ').title()}: ${v:,}" if isinstance(v, (int, float))
                         else f"{k.replace('_',' ').title()}: {v}"
                         for k, v in req.case_study_data.items()]
                card_clip = (
                    TextClip(font=FONT, text="\n".join(lines), font_size=36,
                             color="#00FF88", stroke_color="black", stroke_width=2,
                             method="caption", size=(spec["w"] - 80, None))
                    .with_position(("center", 0.42), relative=True)
                    .with_start(min(3.0, max_dur * 0.3))
                    .with_duration(min(4.0, max_dur * 0.4))
                )
                overlays.append(card_clip)
            except Exception:
                pass

        final = CompositeVideoClip(overlays) if len(overlays) > 1 else vid
        out_path = audio_dir / f"{uid}_{platform}.mp4"
        final.write_videofile(str(out_path), codec="libx264", audio_codec="aac",
                              fps=spec["fps"], logger=None, threads=2)
        final.close()
        for c in broll_sources:
            try: c.close()
            except Exception: pass
        urls[platform] = f"https://{PUBLIC_BASE}/media/{out_path.name}"
        captions[platform] = _format_caption(req.script[:500], platform)

    # cleanup tmp
    audio_path.unlink(missing_ok=True)
    for p in tmp_dir.iterdir():
        try: p.unlink()
        except Exception: pass
    try: tmp_dir.rmdir()
    except Exception: pass

    return {
        "status": "ok",
        "video_type": req.video_type,
        "broll_query": query,
        "urls": urls,
        "tiktok_url":    urls.get("tiktok", ""),
        "instagram_url": urls.get("instagram", ""),
        "youtube_url":   urls.get("youtube", ""),
        "facebook_url":  urls.get("facebook", ""),
        "bluesky_url":   urls.get("bluesky", ""),
        "captions": captions,
        "tiktok_caption":    captions.get("tiktok", ""),
        "instagram_caption": captions.get("instagram", ""),
        "youtube_caption":   captions.get("youtube", ""),
        "facebook_caption":  captions.get("facebook", ""),
        "bluesky_caption":   captions.get("bluesky", ""),
    }


# ---------------------------------------------------------------------------
# /scrape_reddit_sync  — sync Reddit scrape, returns immediately (<5s)
# /scrape_tiktok  — async TikTok scrape via Playwright, poll job_id
# /scrape  — combined async scrape (competitor shops + both platforms)
# ---------------------------------------------------------------------------

class RedditScrapeRequest(BaseModel):
    subreddits: list[str] = ["HVAC", "Contractor", "plumbing", "electricians",
                              "Roofing", "smallbusiness", "mildlyinfuriating"]
    limit: int = 25
    sort: str = "hot"


@app.post("/scrape_reddit")
def scrape_reddit_sync(req: RedditScrapeRequest):
    """Scrape Reddit via public JSON API. Synchronous — returns data immediately."""
    import sys
    sys.path.insert(0, str(BASE))
    from competitor_scraper import scrape_reddit
    posts = scrape_reddit(subreddits=req.subreddits, limit=req.limit, sort=req.sort)
    return {"status": "ok", "count": len(posts), "posts": posts}


class TikTokScrapeRequest(BaseModel):
    hashtags: list[str] = ["hvaclife", "plumberlife", "electricianlife",
                            "constructionlife", "contractorlife", "tradeslife"]
    limit: int = 20


@app.post("/scrape_tiktok")
def scrape_tiktok_start(req: TikTokScrapeRequest):
    """Start async TikTok scrape via Playwright. Poll GET /scrape/{job_id}."""
    import uuid, threading
    job_id = uuid.uuid4().hex
    _scrape_jobs[job_id] = {"status": "pending"}

    def _run():
        try:
            import sys
            sys.path.insert(0, str(BASE))
            from competitor_scraper import scrape_tiktok
            videos = scrape_tiktok(hashtags=req.hashtags, limit=req.limit)
            _scrape_jobs[job_id] = {"status": "done", "result": {"videos": videos, "count": len(videos)}}
        except Exception as e:
            _scrape_jobs[job_id] = {"status": "error", "error": str(e)}

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "pending", "job_id": job_id,
            "poll_url": f"https://{PUBLIC_BASE}/scrape/{job_id}"}


# ---------------------------------------------------------------------------
# /scrape  — competitor + trend scraping (replaces Apify actors)
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    reddit_subreddits: list[str] | None = None
    reddit_limit: int = 25
    reddit_sort: str = "hot"
    tiktok_hashtags: list[str] | None = None
    tiktok_limit: int = 20
    etsy_competitors: list[str] | None = None   # list of Etsy shop URLs
    skip_reddit: bool = False
    skip_tiktok: bool = False


_scrape_jobs: dict = {}


def _run_scrape_job(job_id: str, config: dict):
    try:
        import sys
        sys.path.insert(0, str(BASE))
        from competitor_scraper import run_all
        result = run_all(config)
        _scrape_jobs[job_id] = {"status": "done", "result": result}
    except Exception as e:
        _scrape_jobs[job_id] = {"status": "error", "error": str(e)}


@app.post("/scrape")
def scrape(req: ScrapeRequest):
    """
    Start a competitor/trend scrape. Returns job_id — poll GET /scrape/{job_id}.
    Replaces Apify actors with zero per-run cost.
    """
    import uuid, threading
    job_id = uuid.uuid4().hex
    config = req.model_dump()
    _scrape_jobs[job_id] = {"status": "pending"}
    t = threading.Thread(target=_run_scrape_job, args=(job_id, config), daemon=True)
    t.start()
    return {"status": "pending", "job_id": job_id,
            "poll_url": f"https://{PUBLIC_BASE}/scrape/{job_id}"}


@app.get("/scrape/{job_id}")
def scrape_status(job_id: str):
    job = _scrape_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
