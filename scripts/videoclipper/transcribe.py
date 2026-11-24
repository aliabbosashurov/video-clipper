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


# DTW (token times aligned to the audio) beats whisper's default word times, which pile words up and stretch them
# over silence. It marks a word ~0.2 s after the voice starts, so captions are shifted earlier by DTW_LEAD.
DTW_PRESETS = {"tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en",
               "large.v1", "large.v2", "large.v3", "large.v3.turbo"}
DTW_LEAD = 0.15
WORD_MAX = 0.5  # DTW gives only a start per word; assume it ends by then unless the next word comes sooner


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


def _whisper_json(wav: Path, out_base: Path, lang: str, extra: list[str]) -> dict:
    cmd = ["whisper-cli", "-m", whisper_model(lang), "-f", str(wav), "-l", lang, "-np", "-mc", "0",
           "-oj", "-of", str(out_base), *extra]
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError("whisper failed: " + r.stderr[-400:])
    return json.loads(Path(f"{out_base}.json").read_text())


def transcribe(wav: Path, out_base: Path, lang: str = "en") -> list[dict]:
    """[{start, end, text}] in seconds."""
    data = _whisper_json(wav, out_base, lang, [])
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


def dtw_preset(model: str) -> str | None:
    """whisper.cpp's DTW alignment needs the model family by name (ggml-medium.en.bin -> medium.en)."""
    name = Path(model).name.removeprefix("ggml-").removesuffix(".bin")
    if name.startswith("large"):
        name = name.replace("-", ".")
    return name if name in DTW_PRESETS else None


def _tidy(raw: list[dict]) -> list[dict]:
    """Drop [tags] / (tags) and glue punctuation-only entries onto the word before them."""
    words = []
    for w in raw:
        t = w["t"].strip()
        if not t or re.fullmatch(r"\[.*\]|\(.*\)", t):
            continue
        if re.fullmatch(r"[^\w]+", t) and words:
            words[-1]["t"] += t
            continue
        words.append({**w, "t": t})
    return words


def _dtw_words(data: dict) -> list[dict] | None:
    """Words from the DTW token times, or None if whisper-cli didn't produce them."""
    raw = []
    for seg in data.get("transcription", []):
        fresh = True
        for tok in seg.get("tokens", []):
            text = tok["text"]
            if text.startswith("[_") or not text.strip():
                continue
            if tok.get("t_dtw", -1) < 0:
                return None
            if raw and not fresh and not text.startswith(" "):
                raw[-1]["t"] += text
            else:
                raw.append({"t": text, "s": max(0.0, tok["t_dtw"] / 100 - DTW_LEAD)})
            fresh = False
    for prev, w in zip(raw, raw[1:]):
        w["s"] = max(w["s"], prev["s"])
    words = _tidy(raw)
    for i, w in enumerate(words):
        nxt = words[i + 1]["s"] if i + 1 < len(words) else float("inf")
        w["e"] = min(nxt, w["s"] + WORD_MAX)
    return words


def _split_words(data: dict) -> list[dict]:
    """Fallback: whisper's own one-word-per-segment timings (rough: it stretches words over silence)."""
    raw = [{"t": s["text"], "s": s["offsets"]["from"] / 1000, "e": s["offsets"]["to"] / 1000}
           for s in data.get("transcription", [])]
    return _tidy(raw)


def clip_words(src: Path, ss: float, dur: float, work: Path, lang: str) -> list[dict]:
    """Word timings [{t, s, e}] for the clip that starts `ss` seconds into `src`."""
    wav = work / "w.wav"
    # -ss after -i: decode from the start and cut at the exact time. A seek before -i jumps to a video
    # keyframe, and when the section's first keyframe is late the audio (and so every caption) starts late.
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ss", f"{ss:.2f}", "-t", f"{dur:.2f}",
         "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    out = work / "words"
    words = None
    preset = dtw_preset(whisper_model(lang))
    if preset:
        try:  # DTW needs flash attention off
            words = _dtw_words(_whisper_json(wav, out, lang, ["-ojf", "-dtw", preset, "-nfa"]))
        except RuntimeError:
            words = None
    if words is None:
        words = _split_words(_whisper_json(wav, out, lang, ["-ml", "1", "-sow"]))
    wav.unlink(missing_ok=True)
    return words
