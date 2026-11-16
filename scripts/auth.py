"""One-time Google sign-in. Run on YOUR computer.

Put client_secret.json into the secrets/ folder (it is git-ignored), then:
    python scripts/auth.py
A browser opens; sign in with the Google account that owns the channel.
The refresh token is saved to secrets/token.json (also git-ignored).

For the cloud: copy it WITHOUT opening it or pasting it in a chat:
    pbcopy < secrets/token.json
and paste into the environment variable YT_TOKEN_JSON (see plan/cloud-upload.md).
"""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
SECRETS = Path(__file__).resolve().parent.parent / "secrets"

if __name__ == "__main__":
    flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS / "client_secret.json"), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    (SECRETS / "token.json").write_text(creds.to_json())
    print("Saved secrets/token.json. Next: pbcopy < secrets/token.json, then paste into YT_TOKEN_JSON (plan/cloud-upload.md)")
