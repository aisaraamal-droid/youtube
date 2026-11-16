#!/usr/bin/env python3
"""Check that the stored YouTube credentials work, WITHOUT uploading anything.

    python3 scripts/yt_check.py

Refreshes the access token, then asks YouTube which channel the token belongs to.
Costs 1 quota unit. Exit code 0 = ready to upload, 2 = problem (message says what to do).
"""
import sys

from yt_creds import CredentialsError, build_youtube, load_credentials, read_info


def main():
    try:
        _, source = read_info()
        print(f"Credentials source: {source}")
        creds = load_credentials(refresh=True)
        print("Token refresh: OK")
        yt = build_youtube(creds)
        items = yt.channels().list(part="snippet,statistics", mine=True).execute().get("items", [])
    except CredentialsError as e:
        print(f"PROBLEM: {e}")
        return 2
    except Exception as e:  # network / API error: show the type, never a token
        print(f"PROBLEM: {type(e).__name__}: {str(e)[:300]}")
        return 2
    if not items:
        print("PROBLEM: the token is valid but the Google account has no YouTube channel.")
        return 2
    ch = items[0]
    sn, st = ch["snippet"], ch.get("statistics", {})
    print(f"Channel: {sn.get('title')} ({sn.get('customUrl', 'no handle')}), id {ch['id']}")
    print(f"Subscribers: {st.get('subscriberCount', 'hidden')}, videos: {st.get('videoCount', '?')}")
    print("Scopes: " + ", ".join(s.rsplit('/', 1)[-1] for s in (creds.scopes or [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
