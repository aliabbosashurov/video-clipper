"""Text burned into the clip: the hook box and word-by-word captions, as a PNG timeline for ffmpeg."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .config import CFG

FONTS = [os.environ.get("VIDEO_CLIPPER_FONT"), CFG.get("font"),
         "/System/Library/Fonts/Supplemental/Arial Black.ttf", "/System/Library/Fonts/Supplemental/Impact.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]

# TikTok / Reels / Shorts draw their own UI over the video: description + music along the bottom and the
# like / comment / share buttons down the right side. Keep text inside this box (1080x1920 frame).
SAFE_MAX_Y = 1400   # caption line centre stays above the bottom description area
SAFE_TEXT_W = 840   # 120..960: clear of the button column on the right
HOLD_MAX = 0.6      # a word stays lit at most this long, so a pause shows no caption instead of a frozen word


def font(size: int):
    from PIL import ImageFont
    for f in FONTS:
        if f and Path(f).expanduser().exists():
            try:
                return ImageFont.truetype(str(Path(f).expanduser()), size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)  # Pillow >= 10.1: scalable built-in font
    except TypeError:
        return ImageFont.load_default()


def wrap(draw, text: str, fnt, maxw: float) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=fnt) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def caption_frames(words: list[dict], hook: str | None, seam_y: int, cap_y: int, dur: float, outdir: Path) -> Path:
    """Build one transparent 1080x1920 PNG per caption state + an ffconcat list. Returns the list file."""
    from PIL import Image, ImageDraw
    outdir.mkdir(exist_ok=True)
    hf, cf_ = font(50), font(84)
    cap_y = min(cap_y, SAFE_MAX_Y)

    def base():
        im = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if hook:
            lines = wrap(d, hook.upper(), hf, SAFE_TEXT_W - 60)[:3]
            lh = 62
            bh = lh * len(lines) + 34
            top = seam_y - bh // 2
            bw = max(d.textlength(l, font=hf) for l in lines) + 60
            d.rounded_rectangle([540 - bw / 2, top, 540 + bw / 2, top + bh], 18, fill=(255, 255, 255, 255))
            for i, l in enumerate(lines):
                d.text((540, top + 17 + i * lh + lh / 2), l, font=hf, fill=(0, 0, 0), anchor="mm")
        return im

    # group words into 1-3 word chunks
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= 3 or w["s"] - cur[-1]["e"] > 0.45 or re.search(r"[.?!,]$", cur[-1]["t"])):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)

    states = []  # (t0, t1, group, active_idx)
    for g in groups:
        for i, w in enumerate(g):
            t1 = min(g[i + 1]["s"] if i + 1 < len(g) else w["e"], w["s"] + HOLD_MAX)
            states.append((w["s"], max(t1, w["s"] + 0.08), g, i))
    timeline, t, k = [], 0.0, 0
    blank = outdir / "blank.png"
    base().save(blank)
    for t0, t1, g, ai in states:
        if t0 > t + 0.02:
            timeline.append((blank, t0 - t))
        im = base()
        d = ImageDraw.Draw(im)
        text = [w["t"].upper() for w in g]
        widths = [d.textlength(x, font=cf_) for x in text]
        space = d.textlength(" ", font=cf_)
        total = sum(widths) + space * (len(text) - 1)
        scale_font = cf_
        if total > SAFE_TEXT_W:
            scale_font = font(int(84 * SAFE_TEXT_W / total))
            widths = [d.textlength(x, font=scale_font) for x in text]
            space = d.textlength(" ", font=scale_font)
            total = sum(widths) + space * (len(text) - 1)
        x = 540 - total / 2
        for j, (word, wd) in enumerate(zip(text, widths)):
            d.text((x, cap_y), word, font=scale_font, anchor="lm",
                   fill=(255, 221, 0) if j == ai else (255, 255, 255), stroke_width=7, stroke_fill=(0, 0, 0))
            x += wd + space
        p = outdir / f"c{k:04d}.png"
        im.save(p)
        k += 1
        start = max(t, t0)
        timeline.append((p, max(0.04, t1 - start)))
        t = start + max(0.04, t1 - start)
    if t < dur:
        timeline.append((blank, dur - t))
    lst = outdir / "list.ffconcat"
    body = ["ffconcat version 1.0"]
    for p, d_ in timeline:
        body += [f"file '{p.name}'", f"duration {d_:.3f}"]
    body.append(f"file '{timeline[-1][0].name}'")
    lst.write_text("\n".join(body) + "\n")
    return lst
