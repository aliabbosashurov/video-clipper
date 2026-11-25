# Development

[← Back to README](../README.md)

How the code is organised, where a change belongs, and how to check that nothing broke.

## Layout of the repo

```
SKILL.md                  instructions Claude follows (setup → prep → pick → render → report)
references/picking.md     how Claude picks moments + the picks JSON format
scripts/
  setup.sh                installs tools, the Python env and models into ~/.video-clipper
  vclip                   wrapper: runs vclip.py with the env from setup
  vclip.py                entry point (just calls videoclipper.cli)
  videoclipper/           the code, one module per responsibility (below)
tests/                    unit tests (no network, no videos needed)
docs/                     user documentation + this file
```

## How a video flows through the code

```
prep    sources.source_info ─► sources.download_audio ─► transcribe.transcribe ─► transcribe.clean_segments
                                                     └─► signals.loud_moments / chat_spikes
                                                                    └─► chunks.plan_chunks ─► write_chunks  →  chunks/*.md + chunk index
                                                         manifest.update  →  manifest.json (source, model, settings, timings)
pick    Claude reads chunks/*.md, writes picks/*.json (references/picking.md)
render  picks.select ─► per clip: sources.fetch_section ─► layout.detect + choose + plan
                                  ─► transcribe.clip_words ─► captions.caption_frames
                                  ─► encode ─► cover image ─► post.post_text
        summary.json + manifest.update (pick IDs, models, version, render settings)
```

## Modules

| module | owns | depends on |
|---|---|---|
| `config` | paths (`DATA`, `RUNS`, `SKILL`), `config.json`, quality levels, layout names | nothing |
| `util` | `log`, `run` (subprocess), `hms`, `parse_ts`, `slug` | nothing |
| `media` | ffprobe questions: duration, size, first video frame | util |
| `sources` | links + local files: metadata, audio download, section download, error hints | config, media, util |
| `signals` | loud moments, live-chat spikes | util |
| `transcribe` | Whisper model choice, transcripts (with a confidence per line), junk-line cleanup, caption word timings | config, util |
| `chunks` | `plan_chunks` cuts the transcript (a line belongs to the chunk where it starts, plus a 90 s lookahead), `write_chunks` writes `chunks/chunk_NN.md` and returns the chunk index for the manifest | util |
| `manifest` | `manifest.json`: reading and updating it, `require` (stops on a folder that isn't prepped), tool / Whisper versions, "prepped with other settings" check | config, util |
| `picks` | reading `picks/*.json`, giving each entry an ID (`c07-2`), checking it belongs to its chunk, reporting problems, choosing the moments to render | manifest, chunks, util |
| `layout` | facecam / cam / full detection (OpenCV) and the ffmpeg framing per mode | config, util |
| `captions` | hook box + word captions (Pillow), platform safe zone | config |
| `post` | the post text next to each clip (with its pick ID, model, version), hashtag clean-up | manifest, util |
| `prep`, `render`, `search`, `status` | one command each: put the pieces above together (`status` also flags picks older than their chunk and chunk files edited after prep) | the modules above |
| `cli` | command-line options → `PrepOptions` / `RenderOptions` → commands | commands |

Rules that keep it easy to change:

- **Dependencies point one way**: commands → building blocks → `config` / `util`. A building block never
  imports a command, and nothing imports `cli`.
- **No pipeline logic in `cli`.** It only turns options into `PrepOptions` / `RenderOptions` and calls a command.
- **Heavy libraries are imported inside the function that needs them** (`cv2` in `layout`, `PIL` in
  `captions`), so `--help`, `status` and the tests start instantly.
- **Run folders are the interface between steps.** Each step only reads and writes files in the run folder
  (`manifest.json`, `transcript.json`, `signals.json`, `chunks/`, `picks/`, `clips/`), so steps can be re-run
  on their own and Claude can inspect everything.

## Where a new feature goes

| you want to… | change |
|---|---|
| add a command-line option | `cli.py` (parser) + a field in `PrepOptions` / `RenderOptions` + use it in the command |
| add a quality level | `config.QUALITY` (+ an alias in `QUALITY_ALIASES`), then docs/usage.md and SKILL.md |
| add a layout (e.g. split-screen for two speakers) | `layout.detect` returns a new `mode`, `layout.plan` builds its filter, add the name to `config.LAYOUTS` |
| change how captions look | `captions.py` (fonts, colours, word grouping, `SAFE_*` limits) |
| support a new error message | add a pattern to `sources.ERROR_HINTS` |
| add a signal for the picker (e.g. laughter) | a function in `signals.py`, pass its events to `chunks.write_chunks`, explain the marker in references/picking.md. A per-line signal that comes from Whisper itself (like `conf`) goes in the `transcript.json` segment instead |
| change what goes in the post text | `post.py` |
| record a new fact about a run (a setting, a version, a count) | a section in `manifest.update(...)` from `prep.py` or `render.py`; the other sections are kept. Add a field to `prep` only if it should also be compared on re-runs (`prep._settings`) |
| change how moments are ranked | `picks.select` |
| change how the transcript is cut (chunk size, lookahead, where a cut falls) | `chunks.plan_chunks` (pure: lines in, chunks out). Bump `CHUNK_FORMAT` when the chunk text or the index changes, so prep warns about runs made the old way, and update references/picking.md |
| add a number to the chunk index (for status, or for skipping chunks) | the dict in `chunks.write_chunks`; it ends up in `manifest.json` under `chunks` |
| add a new step to the pipeline | a new module + a command in `cli.py`; keep its input/output in the run folder |

When a change is visible to users, also update `SKILL.md` (so Claude uses it), the docs in `docs/`, and
`docs/commands.md` for new options.

## Checking that nothing broke

**Unit tests** (seconds, no network, no videos):

```bash
~/.video-clipper/venv/bin/python -m unittest discover -s tests -v
```

**End to end** on a short video of your own:

```bash
VC=scripts/vclip; export VIDEO_CLIPS_DIR=/tmp/vc-test
"$VC" prep ~/Movies/some-short-video.mp4
#  write picks/chunk_01.json by hand (format in references/picking.md), then:
"$VC" status /tmp/vc-test/<run folder>
"$VC" render /tmp/vc-test/<run folder> --top 2
```

Check `manifest.json` in the run folder afterwards: it should name the Whisper model you configured, and
`clips/summary.json` and each clip's `.txt` should carry the pick ID (`c01-1`).

Run folders without a `manifest.json` (made by 1.0.4 or older) are not supported: `render` stops with "not a prepped
run folder". Prep the video again (`--force`).

Rendering is deterministic: the same picks and the same code give byte-identical mp4 files. That makes
refactors easy to check. Render once before the change and once after, then compare `md5` of the clips.

**Plugin manifest**:

```bash
claude plugin validate . --strict
```

## Releasing

1. Bump `"version"` in `.claude-plugin/plugin.json` (users only receive an update when it changes).
2. Commit and push.
3. Users update with `/plugin marketplace update aliabbosashurov`, then `/plugin update video-clipper@aliabbosashurov`.
