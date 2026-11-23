"""The transcript cut into pieces for the picker (chunks/chunk_NN.md), with LOUD / CHAT markers inline."""
from __future__ import annotations

import math
from pathlib import Path

from .util import hms

OVERLAP_SEC = 60  # each chunk repeats the end of the previous one, so a moment on the boundary isn't cut in half


def write_chunks(rd: Path, info: dict, segs: list[dict], loud: list[dict], chat: list[dict],
                 chunk_sec: int, context: str | None = None) -> int:
    """Write chunks/chunk_NN.md into the run folder. Returns the number of chunks."""
    who = info["streamer"]
    dur = info.get("duration") or (segs[-1]["end"] if segs else 0)
    n = max(1, math.ceil(dur / chunk_sec))

    def line(s):
        tags = []
        for e in loud:
            if e["start"] <= s["end"] and e["end"] + 1 >= s["start"]:
                tags.append(f"LOUD(+{e['db']:.0f}dB)")
                break
        for e in chat:  # chat reacts a few seconds late
            if e["start"] - 15 <= s["end"] and e["end"] >= s["start"]:
                tags.append(f"CHAT x{e['x']}")
                break
        return f"[{hms(s['start'])}] {s['text']}" + (f"   <<{' '.join(tags)}>>" if tags else "")

    for ci in range(n):
        lo, hi = ci * chunk_sec, (ci + 1) * chunk_sec
        lines = [f"# {who}: {info['title']}", f"Chunk {ci + 1}/{n}  ({hms(lo)} to {hms(hi)})"]
        if context:
            lines.append(f"Context: {context}")
        lines += ["Markers: LOUD(+dB over normal) = speaker got loud. CHAT xN = chat moving N times faster than normal.", ""]
        prev = [s for s in segs if lo - OVERLAP_SEC <= s["start"] and s["end"] <= lo] if ci else []
        if prev:
            lines += ["(end of the previous chunk, for context. Use it only for a moment that continues into this chunk)"]
            lines += [line(s) for s in prev] + ["(this chunk starts here)"]
        lines += [line(s) for s in segs if not (s["end"] <= lo or s["start"] >= hi)]
        (rd / "chunks" / f"chunk_{ci + 1:02d}.md").write_text("\n".join(lines) + "\n")
    return n
