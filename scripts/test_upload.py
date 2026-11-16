#!/usr/bin/env python3
"""Self-test for yt_creds.py and upload.py. No network, no real credentials. Run:

    python3 scripts/test_upload.py

Needs the packages from scripts/requirements.txt. Checks: credentials come from the
environment (and never leak into error messages), a dead refresh token gives a clear message,
metadata limits are enforced, the upload body is private + not-for-kids-as-told + synthetic flag,
and the upload -> thumbnail -> verify call order works against a fake YouTube service.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import yt_creds  # noqa: E402
import upload  # noqa: E402

FAKE = {"client_id": "cid.apps.googleusercontent.com", "client_secret": "SECRET-VALUE-123",
        "refresh_token": "REFRESH-VALUE-456", "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": yt_creds.SCOPES}
passed = 0


def check(name, cond):
    global passed
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        sys.exit(1)
    passed += 1


def clear_env():
    for k in (yt_creds.ENV_JSON, *yt_creds.ENV_SPLIT):
        os.environ.pop(k, None)


# ---- credentials ----------------------------------------------------------------------------
clear_env()
yt_creds.SECRETS = Path(tempfile.mkdtemp())  # empty folder: no local token.json
try:
    yt_creds.load_credentials(refresh=False)
    check("no credentials -> error", False)
except yt_creds.CredentialsError as e:
    check("no credentials -> error names YT_TOKEN_JSON", "YT_TOKEN_JSON" in str(e))

os.environ["YT_TOKEN_JSON"] = json.dumps(FAKE)
c = yt_creds.load_credentials(refresh=False)
check("YT_TOKEN_JSON parsed", c.refresh_token == FAKE["refresh_token"] and c.client_id == FAKE["client_id"])

os.environ["YT_TOKEN_JSON"] = "'" + json.dumps(FAKE) + "'\n"
check("quotes/newline around the value tolerated",
      yt_creds.load_credentials(refresh=False).client_secret == FAKE["client_secret"])

os.environ["YT_TOKEN_JSON"] = "{not json SECRET-VALUE-123"
try:
    yt_creds.load_credentials(refresh=False)
    check("bad JSON -> error", False)
except yt_creds.CredentialsError as e:
    check("bad JSON -> error without leaking the value", "SECRET-VALUE-123" not in str(e))

clear_env()
os.environ.update({"YT_CLIENT_ID": "a", "YT_CLIENT_SECRET": "b", "YT_REFRESH_TOKEN": "c"})
check("split env vars work", yt_creds.load_credentials(refresh=False).refresh_token == "c")

clear_env()
os.environ["YT_TOKEN_JSON"] = json.dumps({"client_id": "x"})
try:
    yt_creds.load_credentials(refresh=False)
    check("incomplete token -> error", False)
except yt_creds.CredentialsError as e:
    check("incomplete token -> says what is missing", "refresh_token" in str(e))

# dead refresh token (invalid_grant) -> actionable message
from google.auth.exceptions import RefreshError  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402

os.environ["YT_TOKEN_JSON"] = json.dumps(FAKE)
orig = Credentials.refresh


def dead(self, request):
    raise RefreshError("invalid_grant: Token has been expired or revoked.",
                       {"error": "invalid_grant"})


Credentials.refresh = dead
try:
    yt_creds.load_credentials(refresh=True)
    check("invalid_grant -> error", False)
except yt_creds.CredentialsError as e:
    msg = str(e)
    check("invalid_grant explains Testing/7 days and the fix",
          "In production" in msg and "auth.py" in msg and "REFRESH-VALUE-456" not in msg)
finally:
    Credentials.refresh = orig
clear_env()

# ---- metadata -------------------------------------------------------------------------------
meta = upload.load_meta(HERE.parent / "plan" / "short1" / "youtube.json")
errs, warns = upload.validate_metadata(meta)
check("real Short #1 metadata has no errors", not errs)
check("real Short #1 metadata has no warnings", not warns)
check("thumbnail path resolved", Path(meta["thumbnail"]).is_file())

bad = {"title": "x" * 101, "description": "a <b> #1 #2 #3 #4 #5 #6 #7 #8 #9 #10 #11 #12 #13 #14 #15 #16",
       "tags": ["t" * 300, "u" * 300]}
errs, _ = upload.validate_metadata(bad)
check("long title caught", any("title is 101" in e for e in errs))
check("angle brackets caught", any("< or >" in e for e in errs))
check("16 hashtags caught", any("hashtags" in e for e in errs))
check("tags over 500 chars caught", any("tags total" in e for e in errs))

body = upload.build_body(meta, made_for_kids=False)
check("always private", body["status"]["privacyStatus"] == "private")
check("made for kids follows the flag", body["status"]["selfDeclaredMadeForKids"] is False)
check("synthetic media flag on", body["status"]["containsSyntheticMedia"] is True)
check("language set", body["snippet"]["defaultLanguage"] == "en")
check("kids flag yes is honoured",
      upload.build_body(meta, made_for_kids=True)["status"]["selfDeclaredMadeForKids"] is True)

# ---- upload call order against a fake service -----------------------------------------------
calls = []


class Req:
    def __init__(self, name, result=None):
        self.name, self.result = name, result

    def next_chunk(self):
        calls.append(self.name + ".next_chunk")
        return None, self.result

    def execute(self):
        calls.append(self.name + ".execute")
        return self.result


class FakeYT:
    def videos(self):
        return SimpleNamespace(
            insert=lambda **kw: (calls.append("insert:" + kw["body"]["status"]["privacyStatus"]) or Req("insert", {"id": "VID123"})),
            list=lambda **kw: Req("list", {"items": [{"status": {"privacyStatus": "private", "madeForKids": False,
                                                             "containsSyntheticMedia": True,
                                                             "uploadStatus": "uploaded"}}]}))

    def thumbnails(self):
        return SimpleNamespace(set=lambda **kw: Req("thumb"))


with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
    f.write(b"fake video bytes")
    f.flush()
    vid = upload.upload(FakeYT(), f.name, meta, False)
check("upload returns the video id", vid == "VID123")
check("order: insert -> thumbnail -> verify",
      calls == ["insert:private", "insert.next_chunk", "thumb.execute", "list.execute"])

# dry run on the real draft (only if the draft file is around)
draft = Path("/mnt/project-files/kapi-test/kapi-short1-draft-1080x1920.mp4")
if draft.exists():
    rc = upload.main([str(draft), "--meta", str(HERE.parent / "plan/short1/youtube.json"),
                      "--made-for-kids", "no", "--dry-run"])
    check("dry run on the real draft passes", rc == 0)

print(f"\nAll {passed} checks passed.")
