"""
FILE 3: reddit_scraper.py
Uses PRAW (official Reddit API) to pull posts and comments from target
subreddits that mention operations/pain-point keywords.
Run independently: python reddit_scraper.py
Output: reddit_pain_points.csv
"""

import csv
import os
import sys

import praw
from dotenv import load_dotenv

SUBREDDITS = [
    "landlord",
    "PropertyManagement",
    "realestateinvesting",
    "HVAC",
    "landscaping",
    "cleaning_business",
    "Contractor",
    "smallbusiness",
    "Entrepreneur",
]

PAIN_KEYWORDS = [
    "template", "tracker", "spreadsheet", "tool", "organize", "system",
    "dashboard", "KPI", "profit", "crew", "technician", "route",
    "job cost", "overhead", "pricing", "scheduling",
]

POSTS_PER_SUBREDDIT = 100
OUTPUT_FILE = "reddit_pain_points.csv"
CSV_FIELDS = [
    "subreddit", "type", "matched_keywords", "title_or_context",
    "text", "score", "url", "created_utc", "author",
]


def load_reddit_client():
    load_dotenv()
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "etsy-pipeline-bot/1.0")

    if not client_id or not client_secret:
        print("[fatal] Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET in .env file.")
        print("        Get credentials at https://www.reddit.com/prefs/apps")
        sys.exit(1)

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        reddit.read_only = True
        return reddit
    except Exception as auth_err:
        print(f"[fatal] Could not authenticate with Reddit API: {auth_err}")
        sys.exit(1)


def find_matched_keywords(text: str):
    if not text:
        return []
    lowered = text.lower()
    return [kw for kw in PAIN_KEYWORDS if kw.lower() in lowered]


def process_subreddit(reddit, sub_name: str, writer, csv_file):
    print(f"\n[*] Scanning r/{sub_name} (top {POSTS_PER_SUBREDDIT} posts)...")
    rows_written = 0

    try:
        subreddit = reddit.subreddit(sub_name)
        submissions = list(subreddit.top(limit=POSTS_PER_SUBREDDIT))
    except Exception as sub_err:
        print(f"  [error] Could not fetch posts from r/{sub_name}: {sub_err}")
        return 0

    for idx, submission in enumerate(submissions, start=1):
        try:
            post_text = f"{submission.title} {submission.selftext or ''}"
            matched = find_matched_keywords(post_text)
            if matched:
                writer.writerow({
                    "subreddit": sub_name,
                    "type": "post",
                    "matched_keywords": ", ".join(matched),
                    "title_or_context": submission.title,
                    "text": (submission.selftext or "")[:1000],
                    "score": submission.score,
                    "url": f"https://www.reddit.com{submission.permalink}",
                    "created_utc": submission.created_utc,
                    "author": str(submission.author) if submission.author else "[deleted]",
                })
                rows_written += 1

            submission.comments.replace_more(limit=0)
            for comment in submission.comments.list():
                comment_body = getattr(comment, "body", "") or ""
                matched_c = find_matched_keywords(comment_body)
                if matched_c:
                    writer.writerow({
                        "subreddit": sub_name,
                        "type": "comment",
                        "matched_keywords": ", ".join(matched_c),
                        "title_or_context": submission.title,
                        "text": comment_body[:1000],
                        "score": getattr(comment, "score", ""),
                        "url": f"https://www.reddit.com{comment.permalink}" if hasattr(comment, "permalink") else "",
                        "created_utc": getattr(comment, "created_utc", ""),
                        "author": str(comment.author) if getattr(comment, "author", None) else "[deleted]",
                    })
                    rows_written += 1

            csv_file.flush()

            if idx % 20 == 0:
                print(f"  [-] Processed {idx}/{len(submissions)} posts in r/{sub_name}")

        except Exception as post_err:
            print(f"  [warn] Skipped a post/comment due to error: {post_err}")
            continue

    print(f"  [+] r/{sub_name}: {rows_written} matching posts/comments captured")
    return rows_written


def main():
    print("=" * 60)
    print("REDDIT PAIN-POINT SCRAPER (PRAW / official API)")
    print("=" * 60)

    reddit = load_reddit_client()
    print("[*] Authenticated with Reddit API (read-only mode)")

    grand_total = 0

    try:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
            writer.writeheader()

            for idx, sub_name in enumerate(SUBREDDITS, start=1):
                print(f"\n[Subreddit {idx}/{len(SUBREDDITS)}]")
                try:
                    grand_total += process_subreddit(reddit, sub_name, writer, csv_file)
                except Exception as sub_err:
                    print(f"  [error] Unexpected failure on r/{sub_name}: {sub_err}")
                    continue

    except PermissionError:
        print(f"[fatal] Could not write to {OUTPUT_FILE}. Is it open in another program?")
        sys.exit(1)
    except Exception as fatal_err:
        print(f"[fatal] Unexpected error: {fatal_err}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"[done] Total matching posts/comments captured: {grand_total}")
    print(f"[done] Results saved to {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
