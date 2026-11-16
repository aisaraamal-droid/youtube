#!/usr/bin/env python3
"""Self-test for mix_music.py. Needs only ffmpeg/ffprobe. Run:

    python3 scripts/test_mix_music.py

Builds a 10 s synthetic "video" whose audio is a 4 kHz tone in two bursts
(2-4 s and 6-8 s; stand-in for dialogue/SFX, at 4 kHz so it can be told apart
from the music) and a two-note chord (220/330 Hz) as music, only 4 s long on
purpose so looping is tested too.
Checks, on the mixed result:
  1. the music band is at least 6 dB lower while the bursts play than in the gaps,
  2. the music is still playing at the same level after the 4 s loop point,
  3. output duration matches the input,
  4. final integrated loudness is within 1.5 LU of the -14 LUFS target.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIX = HERE / "mix_music.py"


def ff(*args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args],
                          capture_output=True, text=True)


def rms_music_band(path, start, dur):
    """RMS (dB) of path[start:start+dur] below ~500 Hz (the music; the burst is 4 kHz)."""
    lp = "lowpass=f=500:poles=2," * 3
    r = ff("-ss", str(start), "-t", str(dur), "-i", str(path), "-vn",
           "-af", lp + "astats=metadata=1:reset=0", "-f", "null", "-")
    after = r.stderr.split("Overall", 1)[1]
    return float(re.search(r"RMS level dB:\s*(-?[\d.]+|-inf)", after).group(1))


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        ff("-y", "-f", "lavfi", "-i", "color=c=black:s=270x480:r=24:d=10",
           "-f", "lavfi", "-i",
           "sine=f=4000:r=48000:d=10,"
           "volume='if(between(t,2,4)+between(t,6,8),1.6,0)':eval=frame",
           "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
           "-shortest", str(d / "video.mp4"))
        ff("-y", "-f", "lavfi", "-i",
           "aevalsrc='0.35*sin(2*PI*220*t)+0.25*sin(2*PI*330*t)':s=48000:d=4",
           str(d / "music.wav"))

        out = d / "out.mp4"
        r = subprocess.run([sys.executable, "-I", str(MIX), str(d / "video.mp4"),
                            str(d / "music.wav"), str(out)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"mix_music.py failed:\n{r.stdout}\n{r.stderr}")

        first_gap = rms_music_band(out, 0.6, 1.2)   # before the loop point
        speech = rms_music_band(out, 2.4, 1.4)      # during the first burst
        gap = rms_music_band(out, 4.4, 1.4)         # after the 4 s loop point
        depth = gap - speech
        print(f"music band: first gap {first_gap:.1f} dB, during burst {speech:.1f} dB "
              f"(ducked {depth:.1f} dB), gap after loop point {gap:.1f} dB")

        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
        loud = ff("-i", str(out), "-vn", "-af", "ebur128", "-f", "null", "-").stderr
        lufs = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", loud)[-1])
        print(f"duration {dur:.2f} s, integrated loudness {lufs:.1f} LUFS")

        failures = []
        if depth < 6:
            failures.append(f"ducking only {depth:.1f} dB (want >= 6)")
        if gap < first_gap - 3:
            failures.append("music drops out after the loop point")
        if abs(dur - 10) > 0.1:
            failures.append(f"duration {dur:.2f} s != 10 s")
        if abs(lufs - (-14)) > 1.5:
            failures.append(f"loudness {lufs:.1f} LUFS not within 1.5 of -14")
        if failures:
            sys.exit("FAIL: " + "; ".join(failures))
        print("OK")


if __name__ == "__main__":
    main()
