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
from pydantic import BaseModel

app = FastAPI(title="Etsy Pipeline API", version="1.0.0")

BASE   = Path(__file__).parent
PYTHON = os.environ.get("PYTHON_BIN", r"C:\Users\Ron39\AppData\Local\Programs\Python\Python312\python.exe")
FONT   = os.environ.get("FONT_PATH", r"C:\Windows\Fonts\arialbd.ttf")


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


class RotationRequest(BaseModel):
    script: str
    voice: str = "en-US-GuyNeural"
    persona_name: str | None = None
    persona_trade: str | None = None
    product_slug: str | None = None   # if set, uses matching browser demo or stick video


@app.post("/next_video")
def next_video(req: RotationRequest):
    """
    Pick the next video and render it with UGC voiceover.
    Browser demos play once through (scenario simulations).
    Stick videos also play once — no looping ever.
    Audio is trimmed to match video duration so nothing repeats.
    Pool alternates browser_demo → stick → browser_demo to keep variety.
    """
    import asyncio, uuid, edge_tts
    from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

    pool_demos = sorted((BASE / "products" / "browser_demos").glob("browser_*.mp4"))
    pool_stick = sorted((BASE / "products" / "videos").glob("stick_*.mp4"))

    counter_file = BASE / "products" / ".rotation_counter"
    count = int(counter_file.read_text()) if counter_file.exists() else 0
    counter_file.write_text(str(count + 1))

    # alternate demo → stick → demo; fall back to whichever pool exists
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
    audio_path = BASE / "products" / "audio" / f"{uid}.mp3"
    out_path   = BASE / "products" / "audio" / f"{uid}_post.mp4"
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    async def _tts():
        await edge_tts.Communicate(req.script, req.voice).save(str(audio_path))

    try:
        asyncio.run(_tts())
        audio = AudioFileClip(str(audio_path))
        video = VideoFileClip(str(chosen))

        # trim to whichever is shorter — video plays once, audio matches it
        duration = min(video.duration, audio.duration)
        video = video.subclipped(0, duration)
        audio = audio.subclipped(0, duration)
        video = video.with_audio(audio)

        if req.persona_name and req.persona_trade:
            label = f"{req.persona_name}  |  {req.persona_trade}"
            try:
                txt = (
                    TextClip(font=FONT, text=label, font_size=26,
                             color="white", stroke_color="black", stroke_width=2, method="label")
                    .with_position(("center", 0.85), relative=True)
                    .with_duration(duration)
                )
                video = CompositeVideoClip([video, txt])
            except Exception:
                pass

        video.write_videofile(str(out_path), codec="libx264", audio_codec="aac",
                              logger=None, threads=2)
        audio_path.unlink(missing_ok=True)
        return {
            "status": "ok",
            "video_path": str(out_path),
            "source_video": chosen.name,
            "video_type": "browser_demo" if chosen in pool_demos else "stick",
            "rotation_count": count,
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
