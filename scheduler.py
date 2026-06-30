"""
FILE 7: scheduler.py
Runs scraper.py and analyzer.py once weekly (Sunday 2am). If any new
opportunity scores above 7/10, sends a desktop notification. Logs every run.
Run independently (leave running in background): python scheduler.py
Output: pipeline_log.txt (appended each run)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

import schedule

try:
    from plyer import notification
    DESKTOP_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    DESKTOP_NOTIFICATIONS_AVAILABLE = False

LOG_FILE = "pipeline_log.txt"
OPPORTUNITIES_FILE = "opportunities.json"
SCORE_THRESHOLD = 7


def log_line(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as log_err:
        print(f"[warn] Could not write to {LOG_FILE}: {log_err}")


def run_script(script_name: str) -> bool:
    log_line(f"Starting {script_name}...")
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True, text=True, timeout=7200,
        )
        if result.returncode != 0:
            log_line(f"{script_name} exited with code {result.returncode}")
            log_line(f"stderr: {result.stderr[-2000:]}")
            return False
        log_line(f"{script_name} completed successfully.")
        return True
    except subprocess.TimeoutExpired:
        log_line(f"{script_name} timed out after 2 hours.")
        return False
    except Exception as run_err:
        log_line(f"Failed to run {script_name}: {run_err}")
        return False


def send_desktop_notification(title: str, message: str):
    if not DESKTOP_NOTIFICATIONS_AVAILABLE:
        log_line("[warn] plyer not installed, skipping desktop notification. Run: pip install plyer")
        return
    try:
        notification.notify(title=title, message=message, timeout=15)
    except Exception as notif_err:
        log_line(f"[warn] Desktop notification failed: {notif_err}")


def check_high_scoring_opportunities():
    if not os.path.exists(OPPORTUNITIES_FILE):
        log_line(f"{OPPORTUNITIES_FILE} not found, skipping score check.")
        return

    try:
        with open(OPPORTUNITIES_FILE, "r", encoding="utf-8") as f:
            opportunities = json.load(f)
    except Exception as read_err:
        log_line(f"Could not read {OPPORTUNITIES_FILE}: {read_err}")
        return

    high_scorers = [o for o in opportunities if isinstance(o.get("score"), (int, float)) and o["score"] > SCORE_THRESHOLD]

    if high_scorers:
        names = ", ".join(o.get("suggested_etsy_title", "Untitled")[:40] for o in high_scorers)
        log_line(f"Found {len(high_scorers)} opportunity(ies) above {SCORE_THRESHOLD}/10: {names}")
        send_desktop_notification(
            "New High-Scoring Etsy Opportunity",
            f"{len(high_scorers)} new opportunity(ies) scored above {SCORE_THRESHOLD}/10. Check opportunities.json.",
        )
    else:
        log_line(f"No opportunities above {SCORE_THRESHOLD}/10 this run.")


def weekly_job():
    log_line("=" * 50)
    log_line("Weekly pipeline run starting (scraper.py -> analyzer.py)")

    scraper_ok = run_script("scraper.py")
    if not scraper_ok:
        log_line("Aborting weekly run: scraper.py failed.")
        return

    analyzer_ok = run_script("analyzer.py")
    if not analyzer_ok:
        log_line("Aborting weekly run: analyzer.py failed.")
        return

    check_high_scoring_opportunities()
    log_line("Weekly pipeline run complete.")
    log_line("=" * 50)


def main():
    print("=" * 60)
    print("PIPELINE SCHEDULER")
    print("=" * 60)
    print("[*] Scheduled to run scraper.py + analyzer.py every Sunday at 2:00 AM.")
    print(f"[*] Logging to {LOG_FILE}")
    print("[*] Press Ctrl+C to stop.\n")

    schedule.every().sunday.at("02:00").do(weekly_job)

    log_line("Scheduler started. Waiting for next scheduled run (Sunday 02:00).")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        log_line("Scheduler stopped by user (Ctrl+C).")
        print("\n[done] Scheduler stopped.")
    except Exception as fatal_err:
        log_line(f"Scheduler crashed: {fatal_err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
