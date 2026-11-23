"""Small helpers shared by every module: logging, running commands, time and name formatting."""
from __future__ import annotations

import re
import subprocess


def log(*a) -> None:
    print(*a, flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """Run a command, capturing stdout / stderr as text. Callers check returncode themselves."""
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def hms(s: float) -> str:
    s = max(0, int(round(s)))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_ts(v) -> float:
    """'01:02:03', '62:03', '3.5' or a number -> seconds."""
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(p) for p in str(v).strip().split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def slug(s: str | None, n: int = 40, whole_words: bool = False) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s or "video").strip("-").lower()
    if whole_words and len(s) > n and "-" in s[:n + 1]:
        return s[:n + 1].rsplit("-", 1)[0]  # "...-in-gta-6" instead of "...-in-gta-6-an"
    return s[:n] or "video"
