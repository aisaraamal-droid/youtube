# Kapi's World (@KapisWorldTV)

Plans, scripts and finished videos for the Kapi's World YouTube channel.

**This repository is public.** Never commit `client_secret.json`, OAuth tokens or API keys. Keep them outside the repo or in environment variables. `.gitignore` blocks the common names.

## Layout

- `plan/` content plan and episode scripts
- `scripts/` pipeline code (generate, edit with ffmpeg, upload)
- `videos/` finished videos (large files: prefer Releases or Git LFS)

## Workflow

1. Scripts are written into `plan/`, the owner approves them.
2. Clips are generated, then edited with ffmpeg.
3. The owner reviews the final video.
4. Upload is private with metadata and the made-for-kids flag; publishing is done by the owner after approval.
