# Usage

[← Back to README](../README.md)

## Asking Claude

Just describe what you want. Claude runs the steps, picks the moments and tells you about each clip.

| you want | say something like |
|---|---|
| clip a link | `clip this video https://www.youtube.com/watch?v=...` |
| clip a file | `make shorts from ~/Movies/episode-12.mp4` |
| more or fewer clips | `give me 5 clips from <link>` |
| better picks | `clip <link>, it's a startup podcast and the guest is a VC` |
| another language | `clip this German interview: <link>` (needs `setup.sh --multilingual`) |
| find videos first | `find podcast episodes about sleep from this week and clip them` |
| several at once | `clip these three: <link> <link> <link>` |

Telling Claude what the video is about ("a cooking tutorial", "an Elden Ring stream") helps it pick better
moments.

## Changing a clip

After the clips are made, ask in the same chat:

- `make clip 2 longer` / `start clip 1 five seconds earlier`
- `give clip 3 a punchier hook`
- `clip 2 shows the wrong face, use the full frame`
- `lower the bar, I want more clips`

Claude edits the moment and renders that clip again. The new version **replaces** the old one, also when
the title (and so the file name) changed, so the clips folder only ever holds the current clips.

## Layouts

Each clip is framed automatically, based on what's on screen:

| layout | used for | looks like |
|---|---|---|
| **facecam** | streams and screen shares with a webcam box (anywhere on screen) | webcam on top, the game or screen below |
| **cam** | podcasts, interviews, vlogs, talking heads | vertical crop centred on the speaker |
| **full** | screen recordings, gameplay without a webcam, travel footage | the whole frame in the middle, over a blurred background |

If a clip is framed wrong, tell Claude which layout to use for it.

## Quality

Clips are always 1080×1920, but a sharper source makes a big difference when a small webcam box is
enlarged to fill the top half. Choose a level by asking, for example `clip <link> in high quality`, or
`make clip 1 sharper`:

| level | say | source video | speed |
|---|---|---|---|
| fast | "small files", "low quality" | up to 720p | about the same time, smaller and softer files |
| **standard** (default) | nothing | up to 1080p | normal |
| high | "high quality", "sharper", "1440p" | up to 1440p, sharper encode | ~25 % slower per clip, ~2× file size |
| max | "max", "best", "4K" | the best the video has (4K if available) | slowest on 4K videos. Same as high otherwise |

Measured on one 68-second clip from a 1440p stream: fast 66 s / 18 MB, standard 69 s / 25 MB, high
87 s / 48 MB. `high` gave the facecam about 2.7× more fine detail than `standard`. For local files, the
file's own resolution is always used; the level only changes the encode.

## Where your clips are

Each video gets its own folder in `~/Video-Clips/`:

```
~/Video-Clips/2026-11-23-my-podcast-1a2b3c4d5e/
├── clips/
│   ├── clip_01_he-got-fired-the-day-his-app-went-1.mp4   ← the clip
│   ├── clip_01_he-got-fired-the-day-his-app-went-1.jpg   ← cover image (thumbnail)
│   ├── clip_01_he-got-fired-the-day-his-app-went-1.txt   ← title, caption, hashtags to paste
│   └── summary.json
├── chunks/     the transcript, in 12-minute pieces (each ends with a short look at the next one)
├── picks/      the moments Claude chose (one file per piece)
└── manifest.json, transcript.json, signals.json
```

Example `.txt` file:

```
TITLE: He got fired the same morning his app hit number one

CAPTION:
Refreshing the charts while your boss walks in 😭 Would you have quit first?

#podcast #startup #entrepreneur #storytime

Source: My Podcast, https://www.youtube.com/watch?v=... at 00:41:12
Category: story  Score: 8.5  Layout: cam  Quality: standard (source 1920x1080)
Pick: c07-2  Whisper: medium.en  video-clipper 1.0.4
```

The last line says which moment it came from (`c07-2` = 2nd entry in `picks/chunk_07.json`), which speech model
timed the captions and which version made the clip. `manifest.json` in the run folder keeps the same facts
for the whole video: the source, the speech model, the settings, the timings and the last render.

Your original files are never modified. Temporary audio and video pieces are deleted automatically.

## Command reference

Claude runs these for you. You can also run them yourself:

```bash
VC=~/.claude/skills/video-clipper/scripts/vclip   # manual install; for the plugin, use the folder from /plugin

"$VC" prep ~/Movies/episode.mp4 --context "startup podcast"
#   prints the run folder, e.g. ~/Video-Clips/2026-11-23-episode-1a2b3c4d5e
#   then write picks/chunk_NN.json for every chunk (format: references/picking.md)
"$VC" status ~/Video-Clips/2026-11-23-episode-1a2b3c4d5e
"$VC" render ~/Video-Clips/2026-11-23-episode-1a2b3c4d5e
```

### `search QUERY`

Finds long YouTube videos to clip.

| option | default | |
|---|---|---|
| `--when` | `week` | `today`, `week`, `month` or `any` |
| `--limit` | `7` | how many results |
| `--min-minutes` | `20` | skip shorter videos |

### `prep SOURCE [SOURCE ...]`

Downloads the audio, transcribes it and splits the transcript into pieces. A source is a link or a file path.

| option | default | |
|---|---|---|
| `--context "..."` | | one line about the video, shown to Claude while picking |
| `--lang` | `en` | spoken language: `en`, `auto`, `de`, `es`, … (anything but `en` needs `--multilingual` setup) |
| `--name "..."` | channel or file name | creator or show name used in hooks and folder names |
| `--cookies` | | `chrome`, `safari`, `firefox` or a `cookies.txt` path, for age-restricted or login-only videos |
| `--jobs` | `2` | videos processed at once |
| `--chunk-min` | `12` | minutes of transcript per piece |
| `--force` | | redo a video that was already prepared |

### `status RUN`

Shows how many pieces have been picked and which are still left. It also warns about picks that are broken, start outside their piece, are older than their piece (prep was run again), or whose piece was edited after prep.

### `render RUN`

Makes the clips from the picked moments.

| option | default | |
|---|---|---|
| `--top` | `3` | number of clips |
| `--min-score` | `7` | quality bar from 0 to 10 (lower it to get more clips) |
| `--max-len` | `75` | longest clip in seconds |
| `--layout` | `auto` | `auto`, `facecam`, `cam` or `full` for every clip |
| `--quality` | `standard` | `fast` (720p), `standard` (1080p), `high` (1440p), `max` (best available, up to 4K). Also accepts `720p`, `1080p`, `1440p`, `4k` |
| `--cookies` | from prep | same as for prep |
| `--keep` | | keep the downloaded video pieces |

For the format of the moment files in `picks/`, see [`references/picking.md`](../references/picking.md).
