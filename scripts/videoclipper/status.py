"""status: how far a run folder is (chunks still to pick, broken picks, clips made)."""
from __future__ import annotations

from pathlib import Path

from .picks import problems


def run_status(rd: Path) -> dict:
    chunks = sorted((rd / "chunks").glob("chunk_*.md"))
    picked = {p.stem for p in (rd / "picks").glob("chunk_*.json")}
    cands, bad = problems(rd)
    return {"run": str(rd), "chunks": len(chunks), "picked_chunks": len(picked), "candidates": cands,
            "chunks_left": [c.name for c in chunks if c.stem not in picked], "bad_picks": bad,
            "clips": sorted(x.name for x in (rd / "clips").glob("*.mp4")) if (rd / "clips").exists() else []}
