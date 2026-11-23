# Video Clipper

Turn long videos into ready-to-post vertical clips with one sentence in Claude Code.

![macOS](https://img.shields.io/badge/platform-macOS-lightgrey) ![Claude Code skill](https://img.shields.io/badge/Claude%20Code-skill-orange) ![License: MIT](https://img.shields.io/badge/license-MIT-blue)

```
You:     clip this podcast https://www.youtube.com/watch?v=...
Claude:  Done. 3 clips from the 1 h 42 min episode:
           1. "He got fired the day his app went #1"   (00:41:12, 46 s)
           2. "Why your brain cleans itself at night"  (01:05:30, 38 s)
           3. "The investor who said no to Uber"       (01:28:04, 52 s)
         Saved to ~/Video-Clips/.../clips
```

Give it a podcast, interview, stream, tutorial or vlog, as a link or a file on your Mac. It finds the best
moments and turns them into short clips for TikTok, YouTube Shorts and Instagram Reels.

## What you get

For every video, 3 clips (or as many as you ask for), each with:

- **Vertical 9:16 video** (1080×1920), framed automatically: facecam on top for streams, a crop on the
  speaker for podcasts, or the full frame for screen recordings
- **A hook title** on screen that makes people stop scrolling
- **Word-by-word captions** that highlight each word as it's spoken
- **Even, platform-ready loudness**
- **A ready-to-paste post**: title, caption and hashtags in a text file next to the clip

## How it works

1. **Listen.** It downloads only the audio (or reads your file) and transcribes it on your Mac.
2. **Pick.** Claude reads the transcript and picks the moments worth sharing: stories, insights, hot
   takes, funny bits and reactions.
3. **Cut.** It downloads only those few minutes of video and renders the clips.

Transcription and rendering run on your Mac. You don't need an API key: the picking happens inside your own
Claude Code session.

## Requirements

- A Mac (Apple Silicon recommended), 8 GB of memory or more
- About 1 GB of free disk space
- [Claude Code](https://claude.com/claude-code)
- [Homebrew](https://brew.sh) is recommended, so setup can install everything for you

See [Installation](docs/installation.md) for full details.

## Installation

**1. Download the skill** into your Claude Code skills folder:

```bash
git clone https://github.com/aliabbosashurov/video-clipper.git ~/.claude/skills/video-clipper
```

**2. Run setup.** It installs what's missing and downloads the speech model (~465 MB):

```bash
bash ~/.claude/skills/video-clipper/scripts/setup.sh
```

Wait for `READY`. For videos that aren't in English, add `--multilingual`.

**3. Restart Claude Code.** That's it.

## Usage

Open Claude Code and ask in plain words:

```
clip this video https://www.youtube.com/watch?v=...
make 5 shorts from ~/Movies/episode-12.mp4, it's a startup podcast
turn yesterday's Twitch stream into clips: https://www.twitch.tv/videos/...
find podcast episodes about sleep from this week and clip them
```

Then fine-tune in the same chat:

```
make clip 2 start a bit earlier
give clip 1 a different hook
clip 3 cuts off the speaker, show the full frame instead
```

Your clips are saved in `~/Video-Clips/`, and Claude opens the folder when it's done.

More examples and options: [Usage guide](docs/usage.md).

## FAQ

**Do I need an API key or a paid service?**
No. Downloading, transcribing and rendering are free, open-source tools on your Mac. The picking runs on
your existing Claude Code plan.

**Which sites are supported?**
YouTube, Twitch, Kick, Vimeo and the [many other sites yt-dlp supports](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md),
plus any video file on your Mac.

**Will it change my original video?**
No. Local files are only read, never modified, moved or deleted.

**Does it work in other languages?**
Yes. Run setup with `--multilingual`, then tell Claude the language ("clip this Spanish interview").

**Does it run on Windows or Linux?**
Not at the moment. It's macOS only.

Something not working? See [Troubleshooting](docs/troubleshooting.md).

## Documentation

- [Installation](docs/installation.md): requirements, setup options, installing without Homebrew, configuration, updating
- [Usage](docs/usage.md): example requests, editing clips, layouts, output files, command reference
- [Troubleshooting](docs/troubleshooting.md): common problems and fixes, known limits

## Responsible use

Only clip videos you own or have permission to repost, and watch every clip before you post it.

## License

[MIT](LICENSE). Built on [yt-dlp](https://github.com/yt-dlp/yt-dlp), [whisper.cpp](https://github.com/ggml-org/whisper.cpp),
[FFmpeg](https://ffmpeg.org), [OpenCV](https://opencv.org) and the [Anton](https://fonts.google.com/specimen/Anton) font (SIL Open Font License).
