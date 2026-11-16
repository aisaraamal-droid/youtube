#!/usr/bin/env python3
"""Where is the spoken line inside a generated clip? Prints words with start/end seconds.

    python3 scripts/speech_times.py clips/c1.mp4 ["expected line"]

Uses pocketsphinx (pip install pocketsphinx), offline. With an expected line it aligns that
text to the audio (forced alignment), which is far more reliable on generated voices than free
recognition; without one it prints what the recogniser hears. Used to time the Rico captions.
"""
import subprocess
import sys


def pcm16k(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                           "-f", "s16le", "-"], capture_output=True, check=True).stdout


def words(path, text=None):
    from pocketsphinx import Decoder
    dec = Decoder(samprate=16000, loglevel="FATAL")
    pcm = pcm16k(path)
    if text:
        clean = "".join(ch for ch in text.lower() if ch.isalpha() or ch in " '")
        dec.set_align_text(clean)
    dec.start_utt()
    dec.process_raw(pcm, False, True)
    dec.end_utt()
    return [(s.word, s.start_frame / 100, s.end_frame / 100) for s in dec.seg()
            if s.word not in ("<s>", "</s>", "<sil>", "[NOISE]", "[SPEECH]")]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for w, a, b in words(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None):
        print(f"{a:6.2f} {b:6.2f}  {w}")
