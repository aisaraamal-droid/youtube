#!/usr/bin/env python3
"""Render the original Kapi theme (and a quiet "bed" version and a closing sting).

This is our own composition, synthesised from scratch with numpy, so there is
no third-party licence, no Content ID fingerprint and nothing to credit. The
mood brief (see plan/music.md): about 108 BPM, E minor, marimba plucks, round
bass, light Afro-house groove, a little wistful, playful on top. The melody and
chord moves are original; nothing here is taken from any existing song.

Output (default music/original/):
  kapi-theme.mp3      full theme, 32 bars (about 71 s), loops seamlessly
  kapi-theme-bed.mp3  same without the lead melody: for under narration
  kapi-sting.mp3      about 3.5 s closing sting for the punchline

Needs numpy and ffmpeg. Deterministic: same seed, same audio.

    python3 scripts/make_theme.py [--out-dir music/original] [--seed 7]
"""
import argparse
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 48000
BPM = 108
STEP = 60.0 / BPM / 4          # one sixteenth note, seconds
BAR = STEP * 16
TAIL = 3.0                     # seconds of ring-out folded back onto the start

# ---------------------------------------------------------------- music data

_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name):
    """'F#4' -> 66."""
    pc, i = _PC[name[0]], 1
    if name[i] in "#b":
        pc += 1 if name[i] == "#" else -1
        i += 1
    return 12 * (int(name[i:]) + 1) + pc


def hz(name):
    return 440.0 * 2 ** ((midi(name) - 69) / 12)


# root (bass), pad tones, arpeggio tones
CHORDS = {
    "Em":    ("E2", ["E3", "G3", "B3", "E4"], ["E4", "G4", "B4", "E5"]),
    "Cmaj7": ("C3", ["C3", "E3", "G3", "B3"], ["C4", "E4", "G4", "B4"]),
    "Am7":   ("A2", ["A2", "E3", "G3", "C4"], ["A3", "C4", "E4", "G4"]),
    "B7":    ("B2", ["B2", "D#3", "F#3", "A3"], ["F#4", "A4", "B4", "D#5"]),
    "D":     ("D3", ["D3", "A3", "D4", "F#4"], ["D4", "F#4", "A4", "D5"]),
    "Bm7":   ("B2", ["B2", "F#3", "A3", "D4"], ["B3", "D4", "F#4", "A4"]),
}

PROG_A = ["Em", "Cmaj7", "Am7", "B7"]
PROG_B = ["Cmaj7", "D", "Bm7", "Em"]
PROG_B_END = ["Cmaj7", "D", "B7", "B7"]      # leans back into Em at the loop point

# 32 bars: 16 bars of A, then 16 bars of B (last bars lean back to the start)
CHORD_PER_BAR = PROG_A * 4 + PROG_B * 3 + PROG_B_END

# melody: per bar a list of (sixteenth-step, note, length in steps)
LEAD_A1 = [
    [(0, "B4", 2), (2, "E5", 3), (6, "D5", 2), (8, "B4", 4), (14, "A4", 2)],
    [(0, "G4", 3), (4, "B4", 2), (6, "C5", 2), (8, "B4", 3), (12, "G4", 2)],
    [(0, "A4", 2), (2, "C5", 2), (4, "E5", 4), (10, "D5", 2), (12, "C5", 2), (14, "A4", 2)],
    [(0, "F#4", 3), (4, "A4", 2), (6, "B4", 2), (8, "D#5", 4), (12, "E5", 3)],
]
LEAD_A2 = [
    [(0, "E5", 2), (2, "G5", 3), (6, "E5", 2), (8, "D5", 4), (14, "B4", 2)],
    [(0, "C5", 3), (4, "E5", 2), (6, "D5", 2), (8, "B4", 3), (12, "C5", 2)],
    [(0, "A4", 2), (2, "C5", 2), (4, "D5", 2), (6, "E5", 2), (8, "C5", 4), (14, "B4", 2)],
    [(0, "A4", 3), (4, "F#4", 2), (6, "A4", 2), (8, "B4", 6)],
]
LEAD_B = [
    [(0, "E5", 1), (2, "E5", 1), (4, "G5", 2), (8, "E5", 2), (11, "D5", 1), (12, "C5", 3)],
    [(0, "F#5", 1), (2, "F#5", 1), (4, "A5", 2), (8, "F#5", 2), (11, "E5", 1), (12, "D5", 3)],
    [(0, "D5", 2), (3, "F#5", 2), (6, "E5", 2), (8, "D5", 2), (11, "B4", 2), (14, "A4", 2)],
    [(0, "G4", 2), (2, "B4", 2), (4, "E5", 6), (12, "D5", 2), (14, "B4", 2)],
]
LEAD_B_END = LEAD_B[:2] + [
    [(0, "D5", 2), (3, "F#5", 2), (6, "E5", 2), (8, "D5", 2), (11, "B4", 2), (14, "A4", 2)],
    [(0, "F#4", 2), (4, "A4", 2), (8, "D#5", 6)],
]

# bar index -> melody for that bar (None = no lead: the intro and one breath)
LEAD_PER_BAR = (
    [None] * 4                       # bars 0-3: intro, groove first
    + LEAD_A1                        # 4-7
    + LEAD_A2                        # 8-11
    + LEAD_A1                        # 12-15
    + LEAD_B + LEAD_B + LEAD_B       # 16-27
    + LEAD_B_END                     # 28-31
)
INTRO_BARS = 2

# drum / bass patterns on the sixteenth grid
KICK = [0, 4, 8, 12]
CLAP = [4, 12]
CONGA = [(3, 1.0), (6, 0.7), (10, 1.0), (11, 0.7), (14, 1.0)]
BASS = [(0, 0, 4), (6, 0, 2), (10, 12, 2), (14, 7, 2)]   # step, semitone offset, length
ARP_STEPS = [(0, 0), (3, 2), (6, 1), (10, 3), (12, 2)]    # step, chord-tone index

# ------------------------------------------------------------------- voices


def t_axis(seconds):
    return np.arange(int(seconds * SR)) / SR


def marimba(freq, length_s, bright=1.0):
    """Struck wooden bar: fundamental plus fast-dying overtones near 4x and 9x."""
    tau = float(np.clip(0.55 * (330.0 / freq) ** 0.35, 0.12, 0.9))
    t = t_axis(min(tau * 5, 1.8))
    s = np.sin(2 * np.pi * freq * t) * np.exp(-t / tau)
    s += 0.30 * bright * np.sin(2 * np.pi * freq * 3.97 * t) * np.exp(-t / (tau * 0.25))
    s += 0.10 * bright * np.sin(2 * np.pi * freq * 9.2 * t) * np.exp(-t / (tau * 0.08))
    s *= np.minimum(t / 0.002, 1.0)
    s *= np.where(t > length_s, np.exp(-(t - length_s) / 0.05), 1.0)  # damp after the written length
    return s


def bass(freq, length_s):
    t = t_axis(length_s + 0.12)
    s = (np.sin(2 * np.pi * freq * t)
         + 0.45 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t / 0.20)
         + 0.20 * np.sin(2 * np.pi * freq * 3 * t) * np.exp(-t / 0.10))
    env = np.minimum(t / 0.005, 1.0) * (0.35 + 0.65 * np.exp(-t / 0.30))
    env *= np.where(t > length_s, np.exp(-(t - length_s) / 0.04), 1.0)
    return np.tanh(1.3 * s * env) / 1.3


def kick():
    t = t_axis(0.4)
    phase = 2 * np.pi * np.cumsum(46 + 95 * np.exp(-t / 0.028)) / SR
    return np.sin(phase) * np.exp(-t / 0.15) * np.minimum(t / 0.001, 1.0)


def hiss(rng, seconds):
    n = rng.standard_normal(int(seconds * SR) + 1)
    return np.diff(n)                       # first difference = crude high-pass


def clap(rng):
    t = t_axis(0.25)
    env = np.exp(-t / 0.05)
    for off in (0.0, 0.011, 0.022):
        env += np.where(t >= off, np.exp(-(t - off) / 0.006), 0.0)
    return hiss(rng, 0.25)[: len(t)] * env * 0.5


def shaker(rng):
    t = t_axis(0.09)
    return hiss(rng, 0.09)[: len(t)] * np.exp(-t / 0.018) * np.minimum(t / 0.003, 1.0)


def conga(rng, freq):
    t = t_axis(0.3)
    s = np.sin(2 * np.pi * freq * (1 + 0.25 * np.exp(-t / 0.02)) * t) * np.exp(-t / 0.11)
    s += 0.15 * hiss(rng, 0.3)[: len(t)] * np.exp(-t / 0.01)
    return s


def pad(freqs, seconds):
    t = t_axis(seconds)
    s = np.zeros_like(t)
    for f in freqs:
        s += np.sin(2 * np.pi * f * t) + 0.7 * np.sin(2 * np.pi * f * 1.004 * t)
        s += 0.15 * np.sin(2 * np.pi * f * 2 * t)
    env = np.minimum(t / 0.35, 1.0) * np.minimum((seconds - t) / 0.45, 1.0)
    return s * env / len(freqs)


# --------------------------------------------------------------------- mixer


class Mix:
    def __init__(self, seconds):
        self.n = int(seconds * SR)
        self.dry = np.zeros((self.n, 2))
        self.send = np.zeros((self.n, 2))

    def add(self, t0, sig, gain, pan=0.0, wet=0.0):
        i = int(round(t0 * SR))
        n = min(len(sig), self.n - i)
        if n <= 0 or i < 0:
            return
        th = (pan + 1) * np.pi / 4
        for ch, g in enumerate((np.cos(th), np.sin(th))):
            self.dry[i:i + n, ch] += sig[:n] * gain * g
            if wet:
                self.send[i:i + n, ch] += sig[:n] * gain * g * wet


def reverb(send, rng, seconds=1.3, decay=0.38):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)) * np.exp(-t / decay)[:, None]
    ir /= np.sqrt((ir ** 2).sum(0))
    size = 1 << int(np.ceil(np.log2(len(send) + n)))
    out = np.zeros((len(send) + n, 2))
    for ch in range(2):
        out[:, ch] = np.fft.irfft(np.fft.rfft(send[:, ch], size) * np.fft.rfft(ir[:, ch], size), size)[: len(send) + n]
    return out


def fold_loop(x, length):
    """Wrap everything past `length` back onto the start so the loop is seamless."""
    out = x[:length].copy()
    rest = x[length:]
    out[: len(rest)] += rest[:length]
    return out


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def to_mp3(wav, mp3, lufs=-16.0):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
         "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=9,aresample={SR}",
         "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)], check=True)


# ------------------------------------------------------------------- arranger


def render_theme(rng, with_lead):
    bars = len(CHORD_PER_BAR)
    m = Mix(bars * BAR + TAIL)

    def jitter(scale=0.004):
        return rng.uniform(-scale, scale)

    def vel(base, spread=0.1):
        return base * (1 + rng.uniform(-spread, spread))

    for b, chord in enumerate(CHORD_PER_BAR):
        t0 = b * BAR
        root, tones, arp = CHORDS[chord]
        groove = b >= INTRO_BARS

        m.add(t0, pad([hz(x) for x in tones], BAR + 0.45), 0.07, 0.0, wet=0.5)

        for s, idx in ARP_STEPS:
            note = arp[idx % 4]
            m.add(t0 + s * STEP + jitter(), marimba(hz(note), 0.3, 0.8),
                  vel(0.30 if groove else 0.20), -0.35, wet=0.45)

        for s in range(16):
            accent = [0.55, 0.2, 0.35, 0.2][s % 4] * (1.25 if s % 4 == 2 else 1.0)
            m.add(t0 + s * STEP + jitter(0.003), shaker(rng), vel(0.13 * accent / 0.35), 0.3 if s % 2 else -0.3)
        for s, strength in CONGA:
            f = 230 if strength >= 1.0 else 165
            m.add(t0 + s * STEP + jitter(), conga(rng, f), vel(0.22 * strength), 0.45, wet=0.2)

        if groove:
            for s in KICK:
                m.add(t0 + s * STEP, kick(), vel(0.36, 0.05), 0.0)
            for s in CLAP:
                m.add(t0 + s * STEP + jitter(0.003), clap(rng), vel(0.30), 0.1, wet=0.35)
            for s, semis, ln in BASS:
                f = hz(root) * 2 ** (semis / 12)
                m.add(t0 + s * STEP, bass(f, ln * STEP * 0.92), vel(0.38, 0.05), 0.0)

        bar_lead = LEAD_PER_BAR[b]
        if with_lead and bar_lead:
            for s, note, ln in bar_lead:
                m.add(t0 + s * STEP + jitter(), marimba(hz(note), ln * STEP * 1.5, 1.1),
                      vel(0.50), 0.25, wet=0.55)

    wet = reverb(m.send, rng)
    wet_scale = 0.30 * np.sqrt((m.send ** 2).mean()) / max(np.sqrt((wet ** 2).mean()), 1e-9)
    full = np.zeros_like(wet)
    full[: m.n] += m.dry
    full += wet * wet_scale
    out = fold_loop(full, int(bars * BAR * SR))
    return out / max(np.abs(out).max(), 1e-9) * 0.89


def render_sting(rng):
    m = Mix(3.5 + 1.5)
    notes = ["E4", "G4", "B4", "F#5", "E5"]
    for i, name in enumerate(notes):
        m.add(i * STEP * 1.5, marimba(hz(name), 0.6, 1.0), 0.45, -0.2 + 0.1 * i, wet=0.55)
    t_end = len(notes) * STEP * 1.5 + 0.1
    m.add(t_end, pad([hz(x) for x in ["E3", "G3", "B3", "F#4"]], 2.5), 0.20, 0.0, wet=0.5)
    m.add(t_end, bass(hz("E2"), 0.9), 0.55, 0.0)
    m.add(t_end, kick(), 0.6, 0.0)
    m.add(t_end, clap(rng), 0.3, 0.1, wet=0.4)
    for name in ["E5", "B5"]:
        m.add(t_end, marimba(hz(name), 1.4, 1.0), 0.35, 0.2, wet=0.6)
    wet = reverb(m.send, rng)
    wet_scale = 0.30 * np.sqrt((m.send ** 2).mean()) / max(np.sqrt((wet ** 2).mean()), 1e-9)
    out = np.zeros_like(wet)
    out[: m.n] += m.dry
    out += wet * wet_scale
    out = out[: int(4.8 * SR)]
    out *= np.minimum((len(out) - np.arange(len(out))) / (0.6 * SR), 1.0)[:, None]  # fade the tail
    return out / max(np.abs(out).max(), 1e-9) * 0.89


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent / "music" / "original"))
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, make in [
            ("kapi-theme", lambda: render_theme(np.random.default_rng(args.seed), True)),
            ("kapi-theme-bed", lambda: render_theme(np.random.default_rng(args.seed), False)),
            ("kapi-sting", lambda: render_sting(np.random.default_rng(args.seed))),
        ]:
            wav = Path(tmp) / f"{name}.wav"
            write_wav(wav, make())
            to_mp3(wav, out_dir / f"{name}.mp3")
            print(f"wrote {out_dir / (name + '.mp3')}")


if __name__ == "__main__":
    main()
