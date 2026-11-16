#!/usr/bin/env python3
"""Read back the state of uploaded videos (title, privacy, made-for-kids, processing). 1 quota unit per call.

    python3 scripts/yt_status.py VIDEO_ID [VIDEO_ID ...]
"""
import sys

from yt_creds import build_youtube, load_credentials


def main(ids):
    yt = build_youtube(load_credentials(refresh=True))
    items = yt.videos().list(part="snippet,status,processingDetails,contentDetails", id=",".join(ids)).execute().get("items", [])
    found = {v["id"] for v in items}
    for v in items:
        st, sn = v["status"], v["snippet"]
        print(f"{v['id']}  privacy={st.get('privacyStatus')}  madeForKids={st.get('madeForKids')}  "
              f"selfDeclaredMadeForKids={st.get('selfDeclaredMadeForKids')}  upload={st.get('uploadStatus')}  "
              f"processing={v.get('processingDetails', {}).get('processingStatus')}  "
              f"duration={v['contentDetails'].get('duration')}  title={sn['title']!r}")
    for i in ids:
        if i not in found:
            print(f"{i}  NOT FOUND")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
