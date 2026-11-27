"""Text burned into the clip: the hook box and word-by-word captions, as a PNG timeline for ffmpeg."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
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
HOOK_SIZES = (50, 46, 42, 38, 34, 30)  # the hook starts at 50 px and shrinks until it fits in 3 lines
HOOK_LINES = 3
CAP_SIZE = 84
CAP_STROKE = 7


@dataclass
class Overlays:
    """What render lays over the framed video: a still hook box and a timeline of small caption strips."""
    strips: Path         # ffconcat list of caption strip PNGs (1080 wide, covering the whole clip)
    strip_y: int         # y where the strips go
    hook: Path | None    # one still PNG (1080 wide, as tall as the box), None without a hook
    hook_y: int


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


def fit_hook(draw, text: str, maxw: float) -> tuple[object, list[str]]:
    """The biggest hook font (HOOK_SIZES) whose text fits in HOOK_LINES lines, each within maxw. A hook that
    still doesn't fit at the smallest size is cut at the last whole word that does, with an ellipsis."""
    for size in HOOK_SIZES:
        fnt = font(size)
        lines = wrap(draw, text, fnt, maxw)
        if len(lines) <= HOOK_LINES and all(draw.textlength(l, font=fnt) <= maxw for l in lines):
            return fnt, lines
    fnt = font(HOOK_SIZES[-1])
    words = text.split()
    while words:
        lines = wrap(draw, " ".join(words) + "…", fnt, maxw)
        if len(lines) <= HOOK_LINES and all(draw.textlength(l, font=fnt) <= maxw for l in lines):
            return fnt, lines
        words.pop()
    return fnt, [text[:1] + "…"]


def caption_frames(words: list[dict], hook: str | None, seam_y: int, cap_y: int, dur: float, outdir: Path) -> Overlays:
    """Build the hook box (one still PNG) and one small transparent strip per caption state, plus an ffconcat
    list for the strips. The strips are 1080 wide and only as tall as the caption line, not full frames."""
    from PIL import Image, ImageDraw
    outdir.mkdir(exist_ok=True)
    cf_ = font(CAP_SIZE)
    cap_y = min(cap_y, SAFE_MAX_Y)
    # the band the caption line can occupy (tallest glyphs + outline), from the biggest caption font
    l_, t_, r_, b_ = cf_.getbbox("ÁÇgjpqy|", anchor="lm", stroke_width=CAP_STROKE)
    half = int(max(-t_, b_)) + 4
    y0 = max(0, cap_y - half) // 2 * 2
    y1 = min(1920, cap_y + half + 1) // 2 * 2 + 2
    y1 = min(y1, 1920)
    strip_h = y1 - y0

    def strip():
        return Image.new("RGBA", (1080, strip_h), (0, 0, 0, 0))

    hook_png, hook_y = None, 0
    if hook:
        probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        hf, lines = fit_hook(probe, hook.upper(), SAFE_TEXT_W - 60)
        lh = round(hf.size * 1.24)
        bh = lh * len(lines) + 34
        top = seam_y - bh // 2
        bw = max(probe.textlength(l, font=hf) for l in lines) + 60
        hook_y = max(0, top) // 2 * 2
        hook_h = min(1920, top + bh + 2) - hook_y
        hook_h += hook_h % 2
        im = Image.new("RGBA", (1080, hook_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([540 - bw / 2, top - hook_y, 540 + bw / 2, top - hook_y + bh], 18, fill=(255, 255, 255, 255))
        for i, l in enumerate(lines):
            d.text((540, top - hook_y + 17 + i * lh + lh / 2), l, font=hf, fill=(0, 0, 0), anchor="mm")
        hook_png = outdir / "hook.png"
        im.save(hook_png)

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
    strip().save(blank)
    for t0, t1, g, ai in states:
        if t0 > t + 0.02:
            timeline.append((blank, t0 - t))
        im = strip()
        d = ImageDraw.Draw(im)
        text = [w["t"].upper() for w in g]
        widths = [d.textlength(x, font=cf_) for x in text]
        space = d.textlength(" ", font=cf_)
        total = sum(widths) + space * (len(text) - 1)
        scale_font = cf_
        if total > SAFE_TEXT_W:
            scale_font = font(int(CAP_SIZE * SAFE_TEXT_W / total))
            widths = [d.textlength(x, font=scale_font) for x in text]
            space = d.textlength(" ", font=scale_font)
            total = sum(widths) + space * (len(text) - 1)
        x = 540 - total / 2
        for j, (word, wd) in enumerate(zip(text, widths)):
            d.text((x, cap_y - y0), word, font=scale_font, anchor="lm",
                   fill=(255, 221, 0) if j == ai else (255, 255, 255), stroke_width=CAP_STROKE, stroke_fill=(0, 0, 0))
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
    return Overlays(lst, y0, hook_png, hook_y)
