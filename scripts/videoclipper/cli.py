"""Command line: parses the options and hands them to the command modules. No pipeline logic lives here."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config
from .prep import PrepOptions, prep_all
from .render import RenderOptions, render_run
from .search import WHEN, search
from .status import run_status
from .util import log


def quality_arg(v: str) -> str:
    try:
        return config.resolve_quality(v)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Video Clipper: long video -> vertical clips. See SKILL.md.")
    sp = p.add_subparsers(dest="cmd", required=True)
    se = sp.add_parser("search"); se.add_argument("query")
    se.add_argument("--limit", type=int, default=7)
    se.add_argument("--when", choices=list(WHEN), default="week")
    se.add_argument("--min-minutes", type=int, default=20, help="skip videos shorter than this")
    pr = sp.add_parser("prep"); pr.add_argument("sources", nargs="+", help="links or video file paths")
    pr.add_argument("--cookies", help="chrome / safari / firefox, or a cookies.txt path (age-restricted YouTube, Kick)")
    pr.add_argument("--jobs", type=int, default=2, help="videos processed at once (2 is safe on a 16 GB Mac)")
    pr.add_argument("--lang", default="en", help="spoken language: en, auto, de, es, ... (non-en needs setup --multilingual)")
    pr.add_argument("--context", help="one line about the video, shown to the picker (e.g. 'startup podcast, guest is a VC')")
    pr.add_argument("--name", help="creator / show name for hooks and run folder (default: channel, or file name)")
    pr.add_argument("--chunk-min", type=int, default=12, help="minutes of transcript per chunk")
    pr.add_argument("--force", action="store_true")
    s = sp.add_parser("status"); s.add_argument("run")
    r = sp.add_parser("render"); r.add_argument("run")
    r.add_argument("--top", type=int, default=3); r.add_argument("--min-score", type=float, default=7.0)
    r.add_argument("--max-len", type=float, default=75, help="longest clip in seconds")
    r.add_argument("--layout", choices=config.LAYOUTS, default="auto",
                   help="auto, facecam (cam box on top), cam (9:16 crop on the speaker), full (whole frame on blur)")
    r.add_argument("--quality", type=quality_arg, default="standard", metavar="LEVEL",
                   help="fast (720p), standard (1080p, default), high (1440p), max (best available, up to 4K). "
                        "Higher = sharper facecam but slower downloads and renders. Also accepts 720p/1080p/1440p/4k")
    r.add_argument("--cookies"); r.add_argument("--keep", action="store_true", help="keep downloaded source sections")
    return p


def main(argv: list[str] | None = None) -> None:
    a = parser().parse_args(argv)
    if not config.is_ready():
        raise SystemExit(f"Not set up yet. Run: bash \"{config.SKILL / 'scripts' / 'setup.sh'}\"")
    if a.cmd == "search":
        search(a.query, a.when, a.limit, a.min_minutes)
    elif a.cmd == "prep":
        prep_all(a.sources, PrepOptions(cookies=a.cookies, lang=a.lang, context=a.context, name=a.name,
                                        chunk_min=a.chunk_min, force=a.force, jobs=a.jobs))
    elif a.cmd == "status":
        log(json.dumps(run_status(Path(a.run)), indent=1, ensure_ascii=False))
    elif a.cmd == "render":
        render_run(Path(a.run), RenderOptions(top=a.top, min_score=a.min_score, max_len=a.max_len, layout=a.layout,
                                              quality=a.quality, cookies=a.cookies, keep=a.keep))
