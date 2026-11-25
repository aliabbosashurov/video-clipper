"""Where video comes from: links (through yt-dlp) and local files.

Metadata, the audio-only download for prep, the section download for render, and friendly hints
for the download errors people hit most.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
import re
from pathlib import Path

from .config import YTDLP, Quality
from .media import probe_duration
from .util import run

# common download errors -> what to do about them (shown under the original message)
ERROR_HINTS = [
    (r"sign in to confirm|not a bot|confirm your age|age.restricted|inappropriate for some users",
     "log in to the site in your browser, then retry with --cookies chrome (or safari / firefox)"),
    (r"members.only|join this channel|available to this channel's members",
     "members-only video: retry with --cookies <browser> logged in to an account that is a member"),
    (r"private video", "this video is private and can't be downloaded"),
    (r"available in your country|geo.?restrict|blocked it in your country",
     "this video is blocked in your region"),
    (r"video (?:is )?unavailable|has been removed|does not exist", "the video was removed or the link is wrong"),
    (r"unsupported url", "this site or link type isn't supported by yt-dlp"),
    (r"http error 429|too many requests", "the site is rate-limiting you: wait a while, or retry with --cookies <browser>"),
    (r"http error 403|forbidden", "access denied: re-run setup.sh (updates yt-dlp), or retry with --cookies <browser>"),
    (r"requested format is not available", "re-run setup.sh (updates yt-dlp), or try a lower --quality"),
]


def explain(msg: str) -> str:
    """Original error + a one-line hint for the errors people hit most."""
    for pat, hint in ERROR_HINTS:
        if re.search(pat, msg, re.I):
            return f"{msg}\n    Hint: {hint}"
    return msg


def cookie_args(c: str | None) -> list[str]:
    """--cookies chrome / safari / firefox (browser login) or a cookies.txt path."""
    if not c:
        return []
    return ["--cookies", c] if os.path.isfile(c) else ["--cookies-from-browser", c]


def ytdlp_json(url: str, cookies: str | None = None, extra=()) -> dict:
    r = run(YTDLP + cookie_args(cookies) + list(extra) + ["-J", url])
    if r.returncode != 0:
        raise RuntimeError(explain(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "yt-dlp failed"))
    return json.loads(r.stdout)


def local_file(src: str) -> Path | None:
    p = Path(src).expanduser()
    return p.resolve() if p.is_file() else None


def source_info(src: str, cookies: str | None, name: str | None) -> dict:
    """Metadata for a link (via yt-dlp) or a local video file. Saved as `source` in the run folder's manifest.json."""
    p = local_file(src)
    if p:
        dur = probe_duration(p)
        if not dur:
            raise RuntimeError(f"can't read {p} as a video (ffprobe found no duration)")
        vid = hashlib.md5(str(p).encode()).hexdigest()[:10]
        return {"url": str(p), "webpage_url": str(p), "path": str(p), "id": vid, "title": p.stem,
                "streamer": name or p.stem, "platform": "local", "duration": dur, "cookies": None}
    meta = ytdlp_json(src, cookies, ["--no-playlist"])
    if meta.get("live_status") == "is_live" and meta.get("extractor_key", "").lower().startswith("youtube"):
        raise RuntimeError("still live on YouTube: clip it once the replay is up (Twitch archives work while live)")
    return {"url": src, "webpage_url": meta.get("webpage_url") or src, "id": meta.get("id"),
            "title": meta.get("title"), "streamer": name or meta.get("uploader") or meta.get("channel") or "creator",
            "platform": meta.get("extractor_key"), "duration": meta.get("duration"), "cookies": cookies}


def download_audio(rd: Path, info: dict) -> Path:
    """Audio only (plus the live-chat replay on YouTube) into the run folder."""
    cookies, url = info["cookies"], info["url"]
    is_yt = "youtube" in (info["platform"] or "").lower()
    with cf.ThreadPoolExecutor(2) as ex:
        fa = ex.submit(run, YTDLP + cookie_args(cookies) + ["--no-playlist", "-f", "bestaudio/audio_only/worst",
                                                             "-o", str(rd / "audio.%(ext)s"), url])
        fc = ex.submit(run, YTDLP + cookie_args(cookies) + ["--no-playlist", "--skip-download", "--write-subs",
                                                             "--sub-langs", "live_chat", "-o", str(rd / "chat"), url]) if is_yt else None
        ra = fa.result()
        if fc:
            fc.result()
    src = next((p for p in rd.glob("audio.*") if p.suffix not in (".part", ".ytdl", ".wav")), None)
    if not src:  # Twitch highlights / edited VODs break yt-dlp's own HLS downloader: retry through ffmpeg
        for p in rd.glob("audio.*"):
            p.unlink(missing_ok=True)
        ra = run(YTDLP + cookie_args(cookies) + ["--no-playlist", "--downloader", "m3u8:ffmpeg", "-f",
                                                 "bestaudio/audio_only/worst", "-o", str(rd / "audio.%(ext)s"), url])
        src = next((p for p in rd.glob("audio.*") if p.suffix not in (".part", ".ytdl", ".wav")), None)
    if not src:
        raise RuntimeError(explain(f"audio download failed: {ra.stderr[-300:].strip()}"))
    return src


def fetch_section(info: dict, a: float, b: float, work: Path, cookies: str | None, q: Quality,
                  exact: bool = False) -> Path:
    """Only the minutes the clip needs: cut from the local file, or download that section.
    exact=True re-encodes at the cut so the picture starts right at `a` (slower, last resort)."""
    if info.get("path"):
        out = work / "src.mp4"
        r = run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}", "-i", info["path"],
                 "-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16",
                 "-c:a", "aac", "-b:a", "192k", str(out)])
        if r.returncode != 0:
            raise RuntimeError("section cut failed: " + r.stderr[-300:])
        return out
    h = q.height
    fmt = f"bv*[height<={h}][fps<=60]+ba/b[height<={h}]/bv*+ba/b" if h else "bv*[fps<=60]+ba/bv*+ba/b"
    # above 1080p YouTube mostly serves VP9/AV1, which may not fit in mp4: fall back to mkv
    for attempt in range(2):  # a dropped connection mid-download ("ffmpeg exited with code 8") is usually one-off
        r = run(YTDLP + cookie_args(cookies) + ["--no-playlist", "-f", fmt, "--download-sections", f"*{a:.1f}-{b:.1f}",
                *(["--force-keyframes-at-cuts"] if exact else []),
                "--merge-output-format", "mp4/mkv", "-o", str(work / "src.%(ext)s"), info["webpage_url"]])
        src = next((p for p in work.glob("src.*") if p.suffix in (".mp4", ".mkv", ".webm")), None)
        if src:
            break
        for p in work.glob("src.*"):
            p.unlink(missing_ok=True)
    if not src:
        raise RuntimeError(explain("section download failed: " + r.stderr[-300:].strip()))
    return src
