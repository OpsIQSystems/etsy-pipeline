"""
tts.py  --  Free neural voiceover via Edge-TTS (no API key, no paid service).

Consistent named voices so every product video shares one narrator and every
stick-figure short shares one (different) voice. Synthesizes a line of script to
an MP3 we can attach to a scene.
"""
import asyncio
import hashlib
import os
import threading

import edge_tts

# Consistent brand voices (change here to restyle the whole catalog at once)
PRODUCT_VOICE = "en-US-AndrewNeural"      # confident, modern, credible
STICK_VOICE = "en-US-BrianNeural"         # casual, comedic timing

VOICE_DIR = os.path.join("products", "videos", "_voice")


def _synth(text, voice, out_path, rate="+0%"):
    # Run in a dedicated thread with its own event loop -- edge-tts uses asyncio,
    # and this module is called from inside Playwright's sync API (which already
    # holds a running loop), so asyncio.run() here would raise.
    error = {}

    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            comm = edge_tts.Communicate(text, voice, rate=rate)
            loop.run_until_complete(comm.save(out_path))
            loop.close()
        except Exception as e:  # noqa: BLE001
            error["e"] = e

    t = threading.Thread(target=run)
    t.start()
    t.join()
    if "e" in error:
        raise error["e"]


def narrate(text, voice, cache_dir=VOICE_DIR, rate="+0%"):
    """Return path to an MP3 of `text` in `voice`, cached by content hash so we
    never re-synthesize the same line twice."""
    text = (text or "").strip()
    if not text:
        return None
    os.makedirs(cache_dir, exist_ok=True)
    key = hashlib.md5(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()[:16]
    out = os.path.join(cache_dir, f"{key}.mp3")
    if not os.path.exists(out):
        _synth(text, voice, out, rate=rate)
    return out
