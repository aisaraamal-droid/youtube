#!/usr/bin/env python3
"""Mix a quiet background music bed under a video's own audio, with ducking.

The video's existing audio (Rico's narration, character sounds, SFX) is used as
the side-chain key: whenever something is happening in it, the music is pushed
down; in the gaps it comes back up. The video stream is copied untouched.

Typical use, on the FINAL 30 s Short (after the two 15 s clips are joined, so
the music runs through the cut instead of restarting):

    python3 scripts/mix_music.py videos/short-01.mp4 music/theme.mp3 videos/short-01-music.mp4

Needs only ffmpeg/ffprobe on PATH. No third-party Python packages.

How the level is chosen
-----------------------
Loudness is measured (EBU R128) for the video audio and for the part of the
music that will be used. The music is then gained so that, before ducking, it
sits --offset LU below the video audio (default 12). The sidechain compressor
then pulls it down a further ~6-12 dB while something is audible (more for loud
voice/SFX; raise --ratio or lower --threshold for harder ducking). The result is
loudness-normalised to --target-lufs (YouTube plays at about -14 LUFS), so
re-running with a different track needs no manual volume tweaking.
"""
import argparse
import json
import math
import re
import shlex
import subprocess
import sys
from pathlib import Path


def sh(cmd, check=True):
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def probe(path):
    out = sh(["ffprobe", "-v", "error", "-print_format", "json",
              "-show_format", "-show_streams", str(path)]).stdout
    return json.loads(out)


def has_audio(info):
    return any(s.get("codec_type") == "audio" for s in info["streams"])


def duration_of(info):
    return float(info["format"]["duration"])


def measure_lufs(path, start=0.0, dur=None):
    """Integrated loudness (LUFS) of path[start:start+dur]; None if silent."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats"]
    if start:
        cmd += ["-ss", f"{start}"]
    if dur:
        cmd += ["-t", f"{dur}"]
    cmd += ["-i", str(path), "-vn",
            "-af", "loudnorm=I=-23:TP=-2:LRA=11:print_format=json",
            "-f", "null", "-"]
    err = sh(cmd, check=False).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S)
    if not m:
        return None
    value = float(json.loads(m.group(0))["input_i"])
    return value if math.isfinite(value) else None


def build_filter(args, duration, music_gain_db, voice_present):
    fade_out_start = max(duration - args.fade_out, 0)
    music = (
        f"[1:a]aresample=48000,aformat=channel_layouts=stereo,"
        f"atrim=duration={duration:.3f},asetpts=N/SR/TB,"
        f"volume={music_gain_db:.2f}dB,"
        f"afade=t=in:st=0:d={args.fade_in},"
        f"afade=t=out:st={fade_out_start:.3f}:d={args.fade_out}"
    )
    # loudnorm resamples to 192 kHz internally, so bring it back to 48 kHz.
    tail = f"aresample=48000,atrim=duration={duration:.3f}"
    if args.no_loudnorm:
        final = f"{tail}[aout]"
    else:
        final = (f"loudnorm=I={args.target_lufs}:TP=-1.5:LRA=11,{tail}[aout]")

    if not voice_present:
        # Video has no audio: the music is the whole soundtrack, nothing to duck.
        return music + f",{final}"

    return ";".join([
        music + "[music]",
        "[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[voice][key]",
        (f"[music][key]sidechaincompress=threshold={args.threshold}:"
         f"ratio={args.ratio}:attack={args.attack}:release={args.release}:"
         f"makeup=1[bed]"),
        "[voice][bed]amix=inputs=2:duration=first:dropout_transition=0:"
        "normalize=0[mix]",
        f"[mix]{final}",
    ])


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("music")
    p.add_argument("out")
    p.add_argument("--offset", type=float, default=12.0,
                   help="LU the music sits below the video audio before ducking (default 12)")
    p.add_argument("--music-start", type=float, default=0.0,
                   help="start offset inside the music file, seconds (default 0)")
    p.add_argument("--threshold", type=float, default=0.03,
                   help="sidechain threshold, linear 0.001-1 (default 0.03, about -30 dBFS)")
    p.add_argument("--ratio", type=float, default=4.0,
                   help="sidechain ratio 1-20 (default 4; higher ducks harder)")
    p.add_argument("--attack", type=float, default=15.0, help="ms (default 15)")
    p.add_argument("--release", type=float, default=350.0, help="ms (default 350)")
    p.add_argument("--fade-in", type=float, default=0.5, help="seconds (default 0.5)")
    p.add_argument("--fade-out", type=float, default=1.5, help="seconds (default 1.5)")
    p.add_argument("--target-lufs", type=float, default=-14.0,
                   help="final integrated loudness (default -14, YouTube's reference)")
    p.add_argument("--no-loudnorm", action="store_true",
                   help="skip the final loudness normalisation")
    p.add_argument("--dry-run", action="store_true",
                   help="print the ffmpeg command and exit")
    args = p.parse_args()

    video, music, out = Path(args.video), Path(args.music), Path(args.out)
    for f in (video, music):
        if not f.is_file():
            sys.exit(f"not found: {f}")
    if out.resolve() == video.resolve():
        sys.exit("output must be a different file than the input video")

    vinfo, minfo = probe(video), probe(music)
    if not has_audio(minfo):
        sys.exit(f"{music} has no audio stream")
    duration = duration_of(vinfo)
    voice_present = has_audio(vinfo)

    music_len = duration_of(minfo) - args.music_start
    if music_len <= 0:
        sys.exit("--music-start is past the end of the music file")

    voice_lufs = measure_lufs(video, 0, duration) if voice_present else None
    music_lufs = measure_lufs(music, args.music_start, min(duration, music_len))
    if music_lufs is None:
        sys.exit("could not measure the music loudness (silent file?)")

    if voice_present and voice_lufs is None:
        print("note: video audio is silent; treating it as having no audio",
              file=sys.stderr)
        voice_present = False

    if voice_present:
        gain = voice_lufs - args.offset - music_lufs
        print(f"video audio {voice_lufs:.1f} LUFS, music {music_lufs:.1f} LUFS "
              f"-> music gain {gain:+.1f} dB (sits {args.offset:.0f} LU under the "
              f"video audio before ducking)")
    else:
        gain = args.target_lufs - music_lufs
        print(f"video has no audio: music is the whole soundtrack, "
              f"no ducking (gain {gain:+.1f} dB)")

    flt = build_filter(args, duration, gain, voice_present)
    cmd = ["ffmpeg", "-hide_banner", "-y", "-i", str(video)]
    if args.music_start:
        cmd += ["-ss", f"{args.music_start}"]
    cmd += ["-stream_loop", "-1", "-i", str(music),
            "-filter_complex", flt,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out)]

    if args.dry_run:
        print(" ".join(shlex.quote(c) for c in cmd))
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{r.stderr[-2000:]}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
