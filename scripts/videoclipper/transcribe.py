"""Speech to text with whisper.cpp: the full transcript for prep, and word timings for the captions."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import CFG
from .util import run

# Whisper writes these for silence / music. Tags that describe a reaction ([laughs], (applause)) are kept:
# they help the picking.
JUNK_LINE = re.compile(r"^\s*(?:[\[(](?!.*(?:laugh|applause|cheer|scream|gasp|clap))[^\])]*[\])]|[♪♫\s.,!?-]+)\s*$",
                       re.I)


def whisper_model(lang: str) -> str:
    en = os.environ.get("VIDEO_CLIPPER_WHISPER_MODEL") or CFG.get("whisper_model")
    multi = CFG.get("whisper_model_multi")
    if lang == "en" and (en or multi):
        return en or multi
    if lang != "en" and multi:
        return multi
    if lang != "en" and en and ".en." not in Path(en).name:
        return en
    if not (en or multi):
        raise RuntimeError("no Whisper model configured: run bash scripts/setup.sh")
    raise RuntimeError(f"language '{lang}' needs a multilingual Whisper model: run bash scripts/setup.sh --multilingual")


def transcribe(wav: Path, out_base: Path, lang: str = "en", words: bool = False) -> list[dict]:
    """[{start, end, text}] in seconds. words=True gives one entry per word (for captions)."""
    cmd = ["whisper-cli", "-m", whisper_model(lang), "-f", str(wav), "-l", lang, "-np", "-mc", "0",
           "-oj", "-of", str(out_base)]
    if words:
        cmd += ["-ml", "1", "-sow", "-ojf"]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError("whisper failed: " + r.stderr[-400:])
    data = json.loads(Path(f"{out_base}.json").read_text())
    segs = []
    for s in data.get("transcription", []):
        txt = s.get("text", "").strip()
        if txt:
            segs.append({"start": s["offsets"]["from"] / 1000, "end": s["offsets"]["to"] / 1000, "text": txt})
    return segs


def clean_segments(segs: list[dict]) -> list[dict]:
    """Drop silence / music markers and merge a line that just repeats the previous one (a Whisper glitch)."""
    out = []
    for s in segs:
        if JUNK_LINE.match(s["text"]):
            continue
        key = re.sub(r"[^\w]", "", s["text"].lower())
        if out and key and key == re.sub(r"[^\w]", "", out[-1]["text"].lower()):
            out[-1]["end"] = s["end"]
            continue
        out.append(s)
    return out


def clip_words(src: Path, ss: float, dur: float, work: Path, lang: str) -> list[dict]:
    """Word timings [{t, s, e}] for the clip that starts `ss` seconds into `src`."""
    wav = work / "w.wav"
    # -ss after -i: decode from the start and cut at the exact time. A seek before -i jumps to a video
    # keyframe, and when the section's first keyframe is late the audio (and so every caption) starts late.
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ss", f"{ss:.2f}", "-t", f"{dur:.2f}",
         "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    segs = transcribe(wav, work / "words", lang, words=True)
    words = []
    for s in segs:
        t = s["text"].strip()
        if not t or re.fullmatch(r"\[.*\]|\(.*\)", t):
            continue
        if re.fullmatch(r"[^\w]+", t) and words:
            words[-1]["t"] += t
            continue
        words.append({"t": t, "s": s["start"], "e": s["end"]})
    wav.unlink(missing_ok=True)
    return words
