---
name: video-clipper
description: Video Clipper. Turns any long video (podcast, interview, talk, gaming or IRL stream, tutorial, screen recording, vlog) into ready-to-post vertical 9:16 clips with a hook title, word-by-word captions, normalised audio, and a post title + caption + hashtags. Works from a link (YouTube, Twitch, Kick, Vimeo, anything yt-dlp supports) or a local video file. Activates on "set up the video clipper", "clip this video <link or file>", "make shorts from this podcast", "turn this stream into clips", "find videos about <topic> and clip them", /video-clipper, or any request to cut a long video into short vertical clips. Downloads audio only, transcribes on the Mac, the Claude session itself reads the transcript chunk by chunk and picks the moments (no API keys), then cuts only the needed minutes and renders 3 clips per video. macOS only.
---

# Video Clipper

Long video (link or file) -> 3 ready-to-post 1080x1920 clips. Everything except the picking runs on this
Mac. The picking is done by YOU (this Claude Code session), so it needs no API keys.

`S` = this skill's folder: `${CLAUDE_SKILL_DIR}` (the folder holding this SKILL.md). Run every command
through the wrapper `"$S/scripts/vclip" <command> ...` (it uses the Python environment made by setup).
Quote every path: they may contain spaces. This skill is self-contained: never use files, models or
scripts from any other skill.

## 0. Setup ("set up the video clipper", or any command says "Not set up yet")

macOS only. On Windows or Linux, tell the user it isn't supported and stop.

Run `bash "$S/scripts/setup.sh"`. It checks ffmpeg, whisper-cpp, deno and Python, then builds the Python
environment and downloads the Whisper model, face detector and caption font into `~/.video-clipper/`
(`$VIDEO_CLIPPER_HOME`), outside the skill folder so plugin updates keep them. It prints READY or a list of
`[MISSING]` items with how to install each one. Tell the user in plain words what was installed. If
something is missing and Homebrew isn't installed, relay the hint lines; don't guess.

- Non-English videos: `bash "$S/scripts/setup.sh" --multilingual`.
- Slow Mac or low disk: `--model base.en` (faster, rougher transcript). Better accuracy: `--model medium.en`.
- Re-run setup if downloads start failing: it updates yt-dlp.

## 1+2. Get the video ready ("prep")

`prep <source> [<source> ...]` where a source is a link or a local file path.

- Ask nothing unless it's unclear what to clip. Pass what you know:
  - `--context "one line about the video"` (e.g. "startup podcast, guest is a VC", "Elden Ring stream",
    "Excel tutorial"). It's shown at the top of every chunk to guide the picking.
  - `--lang de` (or `auto`) for non-English speech. `--name "Show Name"` when a file name is meaningless.
- No link given but a topic ("find podcast episodes about sleep and clip them"): run `search "<query>"`
  (`--when today|week|month|any`, `--limit N`, `--min-minutes 20`), show the list, then `prep` the URLs.
- Age-restricted YouTube or Kick: add `--cookies chrome` (or safari/firefox). Retry with it if a download
  fails with "Sign in to confirm" / 403.
- When an error ends with a `Hint:` line (sign-in, private, region-blocked, members-only, removed video…),
  follow the hint or pass it on to the user in plain words; don't retry blindly.
- `--jobs 2` (default) preps 2 videos at once; don't go higher on a 16 GB Mac.
- Long videos take minutes (download + transcript; Intel Macs are much slower). Run prep in the background
  for long or multiple videos and tell the user it's running.

Local files are only read, never moved, changed or deleted. Prep writes a run folder under `~/Video-Clips/`
(or `$VIDEO_CLIPS_DIR`) with `chunks/chunk_NN.md` transcripts and prints its path.

## 3. Pick the moments (you do this)

Read `$S/references/picking.md` first, every time. Then for each run folder:

1. Read every `chunks/chunk_NN.md`, one at a time, in order.
2. For each chunk write `picks/chunk_NN.json` (same NN): a JSON array of moments as described in
   picking.md, or `[]` if nothing qualifies. Always write the file, even when empty: that's the progress record.
3. `status <run>` lists chunks that still have no picks file in `chunks_left`. Keep going until it's empty.
   It also lists `bad_picks` (invalid JSON, or entries missing `start` / `end` / `score`): fix them before
   rendering. Render skips a file it can't read and any single broken entry (it says which).

Several videos: give each one its own subagent (Agent tool, general-purpose) with the run folder path, the
path to `$S/references/picking.md`, and the instruction "read picking.md, then do step 3 of
$S/SKILL.md for this run folder". Up to 4 at once.

## 4. Make the clips

`render <run>` (defaults `--top 3 --min-score 7 --max-len 75 --layout auto --quality standard`). It ranks the picks, drops
overlaps, snaps to sentence edges, downloads (or cuts from the local file) only those minutes, chooses a
layout, burns in the hook + word-by-word captions, normalises loudness, and writes
`clips/clip_NN_<title>.mp4` + `.jpg` (cover image) + `.txt` (title, caption, hashtags, source +
timestamp) + `summary.json`. Temporary files are removed even if a clip fails. Re-rendering replaces the
previous files of the same clip number (also when its title changed), so there's nothing to delete first.
Captions and the hook stay inside the area TikTok / Reels / Shorts leave free of their own buttons and text.

Layouts (auto-detected per clip, from faces found across the clip):
- `facecam`: a small face inside a box with fixed edges (any position) over moving content (streams,
  screen shares) -> cam box on top, the rest of the frame below.
- `cam`: a person on camera with a static background (podcast, interview, vlog, talking head) -> 9:16
  crop centred on the main face.
- `full`: no steady face (screen recordings, gameplay with no cam, landscapes) -> whole frame centred over
  a blurred copy.

Force one for the whole run with `--layout cam|facecam|full`, e.g. `--layout full` for tutorials where
the screen matters more than the face. If fewer clips came out than asked because scores were low, say so
and offer `--min-score 6` rather than quietly lowering the bar. Pass the same `--cookies` if prep needed
them (they're remembered in `stream.json`).

Quality (`--quality`): how sharp the source is before it's cut to 1080x1920. Output size is always the same;
a bigger source mainly sharpens a small facecam. Use `standard` unless the user asks otherwise, and map
their words:

| user says | flag | source | cost per clip (measured, 68 s clip) |
|---|---|---|---|
| "small files", "low quality", "fast" | `--quality fast` | up to 720p | ~65 s, ~18 MB (barely faster, softer) |
| nothing / "normal" | `--quality standard` | up to 1080p | ~70 s, ~25 MB |
| "high quality", "sharper", "HD", "1440p" | `--quality high` | up to 1440p, sharper encode | ~90 s, ~50 MB |
| "max", "best", "4K" | `--quality max` | best available (4K if it exists) | slowest; same as `high` when there's no 4K |

If the user complains the facecam / streamer looks blurry, suggest `--quality high` and re-render. Local
files are always used at their own resolution; quality only changes the encode.

## 5. Check and report

Look at each clip's cover image `clips/clip_NN_<title>.jpg` (don't extract extra frames into the run
folder). If the framing is wrong (wrong face on top, speaker cut off, screen unreadable), add
`"layout": "full"` (or `"cam"` / `"facecam"`) to that pick in `picks/*.json` and re-run render.

Then report per video: length -> moments found -> clips kept, and for each clip its title, timestamp,
length, layout and file path. Open the folder with `open "<run>/clips"`. Remind the user to watch every
clip before posting and to only clip content they have the rights or permission to repost.

## Other requests

- "Make clip 2 longer / start earlier / new hook": edit that entry in the matching `picks/*.json` and
  re-run render (selection is deterministic, so the same picks come back with the change; the old version
  of the clip is replaced).
- "Give me 5 clips": `render <run> --top 5`. Longer clips: `--max-len 90`. Sharper: `--quality high`.
- Disk: prep deletes its audio after transcribing; render deletes downloaded sections (`--keep` keeps
  them). Delete old run folders only if the user says so.
