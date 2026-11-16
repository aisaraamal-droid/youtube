# Music

`music/original/` holds our own theme (`kapi-theme.mp3`, `kapi-theme-bed.mp3`, `kapi-sting.mp3`), rendered by
`python3 scripts/make_theme.py` (needs numpy and ffmpeg). These are committed: they are our own work.

Drop other audio files you use here (`theme.mp3`, `bed.mp3`, ...). The files are git-ignored,
because library licences usually do not allow re-publishing the files themselves, and this
repository is public. (The `.gitignore` rules only cover files directly in `music/`, not `music/original/`.)

**Every track you use gets one row in `tracks.csv`**: where it came from, the licence, the
date you downloaded or generated it, whether credit is required and the exact credit text.
If a Content ID claim ever appears, this row (plus the licence page or plan receipt) is the
evidence for the dispute. Do not put payment details or account names in the file.

Mixing: `python3 scripts/mix_music.py <video> <music> <out>`; see `plan/music.md`.
