"""manifest.json: one file per run folder with the source, how prep was done, timings and the last render."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from .config import SKILL
from .util import run

SCHEMA = 1


def tool_version() -> str:
    try:
        return json.loads((SKILL / ".claude-plugin" / "plugin.json").read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def whisper_cli_version() -> str:
    try:
        m = re.search(r"version:\s*(\S+)", run(["whisper-cli", "--version"]).stdout)
    except OSError:
        return "unknown"
    return m.group(1) if m else "unknown"


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def read(rd: Path) -> dict:
    """The run's manifest, or {} when the folder has none."""
    p = rd / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def require(rd: Path) -> dict:
    """The manifest of a prepped run folder; stops with a clear message for anything else."""
    m = read(rd)
    if "prep" not in m or "chunks" not in m:
        raise SystemExit(f"{rd} has not been prepped (no finished manifest.json there): run prep first.")
    return m


def update(rd: Path, **sections) -> dict:
    """Replace the given top-level sections and keep the rest."""
    m = read(rd)
    m.update(sections)
    m["schema"] = SCHEMA
    m.setdefault("created", now())
    (rd / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False))
    return m


def stale_reason(m: dict, now_settings: dict) -> str | None:
    """What differs between how a run was prepped and how prep would run now, or None when it matches."""
    was = m.get("prep") or {}
    diffs = [f"{k}: {was[k]} -> {v}" for k, v in now_settings.items() if k in was and was[k] != v]
    return ", ".join(diffs) or None
