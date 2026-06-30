"""
youtube_auth_local.py
Run this ONCE on your local machine (Windows) to log into YouTube and save the session.
The saved yt_session.json is then uploaded to Railway so the headless bot can use it.

Usage:
  python youtube_auth_local.py

After saving, upload via:
  python youtube_auth_local.py --upload
  (requires RAILWAY_URL env var or edit the URL below)
"""

import asyncio
import json
import sys
from pathlib import Path

SESSION_FILE  = Path(__file__).parent / "yt_session.json"
RAILWAY_URL   = "https://etsy-pipeline-production.up.railway.app"


async def capture_session():
    from playwright.async_api import async_playwright
    print("Reading your existing Chrome profile (already logged into YouTube)...")

    chrome_path     = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir   = r"C:\Users\Ron39\AppData\Local\Google\Chrome\User Data"

    async with async_playwright() as p:
        # Launch using your real Chrome profile — already authenticated
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=chrome_path,
            headless=False,
            channel="chrome",
            args=["--profile-directory=Default"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://studio.youtube.com")

        try:
            await page.wait_for_url("https://studio.youtube.com/**", timeout=60_000)
        except Exception:
            print("Could not reach YouTube Studio. Make sure you're logged in to YouTube in Chrome.")
            await context.close()
            return

        await asyncio.sleep(2)
        storage = await context.storage_state()
        SESSION_FILE.write_text(json.dumps(storage, indent=2))
        print(f"\nSession saved to: {SESSION_FILE}")
        await context.close()


def upload_session():
    import requests
    if not SESSION_FILE.exists():
        print("No session file found. Run without --upload first.")
        return
    data = json.loads(SESSION_FILE.read_text())
    r = requests.post(
        f"{RAILWAY_URL}/youtube_studio_auth_upload",
        json={"session": data},
        timeout=30,
    )
    if r.ok:
        print("Session uploaded to Railway successfully.")
        print(r.json())
    else:
        print(f"Upload failed: {r.status_code} — {r.text[:300]}")


if __name__ == "__main__":
    if "--upload" in sys.argv:
        upload_session()
    else:
        asyncio.run(capture_session())
        print("\nNext step: run  python youtube_auth_local.py --upload")
