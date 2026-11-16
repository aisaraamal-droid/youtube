#!/usr/bin/env python3
"""Upload a Short PRIVATE (the owner presses "Publish" in YouTube Studio).

Works in the cloud (credentials from env YT_TOKEN_JSON) and on the Mac (secrets/token.json).

    # check text and file, no network, no credentials needed:
    python3 scripts/upload.py video.mp4 --meta plan/short1/youtube.json --made-for-kids no --dry-run
    # real upload:
    python3 scripts/upload.py video.mp4 --meta plan/short1/youtube.json --made-for-kids no

--made-for-kids is required on purpose: it must reflect who the video is really for
(YouTube / COPPA rule), not a preference. The privacy is always "private".

The metadata file is JSON: title, description, tags (list), optional thumbnail (path relative
to the file), category_id (default "1" Film & Animation), language (default "en").
Uploading costs about 1650 API quota units; the default daily quota (10,000) allows ~6 uploads a day.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

LIMITS = {"title": 100, "description_bytes": 5000, "tags_chars": 500, "hashtags": 15}


def load_meta(path):
    path = Path(path)
    meta = json.loads(path.read_text(encoding="utf-8"))
    thumb = meta.get("thumbnail")
    if thumb:
        meta["thumbnail"] = str((path.parent / thumb).resolve())
    return meta


def validate_metadata(meta):
    """Return (errors, warnings). Errors would make YouTube reject or silently ignore the text."""
    errors, warnings = [], []
    title = meta.get("title", "")
    desc = meta.get("description", "")
    tags = meta.get("tags", [])
    if not title.strip():
        errors.append("title is empty")
    if len(title) > LIMITS["title"]:
        errors.append(f"title is {len(title)} characters, YouTube allows {LIMITS['title']}")
    elif len(title) > 60:
        warnings.append(f"title is {len(title)} characters; on phones over ~60 gets cut off")
    if "<" in title + desc or ">" in title + desc:
        errors.append("title/description must not contain < or >")
    if len(desc.encode("utf-8")) > LIMITS["description_bytes"]:
        errors.append(f"description is {len(desc.encode('utf-8'))} bytes, limit {LIMITS['description_bytes']}")
    n_hash = len({w.lower() for w in desc.split() if w.startswith("#") and len(w) > 1})
    if n_hash > LIMITS["hashtags"]:
        errors.append(f"{n_hash} hashtags: above {LIMITS['hashtags']} YouTube ignores ALL of them")
    elif n_hash == 0:
        warnings.append("no hashtags in the description")
    elif n_hash > 8:
        warnings.append(f"{n_hash} hashtags is spammy; 3-6 is the sweet spot")
    # YouTube counts the tag list as one string; a tag with a space is counted with quotes
    tag_chars = sum(len(t) + (2 if " " in t else 0) for t in tags) + max(len(tags) - 1, 0)
    if tag_chars > LIMITS["tags_chars"]:
        errors.append(f"tags total {tag_chars} characters, limit {LIMITS['tags_chars']}")
    if any(("<" in t or ">" in t) for t in tags):
        errors.append("tags must not contain < or >")
    if len(set(t.lower() for t in tags)) != len(tags):
        warnings.append("duplicate tags")
    return errors, warnings


def build_body(meta, made_for_kids):
    """The videos.insert body. Always private; the synthetic-media flag is always on
    (the video is made with AI tools; disclosing costs nothing)."""
    lang = meta.get("language", "en")
    return {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": list(meta.get("tags", [])),
            "categoryId": str(meta.get("category_id", "1")),
            "defaultLanguage": lang,
            "defaultAudioLanguage": lang,
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": bool(made_for_kids),
            "containsSyntheticMedia": True,
            "embeddable": True,
            "license": "youtube",
        },
    }


def probe_video(path):
    """Basic Shorts sanity check via ffprobe (skipped if ffprobe is missing)."""
    if not shutil.which("ffprobe"):
        return [], ["ffprobe not found, skipped video checks"]
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration,size", "-of", "json", str(path)],
        capture_output=True, text=True)
    try:
        j = json.loads(out.stdout)
        w, h = j["streams"][0]["width"], j["streams"][0]["height"]
        dur, size = float(j["format"]["duration"]), int(j["format"]["size"])
    except (ValueError, KeyError, IndexError):
        return ["ffprobe could not read the video"], []
    errors, warnings = [], []
    if h <= w:
        errors.append(f"video is {w}x{h}: not vertical, it will not be a Short")
    if dur > 180:
        errors.append(f"video is {dur:.0f}s; Shorts are up to 3 minutes")
    print(f"Video: {w}x{h}, {dur:.1f}s, {size / 1e6:.1f} MB")
    return errors, warnings


def _retry(fn, what, tries=5):
    """Retry transient API / network errors with backoff."""
    from googleapiclient.errors import HttpError
    delay = 2
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except HttpError as e:
            if e.resp.status not in (500, 502, 503, 504) or attempt == tries:
                raise
        except (ConnectionError, TimeoutError, OSError):
            if attempt == tries:
                raise
        print(f"  {what}: temporary error, retry {attempt}/{tries - 1} in {delay}s")
        time.sleep(delay)
        delay *= 2


def upload(yt, video, meta, made_for_kids):
    """Upload, set thumbnail (best effort), verify. Returns the video id."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    body = build_body(meta, made_for_kids)
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024,
                                                        resumable=True, mimetype="video/mp4"))
    resp, last = None, -1
    while resp is None:
        status, resp = _retry(req.next_chunk, "upload chunk")
        if status and int(status.progress() * 100) != last:
            last = int(status.progress() * 100)
            print(f"  {last}%")
    vid = resp["id"]
    print(f"Uploaded, video id {vid} (private)")  # print early: never upload twice if a later step fails

    thumb = meta.get("thumbnail")
    if thumb:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb)).execute()
            print("Thumbnail set")
        except HttpError as e:
            print(f"WARNING: thumbnail not set ({e.resp.status}). Pick the frame in Studio instead; "
                  "the video itself is uploaded fine.")

    try:
        got = yt.videos().list(part="status,snippet", id=vid).execute().get("items", [])
        if got:
            st = got[0]["status"]
            print("Check: privacy={} madeForKids={} syntheticMedia={} uploadStatus={}".format(
                st.get("privacyStatus"), st.get("madeForKids"), st.get("containsSyntheticMedia"),
                st.get("uploadStatus")))
    except HttpError as e:
        print(f"WARNING: could not read the video back ({e.resp.status}); open Studio to check.")
    return vid


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("--meta", required=True, help="JSON with title, description, tags, thumbnail")
    p.add_argument("--made-for-kids", required=True, choices=["yes", "no"])
    p.add_argument("--thumbnail", help="override the thumbnail path from the metadata file")
    p.add_argument("--dry-run", action="store_true", help="validate only: no credentials, no network")
    a = p.parse_args(argv)

    meta = load_meta(a.meta)
    if a.thumbnail:
        meta["thumbnail"] = a.thumbnail
    errors, warnings = validate_metadata(meta)
    if not Path(a.video).is_file():
        errors.append(f"video file not found: {a.video}")
    else:
        e2, w2 = probe_video(a.video)
        errors += e2
        warnings += w2
    if meta.get("thumbnail") and not Path(meta["thumbnail"]).is_file():
        errors.append(f"thumbnail not found: {meta['thumbnail']}")
    elif meta.get("thumbnail") and Path(meta["thumbnail"]).stat().st_size > 2 * 1024 * 1024:
        errors.append("thumbnail is over 2 MB (YouTube limit)")
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        return 1

    print(f"Title ({len(meta['title'])}): {meta['title']}")
    if a.dry_run:
        print(json.dumps(build_body(meta, a.made_for_kids == "yes"), ensure_ascii=False, indent=2))
        print("Dry run OK: nothing was uploaded.")
        return 0

    from yt_creds import CredentialsError, build_youtube, load_credentials
    try:
        yt = build_youtube(load_credentials(refresh=True))
    except CredentialsError as e:
        print(f"ERROR: {e}")
        return 2
    vid = upload(yt, a.video, meta, a.made_for_kids == "yes")
    print(f"Open in Studio and press Publish: https://studio.youtube.com/video/{vid}/edit")
    if meta.get("first_comment"):
        print("Pin this comment after publishing:\n  " + meta["first_comment"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
