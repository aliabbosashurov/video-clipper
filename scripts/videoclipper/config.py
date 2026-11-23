"""Paths, settings and render quality levels. Everything else imports its configuration from here."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]  # scripts/videoclipper/config.py -> the skill folder
# venv, models and config live outside the skill folder, so they survive plugin updates
DATA = Path(os.environ.get("VIDEO_CLIPPER_HOME") or Path.home() / ".video-clipper").expanduser()
CFG: dict = json.loads((DATA / "config.json").read_text()) if (DATA / "config.json").exists() else {}
# every location can be moved with an env var; config.json is written by setup.sh
RUNS = Path(os.environ.get("VIDEO_CLIPS_DIR") or CFG.get("clips_dir") or Path.home() / "Video-Clips").expanduser()
YTDLP = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--quiet", "--no-progress"]
LAYOUTS = ("auto", "facecam", "cam", "full")


@dataclass(frozen=True)
class Quality:
    """render --quality: source resolution to download and how hard to encode.
    Output is always 1080x1920; a bigger source means less enlarging of a small facecam."""
    height: int | None  # None = the best the video has
    preset: str         # x264 preset
    crf: int            # x264 quality (lower = better, bigger)
    sharpen: bool       # light unsharp on the face panel


QUALITY = {
    "fast":     Quality(720, "veryfast", 22, False),
    "standard": Quality(1080, "veryfast", 20, False),
    "high":     Quality(1440, "medium", 18, True),
    "max":      Quality(None, "medium", 18, True),  # differs from high only on 4K sources
}
QUALITY_ALIASES = {"720p": "fast", "720": "fast", "1080p": "standard", "1080": "standard", "default": "standard",
                   "1440p": "high", "1440": "high", "2k": "high", "4k": "max", "2160p": "max", "2160": "max",
                   "best": "max"}


def resolve_quality(name: str) -> str:
    """'4K', '1440p', 'best' ... -> one of the QUALITY keys."""
    v = QUALITY_ALIASES.get(name.lower(), name.lower())
    if v not in QUALITY:
        raise ValueError(f"use one of: {', '.join(QUALITY)} (or 720p, 1080p, 1440p, 4k)")
    return v


def is_ready() -> bool:
    """setup.sh finished successfully."""
    return (DATA / ".ready").exists()
