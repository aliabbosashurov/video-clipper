"""Questions about a media file, answered by ffprobe."""
from __future__ import annotations

import json
from pathlib import Path

from .util import run


def probe_duration(path: Path | str) -> float:
    """Length in seconds, or 0.0 if ffprobe can't read it."""
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def probe_video(path: Path | str) -> tuple[int, int, float]:
    """(width, height, duration) of the first video stream."""
    pr = json.loads(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=width,height:format=duration", "-of", "json", str(path)]).stdout)
    return pr["streams"][0]["width"], pr["streams"][0]["height"], float(pr["format"]["duration"])


def video_start(src: Path | str) -> float:
    """Time of the first video frame in a file. A downloaded section only has picture from its first
    keyframe on (YouTube 1440p / 4K can go 5-10 s between keyframes); before that it's audio only."""
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
             "-of", "csv=p=0", "-read_intervals", "%+#1", str(src)])
    try:
        return float(r.stdout.split()[0])
    except (IndexError, ValueError):
        return 0.0
