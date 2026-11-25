"""The transcript cut into pieces for the picker (chunks/chunk_NN.md), with LOUD / CHAT / LOW-CONF markers inline.

A moment belongs to the chunk where it STARTS. Each chunk therefore ends with a lookahead (the first minutes of
the next chunk, context only) so the picker can see how a moment that starts near the end finishes.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from .util import hms

CHUNK_FORMAT = 1    # bump when the chunk text or the manifest's chunk index changes shape
LOOKAHEAD_SEC = 90  # longer than the default longest clip (75 s), so a moment that starts in a chunk can be read to its end
LOW_CONF = 0.5      # lines Whisper was less sure of than this (music, singing, crosstalk) get a LOW-CONF marker


@dataclass
class Chunk:
    n: int            # 1-based
    lo: float         # first second it owns
    end: float        # last second it owns (the video's end for the last chunk)
    own: list[dict]   # transcript lines that START inside it
    ahead: list[dict]  # lines that start in the lookahead after it (empty for the last chunk)


def name(n: int) -> str:
    return f"chunk_{n:02d}"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def plan_chunks(segs: list[dict], dur: float, chunk_sec: int) -> list[Chunk]:
    """Cut the transcript into chunks of `chunk_sec`. Every line is owned by exactly one chunk."""
    n = max(1, math.ceil(dur / chunk_sec))
    chunks = []
    for i in range(n):
        lo, hi = i * chunk_sec, (i + 1) * chunk_sec
        last = i == n - 1
        owns_to = math.inf if last else hi  # the last chunk also takes lines that start after the stated duration
        chunks.append(Chunk(
            n=i + 1, lo=lo, end=min(hi, dur),
            own=[s for s in segs if lo <= s["start"] < owns_to],
            ahead=[] if last else [s for s in segs if hi <= s["start"] < hi + LOOKAHEAD_SEC]))
    return chunks


def _tags(s: dict, loud: list[dict], chat: list[dict]) -> list[str]:
    tags = []
    if s.get("conf") is not None and s["conf"] < LOW_CONF:
        tags.append("LOW-CONF")
    for e in loud:
        if e["start"] <= s["end"] and e["end"] + 1 >= s["start"]:
            tags.append(f"LOUD(+{e['db']:.0f}dB)")
            break
    for e in chat:  # chat reacts a few seconds late
        if e["start"] - 15 <= s["end"] and e["end"] >= s["start"]:
            tags.append(f"CHAT x{e['x']}")
            break
    return tags


def chunk_text(c: Chunk, total: int, info: dict, loud: list[dict], chat: list[dict], context: str | None) -> str:
    def line(s):
        tags = _tags(s, loud, chat)
        return f"[{hms(s['start'])}] {s['text']}" + (f"   <<{' '.join(tags)}>>" if tags else "")

    lines = [f"# {info['streamer']}: {info['title']}", f"Chunk {c.n}/{total}  ({hms(c.lo)} to {hms(c.end)})"]
    if context:
        lines.append(f"Context: {context}")
    lines += ["Markers: LOUD(+dB over normal) = speaker got loud. CHAT xN = chat moving N times faster than normal. "
              "LOW-CONF = the transcription of this line is unreliable (music, singing, crosstalk).", ""]
    lines += [line(s) for s in c.own]
    if c.ahead:
        lines += ["(end of this chunk. The lines below are the start of the next chunk, for context only: "
                  "a moment that started above may run into them, but never start a moment below)"]
        lines += [line(s) for s in c.ahead]
    return "\n".join(lines) + "\n"


def write_chunks(rd: Path, info: dict, segs: list[dict], loud: list[dict], chat: list[dict],
                 chunk_sec: int, context: str | None = None) -> list[dict]:
    """Write chunks/chunk_NN.md into the run folder. Returns the chunk index for the manifest."""
    dur = info.get("duration") or (segs[-1]["end"] if segs else 0)
    chunks = plan_chunks(segs, dur, chunk_sec)
    index = []
    for c in chunks:
        data = chunk_text(c, len(chunks), info, loud, chat, context).encode("utf-8")
        (rd / "chunks" / f"{name(c.n)}.md").write_bytes(data)
        index.append({"n": c.n, "start": round(c.lo), "end": math.ceil(c.end), "lines": len(c.own),
                      "words": sum(len(s["text"].split()) for s in c.own),
                      "loud": sum(c.lo <= e["start"] < c.end for e in loud),
                      "chat": sum(c.lo <= e["start"] < c.end for e in chat),
                      "low_conf_lines": sum(1 for s in c.own if s.get("conf") is not None and s["conf"] < LOW_CONF),
                      "sha": sha(data)})
    return index
