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


def shot_cuts(src: Path | str, start: float, end: float, thr: float = 0.3) -> list[float]:
    """Times (in the file's own clock) of hard shot changes between `start` and `end`. Needs a decode pass over
    just that window, so ask for a few seconds, not the whole file."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{max(0.0, start):.3f}", "-t", f"{end - start:.3f}",
             "-i", str(src), "-an", "-vf", f"scale=320:-2,select='gt(scene,{thr})',showinfo", "-f", "null", "-"])
    out = []
    for line in r.stderr.splitlines():
        if "pts_time:" in line:
            try:
                out.append(max(0.0, start) + float(line.split("pts_time:")[1].split()[0]))
            except ValueError:
                pass
    return out
