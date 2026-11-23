# Video Clipper

A Claude Code skill that turns any long video into ready-to-post vertical clips (1080x1920, 9:16):
hook title, word-by-word captions, loudness-normalised audio, and a post title + caption + hashtags per clip.

Works with podcasts, interviews, talks, gaming and IRL streams, tutorials, screen recordings and vlogs, from a
link (YouTube, Twitch, Kick, Vimeo, or anything else [yt-dlp](https://github.com/yt-dlp/yt-dlp) supports) or a
video file on your Mac.

How it works:

1. **prep**: downloads the audio only (or reads it from your file), transcribes it on your Mac with
   whisper.cpp, marks loud moments and live-chat spikes, and splits the transcript into 12-minute chunks.
2. **pick**: Claude (your Claude Code session, no API key) reads each chunk and writes the best moments as
   JSON, following `references/picking.md`.
3. **render**: ranks the picks, downloads or cuts only those minutes, picks a vertical layout, burns in
   the hook and captions, normalises loudness to -14 LUFS, and writes the clips.

Everything runs locally except the downloads. The skill is fully self-contained: its Python environment,
models and font live inside this folder, and it doesn't need any other skill.

## Requirements

| | |
|---|---|
| OS | **macOS only.** Tested on macOS 27.2, Apple Silicon (M-series). Intel Macs should work but transcribe much slower. Windows and Linux are not supported. |
| Memory | 8 GB minimum, 16 GB recommended (needed to prep 2 videos at once) |
| Disk | ~650 MB for the install (Python env ~135 MB, `small.en` model ~465 MB, face detector + font < 1 MB). `medium` models add ~1.5 GB. Each video in progress needs ~0.2-1 GB of temporary space; finished clips are ~5-15 MB each |
| Tools | `ffmpeg` + `ffprobe` (with libx264), `whisper-cli` (whisper.cpp), Python 3.9+ (or [uv](https://docs.astral.sh/uv/)), `curl`. `deno` is recommended for YouTube links |
| Claude Code | any plan that runs Claude Code |

With [Homebrew](https://brew.sh) installed, setup installs the missing tools for you. Without Homebrew it
lists exactly what's missing and how to get it.

## Install (fresh Mac)

1. Put the skill folder where Claude Code looks for personal skills:

   ```bash
   mkdir -p ~/.claude/skills
   git clone <video-clipper repo URL> ~/.claude/skills/video-clipper
   # or: copy/unzip this folder to ~/.claude/skills/video-clipper
   ```

   For a single project only, use `<project>/.claude/skills/video-clipper` instead.

2. Run setup (or ask Claude Code to "set up the video clipper"):

   ```bash
   bash ~/.claude/skills/video-clipper/scripts/setup.sh
   ```

   It checks every dependency, creates `.venv/` inside the skill folder, downloads the Whisper model, the
   YuNet face detector and the Anton caption font into `models/`, writes `config.json`, and ends with
   `READY`. Safe to re-run. Re-running also updates yt-dlp, which fixes most "download failed" errors.

   | option | what it does |
   |---|---|
   | `--multilingual` | also download the multilingual model, for non-English videos (`prep --lang de`, `--lang auto`) |
   | `--model base.en` | a smaller, faster model (`tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo`; add `.en` for English-only where available) |

3. Restart Claude Code (or start a new session) so it picks up the skill.

### If Homebrew isn't installed

Install these yourself, then re-run setup:

- **ffmpeg**: a static build from https://evermeet.cx/ffmpeg/ (put `ffmpeg` and `ffprobe` on your `PATH`)
- **whisper-cli**: build https://github.com/ggml-org/whisper.cpp (`cmake -B build && cmake --build build -j`)
  and put `build/bin/whisper-cli` on your `PATH`
- **Python 3.9+**: https://www.python.org/downloads/macos/ or `xcode-select --install`
- **deno** (YouTube only): https://deno.com

## Use

In Claude Code, just ask:

- `clip this video https://www.youtube.com/watch?v=...`
- `make 5 shorts from ~/Movies/episode-12.mp4, it's a startup podcast`
- `clip this German interview: <link>` (needs `--multilingual` setup)
- `find podcast episodes about sleep from this week and clip them`
- `make clip 2 start earlier` / `clip 3 has the wrong framing, use the full frame`

Claude runs the commands, reads the transcript, picks the moments and reports each clip's title,
timestamp, length, layout and path. You can also run the pipeline by hand:

```bash
S=~/.claude/skills/video-clipper
PY="$S/.venv/bin/python"

"$PY" "$S/scripts/vclip.py" search "startup podcast" --when week --limit 5
"$PY" "$S/scripts/vclip.py" prep ~/Movies/episode.mp4 --context "startup podcast, guest is a VC"
#   -> prints the run folder, e.g. ~/Video-Clips/2026-11-23-episode-1a2b3c4d5e
#   write picks/chunk_NN.json for every chunk (Claude does this; format in references/picking.md)
"$PY" "$S/scripts/vclip.py" status ~/Video-Clips/2026-11-23-episode-1a2b3c4d5e
"$PY" "$S/scripts/vclip.py" render ~/Video-Clips/2026-11-23-episode-1a2b3c4d5e --top 3
```

| command | main options |
|---|---|
| `search QUERY` | `--when today/week/month/any`, `--limit 7`, `--min-minutes 20` |
| `prep SRC...` | `--context "..."`, `--lang en/auto/de/...`, `--name "Show"`, `--cookies chrome`, `--jobs 2`, `--chunk-min 12`, `--force` |
| `status RUN` | lists the chunks that still need picks |
| `render RUN` | `--top 3`, `--min-score 7`, `--max-len 75`, `--layout auto/facecam/cam/full`, `--keep`, `--cookies` |

### Output

```
~/Video-Clips/<date>-<creator>-<id>/
  stream.json  transcript.json  signals.json  timing.json
  chunks/chunk_01.md ...        transcript pieces with [HH:MM:SS] timestamps and LOUD / CHAT markers
  picks/chunk_01.json ...       the chosen moments (edit these to change a clip)
  clips/clip_01_<title>.mp4     the vertical clip
  clips/clip_01_<title>.txt     title, caption, hashtags, source + timestamp, category, score, layout
  clips/summary.json
```

### Layouts

Chosen per clip from faces found in frames sampled across the clip. Override for a whole run with
`--layout`, or for one clip with `"layout"` in its pick.

| layout | when | result |
|---|---|---|
| `facecam` | a small face in a box with fixed edges (any position) over moving content: streams, screen shares | facecam box on top, the rest of the frame below |
| `cam` | a person on camera with a static background: podcasts, interviews, vlogs, talking heads | 9:16 crop centred on the main face |
| `full` | no steady face: screen recordings, gameplay without a cam, travel footage | the whole frame centred over a blurred copy |

### Your files are safe

Local videos are only ever read: never moved, re-encoded in place or deleted. Prep deletes only its own
temporary audio. Render deletes only the sections it downloaded or cut (`--keep` keeps them).

## Configuration

`setup.sh` writes `config.json` (see `config.example.json`). Environment variables override it:

| variable | default | |
|---|---|---|
| `VIDEO_CLIPS_DIR` | `~/Video-Clips` | where runs and clips are written |
| `VIDEO_CLIPPER_MODELS` | `<skill>/models` | where setup puts models + font (set it when running setup) |
| `VIDEO_CLIPPER_WHISPER_MODEL` | from config | use a specific `ggml-*.bin` Whisper model |
| `VIDEO_CLIPPER_FONT` | Anton, then Arial Black / Impact | caption + hook font (`.ttf` / `.otf`) |

If a Whisper model is already in `~/.cache/whisper-cpp/`, setup reuses it instead of downloading again.

## Troubleshooting

| problem | fix |
|---|---|
| `Not set up yet` | run `scripts/setup.sh` and fix any `[MISSING]` lines |
| `Sign in to confirm you're not a bot` / age-restricted / 403 | `prep ... --cookies chrome` (or `safari`, `firefox`, or a `cookies.txt` path); render reuses it |
| YouTube download fails suddenly | re-run setup (updates yt-dlp); make sure `deno` is installed |
| `still live on YouTube` | wait for the replay to finish processing, then prep again |
| `needs a multilingual Whisper model` | `scripts/setup.sh --multilingual` |
| transcript is gibberish | wrong language: `prep ... --lang auto --force` (or the right code) |
| wrong face on top / speaker cut off | add `"layout": "full"` (or `"cam"`, `"facecam"`) to that pick, delete the mp4, render again |
| fewer clips than asked | not enough moments scored 7+. Try `--min-score 6`, or there may be nothing better |
| captions in a plain font | the Anton download failed: re-run setup or set `VIDEO_CLIPPER_FONT` |
| slow transcription | use `--model base.en` at setup; prep one video at a time (`--jobs 1`) |

## Limits

- The face detector samples 12 frames per clip. A clip that switches between very different layouts
  partway through gets one layout. Override it per pick.
- `cam` uses one fixed crop per clip. It doesn't track a speaker who walks across the frame.
- Chat spikes are only available for YouTube replays with live chat.
- Only clip content you own or have permission to repost. Watch every clip before posting it.

## License

MIT, see `LICENSE`. The Anton font is downloaded at setup under the SIL Open Font License. The YuNet model
comes from [opencv_zoo](https://github.com/opencv/opencv_zoo) and the Whisper models from
[whisper.cpp](https://huggingface.co/ggerganov/whisper.cpp).
