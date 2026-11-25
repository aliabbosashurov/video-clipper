"""status: how far a run folder is (chunks still to pick, broken or outdated picks, clips made)."""
from __future__ import annotations

from pathlib import Path

from . import manifest
from .chunks import name, sha
from .picks import problems


def run_status(rd: Path) -> dict:
    m = manifest.require(rd)
    picked = {p.stem for p in (rd / "picks").glob("chunk_*.json")}
    cands, bad = problems(rd)
    changed, stale = [], []
    for c in m["chunks"]:
        md, pk = rd / "chunks" / f"{name(c['n'])}.md", rd / "picks" / f"{name(c['n'])}.json"
        if not md.exists() or sha(md.read_bytes()) != c["sha"]:
            changed.append(md.name)  # edited or replaced after prep: the picks may not match the text any more
        elif pk.exists() and pk.stat().st_mtime < md.stat().st_mtime:
            stale.append(pk.name)    # picked before this chunk was written (prep was run again)
    return {"run": str(rd), "prepped_with": m["prep"].get("whisper_model"), "chunks": len(m["chunks"]),
            "picked_chunks": len(picked), "candidates": cands,
            "chunks_left": [f"{name(c['n'])}.md" for c in m["chunks"] if name(c["n"]) not in picked],
            "bad_picks": bad, "stale_picks": stale, "changed_chunks": changed,
            "clips": sorted(x.name for x in (rd / "clips").glob("*.mp4")) if (rd / "clips").exists() else []}
