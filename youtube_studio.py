"""
youtube_studio.py
Playwright bot: post + pin a comment on a YouTube video using a saved Google session.
YouTube Shorts do not support cards/end-screens — a pinned comment is the correct CTA method.

Auth flow:
  1. Run youtube_auth_local.py on your local machine (visible browser, you log in once).
  2. It saves yt_session.json — commit it or upload via POST /youtube_studio_auth_upload.
  3. This module then runs headless on Railway using that saved session.
"""

import asyncio
import json
import os
from pathlib import Path

BASE         = Path(__file__).parent
SESSION_FILE = BASE / "yt_session.json"
_HEADLESS    = os.environ.get("YT_HEADLESS", "1") != "0"


def session_exists() -> bool:
    return SESSION_FILE.exists() and SESSION_FILE.stat().st_size > 100


async def _post_and_pin(video_id: str, comment_text: str) -> dict:
    from playwright.async_api import async_playwright

    storage = json.loads(SESSION_FILE.read_text())

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=_HEADLESS)
        context = await browser.new_context(
            storage_state=storage,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # ── Step 1: post the comment on the watch page ──────────────────────
        await page.goto(f"https://www.youtube.com/watch?v={video_id}", wait_until="domcontentloaded")
        await asyncio.sleep(4)

        # Scroll into the comments zone
        await page.evaluate("window.scrollTo(0, 700)")
        await asyncio.sleep(2)

        # Click the "Add a comment…" placeholder to activate the input
        placeholder = page.locator("#simplebox-placeholder, #placeholder-area").first
        try:
            await placeholder.click(timeout=10_000)
        except Exception:
            # Sometimes the placeholder is hidden — click the contenteditable directly
            pass

        await asyncio.sleep(1)

        # Type comment
        content_box = page.locator("#contenteditable-root").first
        await content_box.click()
        await content_box.fill(comment_text)
        await asyncio.sleep(1)

        # Submit
        submit = page.locator("#submit-button").first
        await submit.click()
        await asyncio.sleep(5)  # wait for comment to appear

        # ── Step 2: pin the comment via YouTube Studio ───────────────────────
        # Navigate to Studio's comment management for this video
        studio_url = f"https://studio.youtube.com/video/{video_id}/comments"
        await page.goto(studio_url, wait_until="domcontentloaded")
        await asyncio.sleep(6)

        # The most recently posted comment should appear first (Newest filter)
        # Open its kebab (three-dot) menu
        kebab = page.locator("ytcp-comment-action-menu button, [aria-label='More']").first
        try:
            await kebab.click(timeout=10_000)
            await asyncio.sleep(1)

            # Click "Pin comment" in the dropdown
            pin_option = page.get_by_text("Pin comment", exact=True).first
            await pin_option.click(timeout=8_000)
            await asyncio.sleep(1)

            # Confirm the pin dialog if it appears
            confirm = page.get_by_text("Pin", exact=True).first
            try:
                await confirm.click(timeout=5_000)
                await asyncio.sleep(2)
            except Exception:
                pass  # no confirm dialog — pin applied directly

            pinned = True
        except Exception as pin_err:
            pinned = False
            print(f"[youtube_studio] Pin step failed (comment was posted): {pin_err}")

        await context.storage_state(path=str(SESSION_FILE))  # refresh saved session
        await browser.close()

    return {
        "status": "ok",
        "video_id": video_id,
        "comment_posted": True,
        "comment_pinned": pinned,
        "comment_text": comment_text,
    }


def post_and_pin(video_id: str, etsy_url: str, product_name: str | None = None) -> dict:
    """
    Synchronous wrapper — call this from FastAPI endpoints.
    Posts a comment and attempts to pin it.
    """
    if not session_exists():
        raise RuntimeError(
            "No YouTube session found. POST your yt_session.json to /youtube_studio_auth_upload first."
        )

    if product_name:
        comment_text = f"🔗 Get it here → {etsy_url}\n({product_name})"
    else:
        comment_text = f"🔗 Get it here → {etsy_url}"

    return asyncio.run(_post_and_pin(video_id, comment_text))
