# Command reference

[← Back to README](../README.md)

Every command and option in Video Clipper. In Claude Code you can type the options or just describe what
you want in plain words. In the Terminal, run them as `vclip <command> [options]` (see
[Running in the Terminal](#running-in-the-terminal)).

## Commands

| Command | What it does |
|---|---|
| `search "<query>"` | Searches YouTube for long videos to clip |
| `prep <link or file> [...]` | Downloads the audio (or reads your file), transcribes it and splits the transcript into chunks for Claude |
| `status <run folder>` | Shows how many chunks are picked and which are still left |
| `render <run folder>` | Makes the clips from the picked moments |

## `search` options

| Option | Values | Default | What it does |
|---|---|---|---|
| `--when` | `today`, `week`, `month`, `any` | `week` | How recent the videos must be |
| `--limit` | number | `7` | How many results to show |
| `--min-minutes` | number | `20` | Skips videos shorter than this |

## `prep` options

| Option | Values | Default | What it does |
|---|---|---|---|
| `--context` | text, e.g. `"startup podcast"` | none | Describes the video so Claude picks better moments |
| `--lang` | `en`, `auto`, `de`, `es`, `fr`, … | `en` | Spoken language (anything but `en` needs the multilingual setup) |
| `--name` | text, e.g. `"My Show"` | channel or file name | Creator or show name used in hooks and the folder name |
| `--cookies` | `chrome`, `safari`, `firefox`, or a `cookies.txt` path | none | Uses your browser login for age-restricted or "sign in" videos |
| `--jobs` | number | `2` | How many videos to prepare at once |
| `--chunk-min` | number | `12` | Minutes of transcript per chunk |
| `--force` | (no value) | off | Redoes a video that was already prepared |

## `render` options

| Option | Values | Default | What it does |
|---|---|---|---|
| `--top` | number | `3` | How many clips to make |
| `--min-score` | `0`–`10` | `7` | Quality bar for moments; lower it to get more clips |
| `--max-len` | seconds | `75` | Longest clip allowed |
| `--layout` | `auto`, `facecam`, `cam`, `full` | `auto` | How to frame the vertical video (see below) |
| `--quality` | `fast`, `standard`, `high`, `max` (or `720p`, `1080p`, `1440p`, `4k`) | `standard` | Source resolution and encode quality (see below) |
| `--cookies` | same as prep | taken from prep | Browser login for downloading the video sections |
| `--keep` | (no value) | off | Keeps the downloaded video pieces instead of deleting them |

### `--layout` values

| Value | Best for | Looks like |
|---|---|---|
| `auto` | anything | Picks one of the three below by itself |
| `facecam` | streams with a webcam box | Webcam on top, game or screen below |
| `cam` | podcasts, interviews, vlogs | Vertical crop centred on the speaker |
| `full` | screen recordings, tutorials, no webcam | Whole frame in the middle over a blurred background |

### `--quality` values

| Value | Source | Result |
|---|---|---|
| `fast` | up to 720p | Smaller, softer files; about the same time as standard |
| `standard` | up to 1080p | Normal (default) |
| `high` | up to 1440p | Sharper facecam, ~25 % slower, ~2× file size |
| `max` | best available, up to 4K | Sharpest; the same as `high` if the video has no 4K |

## Setup options (`setup.sh`)

| Option | Values | Default | What it does |
|---|---|---|---|
| `--multilingual` | (no value) | off | Also downloads the speech model for non-English videos (+465 MB) |
| `--model` | `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` (add `.en` for English-only) | `small.en` | Which speech model to use: smaller is faster, bigger is more accurate |

## Settings (environment variables)

| Variable | Default | What it sets |
|---|---|---|
| `VIDEO_CLIPS_DIR` | `~/Video-Clips` | Where clips are saved |
| `VIDEO_CLIPPER_HOME` | `~/.video-clipper` | Where the Python environment and config live |
| `VIDEO_CLIPPER_MODELS` | `~/.video-clipper/models` | Where models and the font are stored |
| `VIDEO_CLIPPER_WHISPER_MODEL` | from config | Use a specific speech model file |
| `VIDEO_CLIPPER_FONT` | Anton | Caption and hook font (`.ttf` / `.otf`) |

## Plain words Claude understands

| You write | Claude uses |
|---|---|
| "in high quality" | `--quality high` |
| "in 4K" / "best quality" | `--quality max` |
| "give me 5 clips" | `--top 5` |
| "use the full frame" | `--layout full` |
| "clips up to 90 seconds" | `--max-len 90` |
| "it's a German video" | `--lang de` |
| "it's a startup podcast" | `--context "startup podcast"` |
| "lower the bar, I want more clips" | `--min-score 6` |

## Examples in Claude Code

```
use video-clipper to clip <link> --quality high --top 5
use video-clipper to clip ~/Movies/podcast.mp4 --layout cam --context "health podcast"
use video-clipper to clip <German link> --lang de
/video-clipper clip <link> --quality max
```

## Running in the Terminal

The commands live in a script inside the installed plugin. The folder name includes the version, so it
changes with each update. Add this line to `~/.zshrc` to always run the newest installed version:

```bash
alias vclip='"$(ls -d ~/.claude/plugins/cache/aliabbosashurov/video-clipper/*/ | sort -V | tail -1)scripts/vclip"'
```

Open a new Terminal, then:

```bash
vclip --help
vclip render --help
vclip render ~/Video-Clips/<run folder> --quality high --top 5
```

For a plain-skill install (`git clone` into `~/.claude/skills`), the script is at
`~/.claude/skills/video-clipper/scripts/vclip`.

Picking the moments is Claude's job. In the Terminal you can run `search`, `prep`, `status` and
`render`, but `render` only works on runs whose `picks/*.json` files have been written (by Claude, or by
hand following [references/picking.md](../references/picking.md)).
