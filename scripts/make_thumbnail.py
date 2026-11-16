#!/usr/bin/env python3
"""Cut one frame out of a finished Short and put the punchline on it as a thumbnail.

    python3 scripts/make_thumbnail.py video.mp4 21.2 plan/short1/thumbnail.jpg "ZERO STEPS." "TWO POINTS."

Needs ffmpeg and Pillow. Output: 1080x1920 JPEG under 2 MB (YouTube's limit).
The text sits on the court at the bottom, clear of the characters' faces.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = ["/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
WHITE, YELLOW, INK = (255, 255, 255), (255, 196, 0), (12, 14, 30)


def font(size):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def main(video, t, out, line1, line2):
    with tempfile.TemporaryDirectory() as d:
        png = Path(d) / "f.png"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(t), "-i", video,
                        "-frames:v", "1", str(png)], check=True)
        im = Image.open(png).convert("RGB")
    im = im.resize((1080, 1920), Image.LANCZOS)

    # soft dark gradient under the text so it reads on any court colour
    grad = Image.new("L", (1, 520))
    for y in range(520):
        grad.putpixel((0, y), int(170 * (y / 519) ** 1.6))
    shade = Image.new("RGB", (1080, 520), INK)
    im.paste(shade, (0, 1920 - 520), grad.resize((1080, 520)))

    d = ImageDraw.Draw(im)
    for text, colour, y in ((line1, WHITE, 1560), (line2, YELLOW, 1710)):
        f = font(128)
        while d.textlength(text, font=f) > 980:
            f = font(f.size - 4)
        w = d.textlength(text, font=f)
        d.text(((1080 - w) / 2, y), text, font=f, fill=colour, stroke_width=10, stroke_fill=INK)
    im.save(out, "JPEG", quality=90, optimize=True)
    print(f"{out}: {Path(out).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    main(*sys.argv[1:])
