"""
poster.py  --  Platform posting layer + per-platform format validation.

Backends (pick via POSTER env var):
  - "dry"        : log what WOULD be posted, never touches the network (default)
  - "youtube"    : upload as a YouTube Short via the free YouTube Data API v3
  - "postforme"  : post to TikTok/YouTube/Instagram/etc via Post for Me's unified API

All backends share:
  - validate_format(): confirm the MP4 meets each target platform's spec
  - build_caption(): append the Etsy store link the right way per platform
    (YouTube descriptions take a clickable URL; TikTok/IG get "link in bio").

Credentials come from .env (never hard-coded). Nothing posts unless POSTER is
set to a live backend AND --live is passed by the caller.
"""
import os

from moviepy import VideoFileClip

# 9:16 vertical master; per-platform duration ceilings (seconds)
PLATFORM_SPECS = {
    "youtube":   {"max_dur": 180, "size": (1080, 1920)},
    "tiktok":    {"max_dur": 600, "size": (1080, 1920)},
    "instagram": {"max_dur": 90,  "size": (1080, 1920)},
    "facebook":  {"max_dur": 90,  "size": (1080, 1920)},
    "bluesky":   {"max_dur": 60,  "size": (1080, 1920)},
}


def validate_format(video_path, platforms=("youtube", "tiktok", "instagram")):
    """Return (ok, issues). Confirms dimensions + duration per platform."""
    issues = []
    clip = VideoFileClip(video_path)
    try:
        w, h = clip.size
        dur = clip.duration
    finally:
        clip.close()
    for plat in platforms:
        spec = PLATFORM_SPECS.get(plat)
        if not spec:
            continue
        if (w, h) != spec["size"]:
            issues.append(f"{plat}: size {w}x{h} != required {spec['size'][0]}x{spec['size'][1]}")
        if dur > spec["max_dur"]:
            issues.append(f"{plat}: duration {dur:.0f}s exceeds {spec['max_dur']}s cap")
    return (len(issues) == 0, issues)


def build_caption(base_caption, hashtags, store_url, platform):
    """Compose the final post text with the store link placed correctly."""
    tags = " ".join("#" + t.lstrip("#").replace(" ", "") for t in (hashtags or []))
    if platform == "youtube":
        # descriptions support clickable links
        link = f"\n\n🛒 Get it on Etsy: {store_url}" if store_url else ""
        return f"{base_caption}{link}\n\n{tags}".strip()
    else:
        # TikTok / IG captions are not clickable -> drive to bio
        link = "\n\n🛒 Link in bio for the full tool on Etsy" if store_url else ""
        return f"{base_caption}{link}\n\n{tags}".strip()


# ---------------------------------------------------------------- backends ----
class DryRunPoster:
    name = "dry"

    def post(self, video_path, caption, title=None, tags=None):
        print("    [DRY-RUN] would post:")
        print(f"      file:  {video_path}")
        print(f"      title: {title}")
        print(f"      caption:\n        " + caption.replace("\n", "\n        "))
        return {"status": "dry-run"}


class YouTubePoster:
    """Free YouTube Data API v3 upload. Requires (one-time, by the user):
       pip install google-api-python-client google-auth-oauthlib
       and a Google OAuth client secret file + a one-time browser consent that
       writes a token file. Paths come from .env:
         YOUTUBE_CLIENT_SECRET_FILE, YOUTUBE_TOKEN_FILE
    """
    name = "youtube"

    def __init__(self):
        self.secret = os.getenv("YOUTUBE_CLIENT_SECRET_FILE")
        self.token = os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")

    def _service(self):
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        scopes = ["https://www.googleapis.com/auth/youtube.upload"]
        creds = None
        if os.path.exists(self.token):
            creds = Credentials.from_authorized_user_file(self.token, scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # opens a browser for the USER to consent (one time)
                flow = InstalledAppFlow.from_client_secrets_file(self.secret, scopes)
                creds = flow.run_local_server(port=0)
            with open(self.token, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        return build("youtube", "v3", credentials=creds)

    def post(self, video_path, caption, title=None, tags=None):
        from googleapiclient.http import MediaFileUpload
        yt = self._service()
        body = {
            "snippet": {"title": (title or "")[:100], "description": caption,
                        "tags": (tags or [])[:15], "categoryId": "22"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = req.execute()
        vid = resp.get("id")
        print(f"    [YouTube] published https://youtube.com/shorts/{vid}")
        return {"status": "published", "id": vid}


class PostForMePoster:
    """Unified posting via Post for Me (https://api.postforme.dev/v1).
       Env: POSTFORME_API_KEY. POSTFORME_ACCOUNTS optional (comma-separated
       social_account ids); if unset we auto-fetch ALL connected accounts.
    """
    name = "postforme"
    BASE = "https://api.postforme.dev/v1"

    def __init__(self):
        self.key = os.getenv("POSTFORME_API_KEY")
        self.accounts = [a.strip() for a in os.getenv("POSTFORME_ACCOUNTS", "").split(",") if a.strip()]

    def _headers(self, json=True):
        h = {"Authorization": f"Bearer {self.key}"}
        if json:
            h["Content-Type"] = "application/json"
        return h

    def list_accounts(self):
        import requests
        r = requests.get(f"{self.BASE}/social-accounts", headers=self._headers(), timeout=60)
        r.raise_for_status()
        return r.json().get("data", [])

    def _resolve_accounts(self):
        if self.accounts:
            return self.accounts
        ids = [a.get("id") for a in self.list_accounts() if a.get("id")]
        if not ids:
            raise RuntimeError("no connected social accounts found on Post for Me")
        return ids

    def _upload_media(self, video_path):
        """Get a signed upload URL, PUT the file, return the public media URL.
        Field names vary, so we probe the common ones."""
        import requests
        r = requests.post(f"{self.BASE}/media/create-upload-url",
                          headers=self._headers(),
                          json={"file_name": os.path.basename(video_path),
                                "mime_type": "video/mp4", "content_type": "video/mp4"},
                          timeout=60)
        r.raise_for_status()
        info = r.json()
        put_url = (info.get("upload_url") or info.get("url")
                   or info.get("signed_url") or info.get("uploadUrl"))
        media_url = (info.get("media_url") or info.get("public_url")
                     or info.get("mediaUrl") or info.get("url"))
        if not put_url:
            raise RuntimeError(f"create-upload-url response missing upload URL: {info}")
        with open(video_path, "rb") as f:
            requests.put(put_url, data=f, headers={"Content-Type": "video/mp4"},
                         timeout=600).raise_for_status()
        return media_url

    def post(self, video_path, caption, title=None, tags=None,
             platform_videos: dict = None, platform_captions: dict = None):
        """Post per-platform if platform_videos dict provided, else single post to all accounts.

        platform_videos:  {"tiktok": "/path/tiktok.mp4", "instagram": "/path/instagram.mp4", ...}
        platform_captions: {"tiktok": "caption...", "instagram": "caption...", ...}
        """
        import requests

        # Map platform name → PostForMe account id
        ACCOUNT_IDS = {
            "youtube":   "UC04oCwObnayhYjHMyUMzFwg",
            "instagram": "17841425222986458",
            "tiktok":    "-000nHuLr7f6aG2up5DjIH5DOQfkUiNsR9F6",
            "bluesky":   "did:plc:ncv74laxg4yeywzwkzhtynnv",
        }

        if platform_videos:
            results = []
            for platform, vid_path in platform_videos.items():
                acct_id = ACCOUNT_IDS.get(platform)
                if not acct_id:
                    print(f"    [PostForMe] skipping {platform} — no account id")
                    continue
                pcaption = (platform_captions or {}).get(platform, caption)
                media_url = self._upload_media(vid_path)
                r = requests.post(f"{self.BASE}/social-posts", headers=self._headers(),
                                  json={"caption": pcaption,
                                        "social_accounts": [acct_id],
                                        "media": [{"url": media_url}]}, timeout=180)
                if r.status_code >= 400:
                    print(f"    [PostForMe] {platform} failed {r.status_code}: {r.text}")
                    results.append({"platform": platform, "status": "error", "error": r.text})
                else:
                    out = r.json()
                    print(f"    [PostForMe] {platform} post id={out.get('id')}")
                    results.append({"platform": platform, "status": "created", "id": out.get("id")})
            return {"status": "created", "results": results}
        else:
            # fallback: single video to all accounts
            accounts = self._resolve_accounts()
            media_url = self._upload_media(video_path)
            r = requests.post(f"{self.BASE}/social-posts", headers=self._headers(),
                              json={"caption": caption, "social_accounts": accounts,
                                    "media": [{"url": media_url}]}, timeout=180)
            if r.status_code >= 400:
                raise RuntimeError(f"post failed {r.status_code}: {r.text}")
            out = r.json()
            print(f"    [PostForMe] created post id={out.get('id')} -> {len(accounts)} account(s)")
            return {"status": "created", "id": out.get("id")}


_BACKENDS = {"youtube": YouTubePoster, "postforme": PostForMePoster, "dry": DryRunPoster}


def get_poster():
    name = os.getenv("POSTER", "dry").lower().split(",")[0].strip()
    return _BACKENDS.get(name, DryRunPoster)()


def get_posters():
    """POSTER may be comma-separated (e.g. 'postforme,youtube') to fan out the
    SAME video to multiple platforms in one daily run."""
    names = [n.strip() for n in os.getenv("POSTER", "dry").lower().split(",") if n.strip()]
    out = []
    for n in names:
        out.append(_BACKENDS.get(n, DryRunPoster)())
    return out or [DryRunPoster()]
