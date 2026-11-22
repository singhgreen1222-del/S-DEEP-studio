"""YouTube upload with SEO metadata, schedule, captions + verification. Works in cloud via env secrets."""
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
DISCLAIMER = "Disclaimer: Ye video sirf educational purpose ke liye hai, personal investment advice nahi hai."


def get_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    cid, sec, rt = os.environ.get("YT_CLIENT_ID"), os.environ.get("YT_CLIENT_SECRET"), os.environ.get("YT_REFRESH_TOKEN")
    if not (cid and sec and rt):
        raise RuntimeError("YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN secrets set nahi hain")
    creds = Credentials(None, refresh_token=rt, token_uri="https://oauth2.googleapis.com/token",
                        client_id=cid, client_secret=sec)
    creds.refresh(Request())
    return creds


def get_service():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=get_creds())


def _hashtags(cfg):
    tags = []
    for h in cfg.get("hashtags", [])[:5]:
        h = "#" + h.strip().lstrip("#").replace(" ", "")
        if len(h) > 1 and h not in tags:
            tags.append(h)
    if cfg.get("mode") == "short" and "#Shorts" not in tags:
        tags.append("#Shorts")
    return tags


def build_description(cfg):
    d = cfg.get("description", "").strip()
    if cfg.get("chapters_text"):
        d += "\n\n⏱ Chapters:\n" + cfg["chapters_text"]
    if cfg.get("sources"):
        d += "\n\n📚 Sources:\n" + "\n".join(cfg["sources"])
    d += "\n\n" + DISCLAIMER + "\nAI-generated voice & visuals used.\n\n" + " ".join(_hashtags(cfg))
    return d[:4900]


def build_tags(cfg):
    out, total = [], 0
    for t in cfg.get("keywords", []) + cfg.get("tags", []):
        t = t.strip().lstrip("#")
        if t and t.lower() not in [x.lower() for x in out] and total + len(t) + 1 < 450:
            out.append(t); total += len(t) + 1
    return out


def upload_video(cfg, video, thumb=None, srt=None, category="25"):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if cfg.get("publish_at"):
        dt = datetime.fromisoformat(cfg["publish_at"]).astimezone(timezone.utc)
        if dt > datetime.now(timezone.utc):
            status["publishAt"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    yt = build("youtube", "v3", credentials=get_creds())
    body = {"snippet": {"title": cfg["title"][:100], "description": build_description(cfg), "tags": build_tags(cfg),
                        "categoryId": category, "defaultLanguage": "hi", "defaultAudioLanguage": "hi"}, "status": status}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid, extras = resp["id"], []
    if thumb and Path(thumb).exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb))).execute(); extras.append("thumbnail")
        except Exception:
            pass  # custom thumbnails need a verified channel
    if srt and Path(srt).exists() and cfg.get("mode") == "long":
        try:
            yt.captions().insert(part="snippet", body={"snippet": {"videoId": vid, "language": "hi", "name": "Hindi"}},
                                 media_body=MediaFileUpload(str(srt), mimetype="application/octet-stream")).execute()
            extras.append("captions")
        except Exception:
            pass
    st = yt.videos().list(part="status", id=vid).execute()["items"][0]["status"]  # real confirmation
    return {"id": vid, "link": f"https://youtu.be/{vid}", "privacy": st.get("privacyStatus"),
            "publishAt": st.get("publishAt"), "uploadStatus": st.get("uploadStatus"), "extras": extras}
