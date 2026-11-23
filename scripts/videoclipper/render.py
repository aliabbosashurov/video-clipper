"""render (step 4): the best picks -> vertical clips with hook, captions, cover image and post text.

Per clip: get the section (with picture from the first frame) -> layout -> caption words -> encode ->
cover + post text -> remove the clip's previous version.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import layout
from .captions import caption_frames
from .config import QUALITY, Quality
from .media import probe_video, video_start
from .picks import select
from .post import post_text
from .sources import fetch_section
from .transcribe import clip_words
from .util import hms, log, run, slug


@dataclass
class RenderOptions:
    top: int = 3                 # clips to make
    min_score: float = 7.0       # quality bar for moments (0-10)
    max_len: float = 75          # longest clip, seconds
    layout: str = "auto"         # auto / facecam / cam / full for every clip (a pick's own "layout" wins)
    quality: str = "standard"    # a config.QUALITY key
    cookies: str | None = None   # default: what prep used
    keep: bool = False           # keep downloaded sections + caption frames


def render_run(rd: Path, opts: RenderOptions) -> dict:
    """Render the best picks of a run folder; writes clips/ + summary.json and returns the summary."""
    info = json.loads((rd / "stream.json").read_text())
    if info.get("path") and not Path(info["path"]).is_file():
        raise SystemExit(f"The source file is gone: {info['path']}")
    t0 = time.time()
    picks, total = select(rd, opts.top, opts.min_score, opts.max_len)
    log(f"[{info['streamer']}] {total} possible moments -> keeping best {len(picks)} (quality: {opts.quality})")
    made = []
    for n, c in enumerate(picks, 1):
        try:
            out, mode = render_clip(rd, info, c, n, opts.cookies or info.get("cookies"), opts.keep, opts.layout,
                                    opts.quality)
            made.append({"file": str(out), "cover": str(out.with_suffix(".jpg")), "title": c.get("title"),
                         "score": c.get("score"), "layout": mode,
                         "at": hms(c["_s"]), "len": round(c["_e"] - c["_s"])})
            log(f"  clip {n}: {c.get('title')}  ({hms(c['_s'])}, {round(c['_e'] - c['_s'])}s, {mode}) -> {out.name}")
        except Exception as e:
            log(f"  clip {n} FAILED: {e}")
    tm = json.loads((rd / "timing.json").read_text()) if (rd / "timing.json").exists() else {}
    tm["render_sec"] = round(time.time() - t0)
    tm["total_sec"] = round(time.time() - tm.get("prep_started", t0))
    (rd / "timing.json").write_text(json.dumps(tm, indent=1))
    (rd / "clips").mkdir(exist_ok=True)
    summary = {"video": info["title"], "creator": info["streamer"], "length": hms(info.get("duration") or 0),
               "moments_found": total, "clips": made, "total_time": hms(tm["total_sec"])}
    (rd / "clips" / "summary.json").write_text(json.dumps(summary, indent=1))
    log(f"\n{info['streamer']}: {summary['length']} video -> {total} moments -> {len(made)} clips "
        f"(total {summary['total_time']}) -> {rd / 'clips'}")
    return summary


def render_clip(rd: Path, info: dict, c: dict, n: int, cookies: str | None, keep: bool, forced_layout: str,
                quality: str = "standard") -> tuple[Path, str]:
    """One clip. Returns (mp4 path, layout mode)."""
    work = rd / f"work_{n:02d}"
    try:
        return _render_clip(rd, info, c, n, cookies, forced_layout, quality, work)
    finally:  # downloaded sections + caption frames go even when the render fails (unless --keep)
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def _render_clip(rd: Path, info: dict, c: dict, n: int, cookies: str | None, forced_layout: str, quality: str,
                 work: Path) -> tuple[Path, str]:
    q = QUALITY[quality]
    clips = rd / "clips"
    clips.mkdir(exist_ok=True)
    work.mkdir(exist_ok=True)
    src, a = _section(info, c, n, work, cookies, q)
    W, H, sdur = probe_video(src)
    ss = min(c["_s"] - a, max(0, sdur - 5))
    v0 = video_start(src)
    if v0 > ss + 0.05:  # still no picture at the start: begin at the first real frame instead of on black
        log(f"  clip {n}: starting {v0 - ss:.1f}s later than picked, where the picture begins")
        ss = v0
    dur = min(c["_e"] - a - ss, sdur - ss)  # ends where the moment ends, even if the start moved

    fc = layout.choose(layout.detect(src, W, H), c.get("layout") or forced_layout, n)
    words = clip_words(src, ss, dur, work, info.get("lang") or "en")
    frame = layout.plan(fc, W, H, q)
    lst = caption_frames(words, c.get("hook") or c.get("title"), frame.seam, frame.cap_y, dur, work / "cap")
    out = clips / f"clip_{n:02d}_{slug(c.get('title') or c.get('hook'), 40, whole_words=True)}.mp4"
    _encode(src, ss, dur, frame.filter, lst, q, out)
    # cover image for Shorts / TikTok / Reels (hook visible, first caption on screen); also used to check framing
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{min(1.5, dur / 3):.2f}", "-i", str(out),
         "-frames:v", "1", "-q:v", "2", str(out.with_suffix(".jpg"))])
    out.with_suffix(".txt").write_text(post_text(c, info, fc["mode"], quality, W, H))
    # a re-render with a new title writes a new file name: remove the previous version of this clip number
    for old in clips.glob(f"clip_{n:02d}_*"):
        if old.stem != out.stem and old.suffix in (".mp4", ".jpg", ".txt"):
            old.unlink(missing_ok=True)
    return out, fc["mode"]


def _section(info: dict, c: dict, n: int, work: Path, cookies: str | None, q: Quality) -> tuple[Path, float]:
    """The source minutes for this clip and where they start (a, in video seconds). Reuses a kept one."""
    a = max(0, c["_s"] - 10)  # lead-in, so the section's first keyframe lands before the moment
    src = next((p for p in work.glob("src.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
    if src is not None:
        return src, a
    b = c["_e"] + 1
    # a section's picture starts at its first keyframe: if that's after the moment, the clip would open
    # on seconds of black. Retry with a longer lead-in, then with an exact (re-encoded) cut.
    for lead, exact in ((10, False), (30, False), (10, True)):
        a = max(0, c["_s"] - lead)
        for p in work.glob("src.*"):
            p.unlink(missing_ok=True)
        src = fetch_section(info, a, b, work, cookies, q, exact)
        if info.get("path") or video_start(src) <= c["_s"] - a + 0.05:
            break
        log(f"  clip {n}: no picture until {video_start(src) - (c['_s'] - a):.1f}s into the clip, retrying")
    return src, a


def _encode(src: Path, ss: float, dur: float, vf: str, captions_list: Path, q: Quality, out: Path) -> None:
    """Frame + captions + loudness-normalised audio -> the final mp4."""
    r = run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
             "-f", "concat", "-safe", "0", "-i", str(captions_list), "-filter_complex",
             vf + ";[1:v]format=rgba[ov];[base][ov]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[v];"
             "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]",
             "-map", "[v]", "-map", "[aout]", "-c:v", "libx264", "-preset", q.preset, "-crf", str(q.crf),
             "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    if r.returncode != 0:
        out.unlink(missing_ok=True)  # don't leave a broken, half-written mp4 that looks like a clip
        raise RuntimeError("render failed: " + r.stderr[-500:])
