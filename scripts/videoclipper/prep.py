"""prep (steps 1 + 2): audio only -> local transcript + signals -> chunks for the picker, one run folder per video."""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from .chunks import write_chunks
from .signals import chat_spikes, loud_moments
from .sources import download_audio, source_info
from .transcribe import clean_segments, transcribe
from .util import hms, log, run, slug


@dataclass
class PrepOptions:
    cookies: str | None = None   # browser name or cookies.txt (age-restricted / members-only / Kick)
    lang: str = "en"             # spoken language for Whisper ("auto" to detect)
    context: str | None = None   # one line about the video, shown to the picker
    name: str | None = None      # creator / show name (default: channel, or file name)
    chunk_min: int = 12          # minutes of transcript per chunk
    force: bool = False          # redo a video that was already prepped
    jobs: int = 2                # videos processed at once


def prep_all(sources: list[str], opts: PrepOptions) -> list[dict]:
    """Prep every source (in parallel), print a summary, return one result dict per source."""
    config.RUNS.mkdir(parents=True, exist_ok=True)
    results = []
    with cf.ThreadPoolExecutor(opts.jobs) as ex:
        futs = {ex.submit(prep_one, s, opts): s for s in sources}
        for f in cf.as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                results.append({"url": futs[f], "error": str(e)})
                log(f"FAILED {futs[f]}: {e}")
    log("\nRUNS:")
    for r in results:
        log(f"  {r.get('run') or r.get('url')}  {r.get('error') or ''}")
    return results


def run_dir(info: dict) -> Path:
    return config.RUNS / f"{dt.date.today()}-{slug(info['streamer'], 24)}-{slug(str(info['id']), 16)}"


def prep_one(src: str, opts: PrepOptions) -> dict:
    t0 = time.time()
    info = source_info(src, opts.cookies, opts.name)
    info.update({"lang": opts.lang, "context": opts.context})
    who = info["streamer"]
    rd = run_dir(info)
    (rd / "chunks").mkdir(parents=True, exist_ok=True)
    (rd / "picks").mkdir(exist_ok=True)
    (rd / "stream.json").write_text(json.dumps(info, indent=2))
    if (rd / "transcript.json").exists() and not opts.force:
        log(f"[{who}] already prepped -> {rd}")
        return {"run": str(rd), "streamer": who, "cached": True}

    try:
        return _audio_to_chunks(rd, info, opts, t0)
    finally:  # also after a crash or Ctrl-C: never leave the big temporary audio behind
        for p in [*rd.glob("audio.*"), rd / "whisper.json"]:
            p.unlink(missing_ok=True)


def _audio_to_chunks(rd: Path, info: dict, opts: PrepOptions, t0: float) -> dict:
    who = info["streamer"]
    wav = rd / "audio.wav"
    if info["platform"] == "local":
        log(f"[{who}] 1/2 reading audio from the file ({hms(info['duration'])})")
        r = run(["ffmpeg", "-y", "-loglevel", "error", "-i", info["path"], "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        if r.returncode != 0:
            raise RuntimeError("audio extract failed: " + r.stderr[-300:])
    else:
        log(f"[{who}] 1/2 downloading audio only ({hms(info.get('duration') or 0)} video)")
        audio = download_audio(rd, info)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-ac", "1", "-ar", "16000", str(wav)])
        audio.unlink(missing_ok=True)
    t_dl = time.time()

    log(f"[{who}] 2/2 transcribing on this Mac ({opts.lang}) + scanning for loud moments and chat spikes")
    with cf.ThreadPoolExecutor(2) as ex:
        fs = ex.submit(transcribe, wav, rd / "whisper", opts.lang)
        fl = ex.submit(loud_moments, wav)
        raw = fs.result()
        loud, _ = fl.result()
    chat = chat_spikes(next(iter(rd.glob("chat*.live_chat.json")), None))
    wav.unlink(missing_ok=True)
    (rd / "whisper.json").unlink(missing_ok=True)
    segs = clean_segments(raw)
    (rd / "transcript.json").write_text(json.dumps(segs))
    (rd / "signals.json").write_text(json.dumps({"loud": loud, "chat": chat}, indent=1))
    n = write_chunks(rd, info, segs, loud, chat, opts.chunk_min * 60, opts.context)
    timing = {"prep_started": t0, "download_sec": round(t_dl - t0), "analyse_sec": round(time.time() - t_dl),
              "chunks": n, "segments": len(segs), "junk_lines_removed": len(raw) - len(segs),
              "loud_events": len(loud), "chat_spikes": len(chat)}
    (rd / "timing.json").write_text(json.dumps(timing, indent=1))
    log(f"[{who}] ready: {n} chunks, {len(loud)} loud moments, {len(chat)} chat spikes "
        f"({round(time.time() - t0)}s) -> {rd}")
    return {"run": str(rd), "streamer": who, "chunks": n}
