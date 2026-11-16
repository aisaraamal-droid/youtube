#!/usr/bin/env python3
"""Assemble the Kapi-in-the-League Short draft from generated 480p clips.

Steps: upscale each clip to 1080x1920 (Lanczos + light sharpen + grade),
join with short cross-dissolves, burn in ASS graphics (title, name tags,
scoreboard, Rico captions, end card), add small sound effects, loudness-normalise.
No paid generation happens here, only local ffmpeg.
"""
import json, os, subprocess, sys

HERE = os.getcwd()  # run from the project folder; outputs go to ./work
CFG = json.load(open(os.path.join(HERE, sys.argv[1])))
OUT = sys.argv[2]
W, H = 1080, 1920
FADE = CFG.get("fade", 0.2)
FONT = "Inter ExtraBold"
FONT_B = "Inter"


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                       capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def ts(t):
    t = max(t, 0)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def rrect(w, h, r):
    k = 0.5523 * r
    return (f"m {r} 0 l {w-r} 0 b {w-r+k:.1f} 0 {w} {r-k:.1f} {w} {r} l {w} {h-r} "
            f"b {w} {h-r+k:.1f} {w-r+k:.1f} {h} {w-r} {h} l {r} {h} "
            f"b {r-k:.1f} {h} 0 {h-r+k:.1f} 0 {h-r} l 0 {r} b 0 {r-k:.1f} {r-k:.1f} 0 {r} 0")


def bgr(hexrgb):
    hexrgb = hexrgb.lstrip("#")
    return hexrgb[4:6] + hexrgb[2:4] + hexrgb[0:2]


class Ass:
    def __init__(self):
        self.lines = []

    def box(self, t0, t1, x, y, w, h, r, color, alpha=0x30, fin=0.18, fout=0.18, slide=0):
        # alpha: 00 opaque .. FF transparent
        mv = f"\\move({x-slide},{y},{x},{y},0,{int(fin*1000)})" if slide else f"\\pos({x},{y})"
        self.lines.append(
            f"Dialogue: 1,{ts(t0)},{ts(t1)},Box,,0,0,0,,{{\\an7{mv}\\fad({int(fin*1000)},{int(fout*1000)})"
            f"\\1c&H{bgr(color)}&\\1a&H{alpha:02X}&\\bord0\\shad0\\p1}}{rrect(w,h,r)}{{\\p0}}")

    def text(self, t0, t1, x, y, s, size, color="FFFFFF", font=FONT, an=7, fin=0.18, fout=0.18,
             slide=0, bord=0, bordc="000000", shad=0, extra="", layer=2, spacing=0):
        mv = f"\\move({x-slide},{y},{x},{y},0,{int(fin*1000)})" if slide else f"\\pos({x},{y})"
        self.lines.append(
            f"Dialogue: {layer},{ts(t0)},{ts(t1)},Txt,,0,0,0,,{{\\an{an}{mv}\\fad({int(fin*1000)},{int(fout*1000)})"
            f"\\fn{font}\\fs{size}\\1c&H{bgr(color)}&\\3c&H{bgr(bordc)}&\\bord{bord}\\shad{shad}\\fsp{spacing}{extra}}}{s}")

    def raw(self, line):
        self.lines.append(line)

    def render(self):
        head = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            f"Style: Txt,{FONT},60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
            f"Style: Box,{FONT},60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
        return head + "\n".join(self.lines) + "\n"


def main():
    clips = CFG["clips"]
    durs = [probe(os.path.join(HERE, c["file"])) for c in clips]
    starts = []
    t = 0.0
    for i, d in enumerate(durs):
        starts.append(t)
        t += d - (FADE if i < len(durs) - 1 else 0)
    body_len = t
    tail = CFG.get("tail_hold", 0.8)
    total = body_len + tail
    print("clip durations", [round(d, 2) for d in durs], "starts", [round(s, 2) for s in starts], "body", round(body_len, 2), "total", round(total, 2))

    def T(spec):
        """Resolve {"clip": i, "t": x | [a, b]} (clip-local) or {"t": ...} (global) to absolute seconds."""
        base = starts[spec["clip"]] if "clip" in spec else 0.0
        t = spec["t"]
        return tuple(base + x for x in t) if isinstance(t, list) else base + t

    # ---- upscale each clip ------------------------------------------------
    prepped = []
    for i, c in enumerate(clips):
        src = os.path.join(HERE, c["file"])
        dst = os.path.join(HERE, "work", f"p{i}.mp4")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        vf = (f"scale=-2:{H}:flags=lanczos,crop={W}:{H},"
              "unsharp=5:5:0.6:5:5:0.0,"
              "eq=contrast=1.04:saturation=1.10:gamma=0.98,"
              "vignette=PI/6,fps=24,format=yuv420p")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf,
                        "-af", "aresample=48000,aformat=channel_layouts=stereo",
                        "-c:v", "libx264", "-crf", "14", "-preset", "slow", "-c:a", "pcm_s16le", dst], check=True)
        prepped.append(dst)

    # ---- graphics ---------------------------------------------------------
    a = Ass()
    g = CFG["graphics"]
    # scoreboard (persistent)
    sb_x, sb_y = 56, 150
    st = T(g["score"])
    a.box(0.2, total, sb_x, sb_y, 600, 96, 24, "0B1630", alpha=0x28, slide=40)
    a.box(0.2, total, sb_x, sb_y, 190, 96, 24, "F5B700", alpha=0x00, slide=40)
    a.text(0.2, total, sb_x + 95, sb_y + 48, "LEAGUE", 38, color="0B1630", an=5, slide=40, spacing=2)
    a.text(0.2, total, sb_x + 215, sb_y + 48, "HOME", 34, color="C9D4F0", an=4, slide=40, font=FONT_B)
    a.text(0.2, st, sb_x + 345, sb_y + 48, "0", 56, an=5, slide=40)
    a.text(0.2, total, sb_x + 385, sb_y + 46, "-", 44, color="8FA0CC", an=5, slide=40)
    a.text(0.2, total, sb_x + 425, sb_y + 48, "0", 56, an=5, slide=40)
    a.text(0.2, total, sb_x + 470, sb_y + 48, "AWAY", 34, color="C9D4F0", an=4, slide=40, font=FONT_B)
    # score change: home 0 -> 2 with pop + gold flash + "+2"
    a.raw(f"Dialogue: 3,{ts(st)},{ts(total)},Txt,,0,0,0,,{{\\an5\\pos({sb_x+345},{sb_y+48})\\fn{FONT}\\fs56\\1c&H{bgr('F5B700')}&"
          f"\\fscx160\\fscy160\\t(0,350,\\fscx100\\fscy100)}}2")
    a.raw(f"Dialogue: 3,{ts(st)},{ts(st+1.6)},Txt,,0,0,0,,{{\\an5\\move({sb_x+345},{sb_y+130},{sb_x+345},{sb_y+210},0,900)"
          f"\\fn{FONT}\\fs64\\1c&H{bgr('F5B700')}&\\bord3\\3c&H{bgr('0B1630')}&\\fad(80,500)}}+2")

    # title
    ts0, ts1 = T(g["title"])
    a.box(ts0, ts1, 56, 330, 760, 170, 28, "0B1630", alpha=0x30, slide=60, fin=0.3, fout=0.3)
    a.box(ts0, ts1, 56, 330, 14, 170, 7, "F5B700", alpha=0x00, slide=60, fin=0.3, fout=0.3)
    a.text(ts0, ts1, 96, 356, "KAPI IN THE LEAGUE", 66, slide=60, fin=0.3, fout=0.3)
    a.text(ts0, ts1, 98, 438, "SEASON OPENER · EPISODE 1", 36, color="F5B700", font=FONT_B, slide=60, fin=0.3, fout=0.3, spacing=3)

    # name tags
    for tg in g["tags"]:
        t0, t1 = T(tg)
        col = tg["color"]
        a.box(t0, t1, 56, 330, 640, 128, 26, "0B1630", alpha=0x30, slide=60)
        a.box(t0, t1, 56, 330, 14, 128, 7, col, alpha=0x00, slide=60)
        a.text(t0, t1, 96, 344, tg["name"], 60, slide=60)
        a.text(t0, t1, 98, 410, tg["role"], 32, color=col, font=FONT_B, slide=60, spacing=3)

    # Rico captions (uppercase, left of the Shorts button column)
    for cp in g["captions"]:
        t0, t1 = T(cp)
        a.box(t0, t1, 405, 1236, 190, 58, 29, "F5B700", alpha=0x00, fin=0.12, fout=0.12)
        a.text(t0, t1, 500, 1265, "RICO", 36, color="0B1630", an=5, fin=0.12, fout=0.12, spacing=4)
        a.text(t0, t1, 500, 1400, cp["text"].replace("|", "\\N"), cp.get("size", 84), an=5, fin=0.08, fout=0.1, bord=8,
               bordc="0B1630", shad=3, layer=4,
               extra="\\fscx90\\fscy90\\t(0,140,\\fscx100\\fscy100)")

    # end card (top part of frame so Kapi's last shrug stays visible)
    e0 = T(g["end"])
    a.box(e0, total, 0, 290, W, 400, 0, "0B1630", alpha=0x4C, fin=0.35, fout=0.0)
    a.text(e0 + 0.15, total, 500, 390, "TO BE CONTINUED...", 72, an=5, fin=0.3, fout=0.0)
    a.text(e0 + 0.35, total, 500, 490, "NEXT: BUNNY'S BIG DUNK", 46, color="F5B700", an=5, fin=0.3, fout=0.0, font=FONT_B, spacing=2)
    a.text(e0 + 0.55, total, 500, 585, "FOLLOW KAPI'S WORLD", 36, color="C9D4F0", an=5, fin=0.3, fout=0.0, font=FONT_B, spacing=4)

    ass = os.path.join(HERE, "work", "graphics.ass")
    open(ass, "w").write(a.render())

    # ---- join clips with dissolves ---------------------------------------
    inputs = []
    for p in prepped:
        inputs += ["-i", p]
    fc = []
    vlast, alast = "[0:v]", "[0:a]"
    off = 0.0
    for i in range(1, len(prepped)):
        off = starts[i]
        tr = CFG["transitions"][i - 1]
        fc.append(f"{vlast}[{i}:v]xfade=transition={tr}:duration={FADE}:offset={off:.3f}[v{i}]")
        fc.append(f"{alast}[{i}:a]acrossfade=d={FADE}[a{i}]")
        vlast, alast = f"[v{i}]", f"[a{i}]"
    # tail hold (freeze last frame) and subtitles
    n = len(prepped) - 1
    fc.append(f"{vlast}tpad=stop_mode=clone:stop_duration={tail}[vt]")
    punch = CFG["graphics"].get("punch")
    if punch:
        p0, p1 = T(punch)
        fc.append(f"[vt]scale=w='{W}*(1+0.06*between(t,{p0},{p1})*(t-{p0})/{p1-p0})':h=-2:eval=frame,crop={W}:{H}[vz]")
        vlast2 = "[vz]"
    else:
        vlast2 = "[vt]"
    fc.append(f"{vlast2}ass={ass}:fontsdir=/usr/share/fonts/opentype/inter[vout]")
    # audio: normalised later
    fc.append(f"{alast}apad=pad_dur={tail}[abase]")

    # sound effects (synth) mixed under dialogue
    sfx = CFG.get("sfx", [])
    sfx_inputs = []
    mix_labels = ["[abase]"]
    base_idx = len(prepped)
    for k, s in enumerate(sfx):
        if s["type"] == "ding":
            src = ("aevalsrc='0.5*exp(-5*t)*(sin(2*PI*1318.5*t)+0.6*sin(2*PI*1975.5*t)+0.3*sin(2*PI*2637*t))':d=1.2:s=48000")
        else:  # whoosh
            src = "anoisesrc=d=0.45:c=pink:a=0.6:r=48000"
        sfx_inputs += ["-f", "lavfi", "-i", src]
        idx = base_idx + k
        delay = int(T(s) * 1000)
        if s["type"] == "ding":
            fc.append(f"[{idx}:a]aformat=channel_layouts=stereo,volume={s.get('vol',0.6)},adelay={delay}|{delay}[s{k}]")
        else:
            fc.append(f"[{idx}:a]aformat=channel_layouts=stereo,bandpass=f=900:w=1.5,afade=t=in:d=0.2,afade=t=out:st=0.2:d=0.25,volume={s.get('vol',0.5)},adelay={delay}|{delay}[s{k}]")
        mix_labels.append(f"[s{k}]")
    fc.append("".join(mix_labels) + f"amix=inputs={len(mix_labels)}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    cmd = ["ffmpeg", "-v", "error", "-y"] + inputs + sfx_inputs + [
        "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-r", "24", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total:.3f}", OUT]
    print(" ".join(cmd)[:300], "...")
    subprocess.run(cmd, check=True)
    print("wrote", OUT, "length", round(probe(OUT), 2))


if __name__ == "__main__":
    main()
