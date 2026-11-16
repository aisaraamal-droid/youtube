"""Load YouTube OAuth credentials for scripts that run in the cloud or on the Mac.

Order of lookup (first hit wins):
  1. env YT_TOKEN_JSON: the whole content of token.json (one line);
  2. env YT_CLIENT_ID + YT_CLIENT_SECRET + YT_REFRESH_TOKEN;
  3. secrets/token.json next to the repo (local computer only, git-ignored).

Nothing here ever prints a token, secret or refresh token; error messages say
what is wrong and what to do, never the value.
"""
import json
import os
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
SECRETS = Path(__file__).resolve().parent.parent / "secrets"
ENV_JSON = "YT_TOKEN_JSON"
ENV_SPLIT = ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")
TOKEN_URI = "https://oauth2.googleapis.com/token"


class CredentialsError(RuntimeError):
    """Human-readable problem with the stored YouTube credentials."""


def _clean(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        raw = raw[1:-1].strip()
    return raw


def read_info():
    """Return (info_dict, source_label). Raises CredentialsError if nothing is set."""
    raw = os.environ.get(ENV_JSON, "")
    if raw.strip():
        try:
            info = json.loads(_clean(raw))
        except ValueError:
            raise CredentialsError(
                f"{ENV_JSON} is set but is not valid JSON. Paste the whole content of "
                "token.json as one value (no extra text before or after).") from None
        if not isinstance(info, dict):
            raise CredentialsError(f"{ENV_JSON} must be a JSON object (the content of token.json).")
        return info, f"env {ENV_JSON}"

    parts = [os.environ.get(k, "").strip() for k in ENV_SPLIT]
    if all(parts):
        return ({"client_id": parts[0], "client_secret": parts[1],
                 "refresh_token": parts[2], "token_uri": TOKEN_URI}, "env YT_CLIENT_ID/SECRET/REFRESH_TOKEN")

    path = SECRETS / "token.json"
    if path.exists():
        try:
            return json.loads(path.read_text()), f"file {path}"
        except ValueError:
            raise CredentialsError(f"{path} is not valid JSON; run scripts/auth.py again.") from None

    raise CredentialsError(
        f"No YouTube credentials found. Set the environment variable {ENV_JSON} (content of "
        "token.json) in the cloud environment settings, or put secrets/token.json on your computer. "
        "See plan/cloud-upload.md.")


def load_credentials(refresh=True):
    """Build google Credentials; with refresh=True also fetches a fresh access token now,
    so a dead refresh token is reported clearly before any upload starts."""
    from google.auth.exceptions import RefreshError, TransportError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    info, source = read_info()
    missing = [k for k in ("client_id", "client_secret", "refresh_token") if not info.get(k)]
    if missing:
        raise CredentialsError(f"Credentials from {source} lack: {', '.join(missing)}. "
                               "Run scripts/auth.py again and copy the new token.json.")
    creds = Credentials.from_authorized_user_info(info, scopes=info.get("scopes") or SCOPES)
    if refresh:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            text = str(e)
            if "invalid_grant" in text:
                raise CredentialsError(
                    "Google refused the refresh token (invalid_grant). It was revoked or it expired. "
                    "Most common cause: the OAuth consent screen is in 'Testing', where refresh "
                    "tokens die 7 days after they were issued. Remove the app's access at "
                    "myaccount.google.com/permissions, run scripts/auth.py again on your computer "
                    f"and update {ENV_JSON} (plan/cloud-upload.md).") from None
            if "invalid_client" in text or "unauthorized_client" in text:
                raise CredentialsError(
                    "Google does not recognise the OAuth client (invalid_client). The client_id / "
                    "client_secret in the credentials do not match the Google Cloud project; "
                    "copy a fresh token.json made with the right client_secret.json.") from None
            raise CredentialsError(f"Google refused to refresh the token: {text.splitlines()[0][:200]}") from None
        except TransportError as e:
            raise CredentialsError(
                "Could not reach oauth2.googleapis.com. In a cloud session add this host (and "
                f"youtube.googleapis.com) to the environment's allowed hosts. Detail: {str(e)[:150]}") from None
    return creds


def build_youtube(creds):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=creds, cache_discovery=False)
