"""The picker's moments (picks/chunk_NN.json): reading them, reporting problems, and choosing what to render."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from . import manifest
from .util import hms, log, parse_ts

REQUIRED = ("start", "end", "score")
SLACK_SEC = 2  # a pick may start this much before its chunk (timestamps are whole seconds)


def pick_files(rd: Path) -> Iterator[tuple[Path, object, Exception | None]]:
    """(file, parsed JSON or None, error or None) for every picks/chunk_NN.json, in order."""
    for p in sorted((rd / "picks").glob("chunk_*.json")):
        try:
            yield p, json.loads(p.read_text()), None
        except Exception as e:
            yield p, None, e


def chunk_number(p: Path) -> int:
    return int(re.search(r"\d+", p.stem).group())


def outside(start: float, chunk: dict) -> str | None:
    """Why a moment starting at `start` doesn't belong to `chunk`, or None when it does."""
    if chunk["start"] - SLACK_SEC <= start < chunk["end"]:
        return None
    return (f"starts at {hms(start)}, outside chunk {chunk['n']} ({hms(chunk['start'])} to {hms(chunk['end'])}): "
            f"a moment belongs to the chunk where it starts")


def problems(rd: Path) -> tuple[int, list[dict]]:
    """(number of entries in readable files, list of problems) for `status`."""
    chunks = {c["n"]: c for c in manifest.require(rd)["chunks"]}
    cands, bad = 0, []
    for p, entries, err in pick_files(rd):
        n = chunk_number(p)
        if n not in chunks:
            bad.append({"file": p.name, "error": f"there is no chunk {n} (this run has {len(chunks)})"})
            continue
        if err is None and not isinstance(entries, list):
            err = ValueError("must be a JSON array ([] when nothing qualifies)")
        if err is not None:  # report it instead of crashing, so the file can be fixed
            bad.append({"file": p.name, "error": str(err)})
            continue
        cands += len(entries)
        for i, c in enumerate(entries):
            missing = [k for k in REQUIRED if not isinstance(c, dict) or k not in c]
            if missing:
                bad.append({"file": p.name, "entry": i, "error": f"missing {', '.join(missing)}"})
                continue
            try:
                why = outside(parse_ts(c["start"]), chunks[n])
            except (ValueError, TypeError) as e:
                why = f"bad start: {e}"
            if why:
                bad.append({"file": p.name, "entry": i, "error": why})
    return cands, bad


def load_moments(rd: Path) -> list[dict]:
    """Every usable moment, with `_s` / `_e` in seconds and `_id` / `_chunk` saying where it came from
    (c07-2 = 2nd entry of picks/chunk_07.json). Broken entries are skipped one by one (and logged)."""
    chunks = {c["n"]: c for c in manifest.require(rd)["chunks"]}
    cands = []
    for p, entries, err in pick_files(rd):
        if err is not None:
            log(f"  bad pick file {p.name}: {err}")
            continue
        chunk = chunk_number(p)
        if chunk not in chunks:
            log(f"  bad pick file {p.name}: there is no chunk {chunk}")
            continue
        for i, c in enumerate(entries if isinstance(entries, list) else []):
            try:  # one broken entry must not take the other moments in the file down with it
                c["_s"], c["_e"] = parse_ts(c["start"]), parse_ts(c["end"])
                c["_id"], c["_chunk"] = f"c{chunk:02d}-{i + 1}", chunk
                float(c.get("score", 0))
            except Exception as e:
                log(f"  skipped {p.name} entry {i + 1}: {'missing ' + str(e) if isinstance(e, KeyError) else e}")
                continue
            if c["_e"] <= c["_s"]:
                log(f"  skipped {p.name} entry {i + 1}: end is not after start")
                continue
            if why := outside(c["_s"], chunks[chunk]):
                log(f"  skipped {p.name} entry {i + 1}: {why}")
                continue
            cands.append(c)
    return cands


def select(rd: Path, top: int, min_score: float, max_len: float) -> tuple[list[dict], int]:
    """The best `top` moments, snapped to sentence edges, without overlaps. Returns (chosen, all moments)."""
    cands = load_moments(rd)
    segs = json.loads((rd / "transcript.json").read_text())
    total = len(cands)
    ok = []
    for c in sorted(cands, key=lambda c: -float(c.get("score", 0))):
        if float(c.get("score", 0)) < min_score:
            continue
        # snap to sentence boundaries so clips don't start/end mid-word
        st = max([s["start"] for s in segs if s["start"] <= c["_s"] + 0.5] or [c["_s"]])
        en = min([s["end"] for s in segs if s["end"] >= c["_e"] - 0.5] or [c["_e"]])
        if en - st > max_len:
            en = st + max_len
        if en - st < 12:
            continue
        if any(st < o["_e"] and en > o["_s"] for o in ok):  # same or overlapping moment
            continue
        c["_s"], c["_e"] = max(0, st - 0.25), en + 0.4
        ok.append(c)
        if len(ok) >= top:
            break
    return ok, total
