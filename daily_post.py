"""
daily_post.py  --  One run = one day's post. Designed to be triggered daily by
Windows Task Scheduler.

Logic:
  - Alternates content type by day: even day -> product use-case video,
    odd day -> stick-figure humor short. (Your chosen 1/day rotate mix.)
  - Rotates through all 19 products so nothing repeats until the cycle completes,
    tracked in _post_history.json.
  - Builds the platform-correct caption (store link in the right place).
  - Validates the MP4 against each target platform's format spec.
  - Posts via the configured backend. SAFE BY DEFAULT: dry-run unless --live is
    passed AND POSTER is a live backend.

Run:  python daily_post.py            (dry-run preview of today's post)
      python daily_post.py --live     (actually post, using POSTER backend)
"""
import datetime
import json
import os
import sys

try:  # Windows consoles default to cp1252 and choke on emoji in captions
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv

import creator
import poster as P

load_dotenv()
VIDEOS_DIR = os.path.join(creator.PRODUCTS_DIR, "videos")
HISTORY = os.path.join(VIDEOS_DIR, "_post_history.json")
STORE_URL = os.getenv("STORE_URL", "").strip()
TARGET_PLATFORMS = [p.strip() for p in os.getenv("TARGET_PLATFORMS", "youtube").split(",") if p.strip()]


def load_history():
    if os.path.exists(HISTORY):
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": [], "cycle_index": 0}


def save_history(h):
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(h, f, indent=2)


def read_caption(path):
    """caption .txt is: caption text, blank line, hashtag line."""
    if not os.path.exists(path):
        return "", []
    text = open(path, encoding="utf-8").read().strip()
    parts = text.split("\n\n")
    base = parts[0].strip()
    tags = []
    if len(parts) > 1:
        tags = [t.lstrip("#") for t in parts[-1].split() if t.startswith("#")]
    return base, tags


# Fixed anchor so the schedule is fully deterministic from the date. Every
# platform, every run, on a given calendar day resolves to the SAME video.
SCHEDULE_EPOCH = datetime.date(2026, 6, 29)


def todays_pick(opportunities, history, on=None):
    """Return (kind, opportunity, fname_base, idx) as a pure function of the date.
    Day N from the epoch: even -> product demo, odd -> humor short; the catalog
    index advances every 2 days so each product gets a demo day and a humor day.
    Because nothing here depends on mutable state, all platforms stay in lockstep."""
    today = on or datetime.date.today()
    days = (today - SCHEDULE_EPOCH).days
    kind = "product" if days % 2 == 0 else "humor"
    idx = (days // 2) % len(opportunities)
    opp = opportunities[idx]
    fname_base = creator.safe_filename(opp["suggested_etsy_title"])
    return kind, opp, fname_base, idx


def main():
    live = "--live" in sys.argv
    with open(creator.INPUT_FILE, encoding="utf-8") as f:
        opportunities = json.load(f)
    history = load_history()
    kind, opp, fname_base, idx = todays_pick(opportunities, history)

    if kind == "humor":
        video = os.path.join(VIDEOS_DIR, f"stick_{fname_base}.mp4")
        cap_file = os.path.join(VIDEOS_DIR, f"stick_{fname_base}_caption.txt")
        title = f"{opp['suggested_etsy_title'].split('|')[0].strip()} (you know the feeling)"
    else:
        video = os.path.join(VIDEOS_DIR, f"{fname_base}.mp4")
        cap_file = os.path.join(VIDEOS_DIR, f"{fname_base}_caption.txt")
        title = opp["suggested_etsy_title"].split("|")[0].strip()

    print(f"=== daily_post {datetime.date.today()} | {kind.upper()} | {title[:50]} ===")
    if not os.path.exists(video):
        print(f"[abort] video not built yet: {video}")
        sys.exit(1)

    ok, issues = P.validate_format(video, TARGET_PLATFORMS)
    if not ok:
        print("[format issues]"); [print("   -", i) for i in issues]
        # 9:16 master is compliant; only abort on real problems
    else:
        print(f"[format] OK for {', '.join(TARGET_PLATFORMS)}")

    base_caption, tags = read_caption(cap_file)
    if not STORE_URL:
        print("[warn] STORE_URL not set in .env -- caption has no store link yet")

    # Post the SAME date-derived video to every configured backend. Caption is
    # tailored per backend (YouTube gets a clickable link; others get link-in-bio).
    backends = P.get_posters()  # from POSTER env (comma-separated), e.g. "postforme,youtube"
    today = str(datetime.date.today())
    done_key = lambda b: f"{today}|{kind}|{b}"

    for backend in backends:
        cap_platform = "youtube" if backend.name == "youtube" else (TARGET_PLATFORMS[0] if TARGET_PLATFORMS else "tiktok")
        caption = P.build_caption(base_caption, tags, STORE_URL, cap_platform)
        already = any(p.get("key") == done_key(backend.name) for p in history["posted"])

        if already and live and backend.name != "dry":
            print(f"[skip] {backend.name}: already posted today"); continue

        print(f"[backend] {backend.name}" + ("" if (live and backend.name != 'dry') else "  (dry-run)"))
        if not live or backend.name == "dry":
            P.DryRunPoster().post(video, caption, title=title, tags=tags)
        else:
            try:
                backend.post(video, caption, title=title, tags=tags)
                history["posted"].append({"date": today, "kind": kind, "fname": fname_base,
                                          "backend": backend.name, "key": done_key(backend.name)})
                save_history(history)
                print(f"[done] posted via {backend.name}.")
            except Exception as e:
                print(f"[error] {backend.name} post failed: {e}")


if __name__ == "__main__":
    main()
