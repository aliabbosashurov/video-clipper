"""search: long YouTube videos / stream replays for a query, most viewed first."""
from __future__ import annotations

import datetime as dt
import json
import urllib.parse

from . import config
from .sources import ytdlp_json
from .util import hms, log, slug

WHEN = {"today": "EgIIAg%3D%3D", "week": "EgIIAw%3D%3D", "month": "EgIIBA%3D%3D", "any": ""}  # YouTube upload-date filter


def search(query: str, when: str = "week", limit: int = 7, min_minutes: int = 20) -> list[dict]:
    sp = WHEN[when]
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}" + (f"&sp={sp}" if sp else "")
    log(f"Searching YouTube for long videos: {query!r} ({when})")
    try:
        pl = ytdlp_json(url, extra=["--flat-playlist", "--playlist-end", str(max(40, limit * 5))])
    except Exception as e:
        raise SystemExit(f"Search failed: {e}")
    found, seen = [], set()
    for e in pl.get("entries") or []:
        if not e or e.get("id") in seen or e.get("live_status") == "is_live":
            continue
        if (e.get("duration") or 0) < min_minutes * 60:
            continue
        seen.add(e["id"])
        found.append({"channel": e.get("channel") or e.get("uploader") or "", "title": e.get("title", ""),
                      "views": e.get("view_count") or 0, "length": hms(e.get("duration") or 0),
                      "url": f"https://www.youtube.com/watch?v={e['id']}"})
    found = sorted(found, key=lambda v: -v["views"])[:limit]
    config.RUNS.mkdir(parents=True, exist_ok=True)
    (config.RUNS / f"search-{dt.date.today()}-{slug(query, 30)}.json").write_text(json.dumps(found, indent=2))
    for i, v in enumerate(found, 1):
        log(f"{i}. {v['channel']} ({v['length']}, {v['views']:,} views) {v['title'][:80]}\n   {v['url']}")
    if not found:
        log("Nothing found. Try --when any, a lower --min-minutes, or paste links instead.")
    return found
