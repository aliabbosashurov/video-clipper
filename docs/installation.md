# Installation

[← Back to README](../README.md)

## Requirements

| | |
|---|---|
| **Operating system** | macOS only. Tested on Apple Silicon (M-series). Intel Macs should work, but transcription is much slower. |
| **Memory** | 8 GB minimum, 16 GB recommended (needed to process 2 videos at once) |
| **Disk space** | ~650 MB for the install (Python environment ~135 MB, speech model ~465 MB). Each video in progress needs 0.2–1 GB of temporary space. Finished clips are 5–15 MB each. |
| **Claude Code** | any plan that runs [Claude Code](https://claude.com/claude-code) |

Setup checks for these tools and, if [Homebrew](https://brew.sh) is installed, installs the missing ones for you:

| tool | used for |
|---|---|
| `ffmpeg` / `ffprobe` (with libx264) | cutting and encoding video |
| `whisper-cli` ([whisper.cpp](https://github.com/ggml-org/whisper.cpp)) | speech-to-text on your Mac |
| Python 3.9+ or [uv](https://docs.astral.sh/uv/) | the clipping script |
| `deno` (recommended) | YouTube downloads |
| `curl` | downloading models (ships with macOS) |

## Install

### Option A: as a plugin (recommended)

In Claude Code, run:

```
/plugin marketplace add aliabbosashurov/video-clipper
/plugin install video-clipper@aliabbosashurov
```

Or from your terminal:

```bash
claude plugin marketplace add aliabbosashurov/video-clipper
claude plugin install video-clipper@aliabbosashurov
```

Then restart Claude Code and say *"set up the video clipper"*. Claude runs setup for you.

### Option B: as a plain skill

```bash
git clone https://github.com/aliabbosashurov/video-clipper.git ~/.claude/skills/video-clipper
bash ~/.claude/skills/video-clipper/scripts/setup.sh
```

Then restart Claude Code. To use it in one project only, clone it into
`<your-project>/.claude/skills/video-clipper` instead.

### What setup does

- Checks each tool and installs missing ones with Homebrew (or tells you how to get them)
- Creates a private Python environment in `~/.video-clipper/venv`
- Downloads the speech model, a face detector and the caption font into `~/.video-clipper/models`
- Writes `~/.video-clipper/config.json` and prints `READY`

These live outside the skill folder, so updating the plugin doesn't delete them or download them again.

It's safe to run again at any time. Re-running also updates the downloader, which fixes most download errors.

## Setup options

| option | what it does |
|---|---|
| `--multilingual` | also downloads the multilingual speech model, needed for videos that aren't in English (+465 MB) |
| `--model NAME` | picks a different speech model (see below) |

| model | size | when to use it |
|---|---|---|
| `tiny.en` / `tiny` | 75 MB | very fast, rough transcript |
| `base.en` / `base` | 142 MB | older or slower Macs, low disk space |
| `small.en` (default) / `small` | 465 MB | good balance |
| `medium.en` / `medium` | 1.5 GB | best accuracy, slower |
| `large-v3-turbo` | 1.6 GB | multilingual, high accuracy |

Models ending in `.en` are English-only.

Ask Claude (*"set up the video clipper with the multilingual model"*), or run it yourself:

```bash
bash ~/.claude/skills/video-clipper/scripts/setup.sh --model medium.en
bash ~/.claude/skills/video-clipper/scripts/setup.sh --multilingual
```

## Installing without Homebrew

Install these yourself, then run setup again:

- **ffmpeg**: a static build from [evermeet.cx/ffmpeg](https://evermeet.cx/ffmpeg/). Put `ffmpeg` and
  `ffprobe` on your `PATH`.
- **whisper-cli**: build [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
  (`cmake -B build && cmake --build build -j`) and put `build/bin/whisper-cli` on your `PATH`.
- **Python 3.9+**: from [python.org](https://www.python.org/downloads/macos/), or run `xcode-select --install`.
- **deno** (for YouTube): [deno.com](https://deno.com)

## Configuration

Setup writes `~/.video-clipper/config.json` (see [`config.example.json`](../config.example.json)).
These environment variables override it:

| variable | default | what it sets |
|---|---|---|
| `VIDEO_CLIPS_DIR` | `~/Video-Clips` | where clips and working files are saved |
| `VIDEO_CLIPPER_HOME` | `~/.video-clipper` | where the Python environment and `config.json` live |
| `VIDEO_CLIPPER_MODELS` | `~/.video-clipper/models` | where setup stores models and the font (set it when you run setup) |
| `VIDEO_CLIPPER_WHISPER_MODEL` | from `config.json` | path to a specific `ggml-*.bin` speech model |
| `VIDEO_CLIPPER_FONT` | Anton, then Arial Black / Impact | font for the captions and hook (`.ttf` / `.otf`) |

If a speech model is already in `~/.cache/whisper-cpp/`, setup reuses it instead of downloading it again.

## Updating

Plugin:

```bash
claude plugin marketplace update aliabbosashurov
claude plugin update video-clipper@aliabbosashurov
```

Plain skill:

```bash
cd ~/.claude/skills/video-clipper && git pull
```

After updating, it's worth saying *"set up the video clipper"* once: it refreshes the downloader and installs
anything new. Your models are kept.

## Uninstalling

```bash
claude plugin uninstall video-clipper@aliabbosashurov   # plugin install
rm -rf ~/.claude/skills/video-clipper                   # plain-skill install
rm -rf ~/.video-clipper                                 # Python environment, models, config
rm -rf ~/Video-Clips                                    # your clips: only if you no longer need them
```

Tools installed with Homebrew (ffmpeg, whisper-cpp, deno) stay installed. Remove them with `brew uninstall`
if nothing else uses them.
