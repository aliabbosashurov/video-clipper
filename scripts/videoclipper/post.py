"""The post next to each clip (clip_NN_<title>.txt): title, caption, hashtags and where it came from."""
from __future__ import annotations

import re
from pathlib import Path

from .util import hms


def hashtags(tags) -> str:
    """'#GTA6', 'gta 6', '#gta6' -> one '#GTA6'. Accepts a list or a space-separated string."""
    if isinstance(tags, str):
        tags = tags.split()
    out, seen = [], set()
    for t in tags or []:
        if not isinstance(t, str):
            continue
        t = re.sub(r"[^\w]", "", t)  # drops '#', spaces and punctuation, keeps letters in any language
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append("#" + t)
    return " ".join(out)


def post_text(c: dict, info: dict, mode: str, quality: str, W: int, H: int) -> str:
    tags = hashtags(c.get("hashtags"))
    source = info["webpage_url"] if info["platform"] != "local" else Path(info["path"]).name
    return (f"TITLE: {c.get('title', '')}\n\nCAPTION:\n{c.get('caption', '')}\n\n{tags}\n\n"
            f"Source: {info['streamer']}, {source} at {hms(c['_s'])}\n"
            f"Category: {c.get('category')}  Score: {c.get('score')}  Layout: {mode}  "
            f"Quality: {quality} (source {W}x{H})\n")
