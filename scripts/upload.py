"""Upload a video PRIVATE (owner publishes manually in YouTube Studio).

Usage:
    python scripts/upload.py video.mp4 "Title" "Description" --tags kapi,capybara
"""
import argparse
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SECRETS = Path(__file__).resolve().parent.parent / "secrets"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("title")
    p.add_argument("description")
    p.add_argument("--tags", default="")
    p.add_argument("--thumbnail")
    a = p.parse_args()

    creds = Credentials.from_authorized_user_file(str(SECRETS / "token.json"))
    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {"title": a.title, "description": a.description,
                    "tags": [t for t in a.tags.split(",") if t], "categoryId": "1"},
        "status": {"privacyStatus": "private",
                   "selfDeclaredMadeForKids": True,
                   "containsSyntheticMedia": True},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(a.video, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"{int(status.progress() * 100)}%")
    vid = resp["id"]
    if a.thumbnail:
        yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(a.thumbnail)).execute()
    print(f"Uploaded (private): https://studio.youtube.com/video/{vid}/edit")


if __name__ == "__main__":
    main()
