"""
package_uploads.py  --  Build ready-to-upload, dated video folders for manual
posting to TikTok and Instagram, plus a calendar file of reminders.

For each scheduled day (deterministic, same sequence as the auto-poster), it:
  - picks the day's video (product demo / humor short),
  - re-muxes it with +faststart for smooth mobile playback (format-correct MP4),
  - copies it into products/uploads/<platform>/ named by DATE_TIME so you know
    exactly when to post it,
  - drops a matching _caption.txt (platform-appropriate, with your store link),
  - and writes posting_schedule.ics -- import it into Google/Apple/Outlook
    Calendar to get a reminder before every post.

Run: python package_uploads.py
"""
import datetime
import os
import shutil
import subprocess
import json

import imageio_ffmpeg
from dotenv import load_dotenv

import creator
import daily_post as D
import poster as P

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VIDEOS_DIR = os.path.join(creator.PRODUCTS_DIR, "videos")
UPLOADS_DIR = os.path.join(creator.PRODUCTS_DIR, "uploads")
STORE_URL = os.getenv("STORE_URL", "").strip()
ICS_FILE = "posting_schedule.ics"

# Start tomorrow; both platforms get the SAME video the SAME day (staggered time).
START_DATE = datetime.date.today() + datetime.timedelta(days=1)
N_DAYS = 38  # 19 products x (1 demo day + 1 humor day)
PLATFORM_TIMES = {"tiktok": (18, 0), "instagram": (19, 0)}


def short_name(title):
    base = title.split("|")[0].strip()
    keep = "".join(c if c.isalnum() else " " for c in base).split()
    return "".join(w.capitalize() for w in keep)[:34]


def faststart_copy(src, dst):
    """Stream-copy with moov atom at the front (mobile-friendly). No re-encode."""
    subprocess.run([FFMPEG, "-y", "-i", src, "-c", "copy", "-movflags", "+faststart", dst],
                   capture_output=True, timeout=120)


def ics_escape(s):
    return (s or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def ics_event(dt, summary, description):
    end = dt + datetime.timedelta(minutes=15)
    fmt = "%Y%m%dT%H%M%S"
    uid = f"{dt.strftime(fmt)}-{abs(hash(summary)) % 10**8}@etsy-pipeline"
    return (
        "BEGIN:VEVENT\n"
        f"UID:{uid}\n"
        f"DTSTAMP:{datetime.datetime.now().strftime(fmt)}\n"
        f"DTSTART:{dt.strftime(fmt)}\n"
        f"DTEND:{end.strftime(fmt)}\n"
        f"SUMMARY:{ics_escape(summary)}\n"
        f"DESCRIPTION:{ics_escape(description)}\n"
        "BEGIN:VALARM\nTRIGGER:-PT15M\nACTION:DISPLAY\n"
        f"DESCRIPTION:{ics_escape(summary)}\nEND:VALARM\n"
        "END:VEVENT\n"
    )


def main():
    with open(creator.INPUT_FILE, encoding="utf-8") as f:
        opportunities = json.load(f)

    for plat in PLATFORM_TIMES:
        os.makedirs(os.path.join(UPLOADS_DIR, plat), exist_ok=True)

    events = []
    rows = []
    made = 0
    for d in range(N_DAYS):
        date = START_DATE + datetime.timedelta(days=d)
        kind, opp, fname_base, idx = D.todays_pick(opportunities, {"posted": []}, on=date)
        if kind == "humor":
            src = os.path.join(VIDEOS_DIR, f"stick_{fname_base}.mp4")
            cap_file = os.path.join(VIDEOS_DIR, f"stick_{fname_base}_caption.txt")
            title = f"{opp['suggested_etsy_title'].split('|')[0].strip()} (humor)"
        else:
            src = os.path.join(VIDEOS_DIR, f"{fname_base}.mp4")
            cap_file = os.path.join(VIDEOS_DIR, f"{fname_base}_caption.txt")
            title = opp["suggested_etsy_title"].split("|")[0].strip()
        if not os.path.exists(src):
            print(f"[skip] missing source: {src}")
            continue

        base_caption, tags = D.read_caption(cap_file)
        sn = short_name(opp["suggested_etsy_title"])

        for plat, (hh, mm) in PLATFORM_TIMES.items():
            dt = datetime.datetime(date.year, date.month, date.day, hh, mm)
            stamp = f"{date.strftime('%Y-%m-%d')}_{hh:02d}{mm:02d}"
            out_base = f"{stamp}_{kind}_{sn}"
            out_mp4 = os.path.join(UPLOADS_DIR, plat, out_base + ".mp4")
            faststart_copy(src, out_mp4)
            caption = P.build_caption(base_caption, tags, STORE_URL, plat)
            with open(os.path.join(UPLOADS_DIR, plat, out_base + "_caption.txt"),
                      "w", encoding="utf-8") as cf:
                cf.write(caption + "\n")
            events.append(ics_event(
                dt, f"Post to {plat.capitalize()}: {title}",
                f"File: uploads/{plat}/{out_base}.mp4\n\nCaption:\n{caption}"))
            rows.append((dt, plat, out_base))
        made += 1
        print(f"  [{d+1:2}/{N_DAYS}] {date} {kind:7} -> {sn}")

    cal = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//etsy-pipeline//posting//EN\nCALSCALE:GREGORIAN\n"
    cal += "".join(events) + "END:VCALENDAR\n"
    with open(ICS_FILE, "w", encoding="utf-8") as f:
        f.write(cal)

    print(f"\n[done] packaged {made} days x {len(PLATFORM_TIMES)} platforms -> {UPLOADS_DIR}\\<platform>\\")
    print(f"[done] reminders -> {ICS_FILE}  (import into your calendar)")
    print(f"[schedule] {START_DATE} through {START_DATE + datetime.timedelta(days=N_DAYS-1)}")


if __name__ == "__main__":
    main()
