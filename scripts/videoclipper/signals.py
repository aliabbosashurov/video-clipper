"""Hints for the picker that don't come from the words: the speaker getting loud, and live chat speeding up."""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from .util import run


def loud_moments(wav: Path) -> tuple[list[dict], list[float]]:
    """Per-second RMS, flag seconds well above the local baseline (yelling / laughing / losing it)."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af",
             "asetnsamples=n=16000,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
             "-f", "null", "-"])
    vals = []
    for m in re.finditer(r"RMS_level=(-?[\d.]+|-inf)", r.stdout):
        v = m.group(1)
        vals.append(-90.0 if v == "-inf" else float(v))
    events = []
    if not vals:
        return events, vals
    W = 90
    for i, v in enumerate(vals):
        if v < -32:
            continue
        lo, hi = max(0, i - W), min(len(vals), i + W)
        base = statistics.median(vals[lo:hi])
        if v - base >= 9:
            events.append((i, round(v - base, 1)))
    merged = []
    for t, d in events:
        if merged and t - merged[-1]["end"] <= 2:
            merged[-1]["end"] = t
            merged[-1]["db"] = max(merged[-1]["db"], d)
        else:
            merged.append({"start": t, "end": t, "db": d})
    return merged, vals


def chat_spikes(chat_file: Path | None) -> list[dict]:
    """YouTube replay chat: messages per 10 s vs the local baseline."""
    if not chat_file or not Path(chat_file).exists():
        return []
    times = []
    with open(chat_file) as f:
        for line in f:
            try:
                ms = json.loads(line)["replayChatItemAction"]["videoOffsetTimeMsec"]
                times.append(int(ms) / 1000)
            except Exception:
                pass
    if len(times) < 50:
        return []
    nb = int(max(times) // 10) + 1
    bins = [0] * nb
    for t in times:
        if t >= 0:
            bins[int(t // 10)] += 1
    out = []
    for i, c in enumerate(bins):
        lo, hi = max(0, i - 30), min(nb, i + 30)
        base = max(1.0, statistics.median(bins[lo:hi]))
        if c >= 8 and c / base >= 2.5:
            out.append({"start": i * 10, "end": i * 10 + 10, "x": round(c / base, 1), "msgs": c})
    return out
