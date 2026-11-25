# Troubleshooting

[← Back to README](../README.md)

## Setup

| problem | fix |
|---|---|
| `Not set up yet` | Say *"set up the video clipper"* in Claude Code (or run `scripts/setup.sh`) and wait for `READY`. |
| Setup shows `[MISSING]` items | Install each listed item (the line says how), then run setup again. Without Homebrew, see [Installing without Homebrew](installation.md#installing-without-homebrew). |
| Claude doesn't know the skill | Plugin: check `claude plugin list` shows `video-clipper` as enabled. Plain skill: check the folder is at `~/.claude/skills/video-clipper` with `SKILL.md` inside. Then restart Claude Code. |
| Setup ended with `[MISSING]` and now every command says `Not set up yet` | A setup that doesn't finish removes the READY mark. Install the missing item and run setup again, with the same `--model` you use: a plain run resets the English model to `small.en`. |
| Setup runs again after every plugin update | It shouldn't need to download anything: models are kept in `~/.video-clipper`. If you moved them, set `VIDEO_CLIPPER_HOME` to the new folder. |
| Captions use a plain font | The font download failed. Run setup again, or set `VIDEO_CLIPPER_FONT` to a `.ttf` file. |

## Downloads

Most download errors end with a **`Hint:` line** that says what to do: sign in with your browser's
cookies, the video is private, blocked in your region, members-only, or removed. Claude follows the hint or
tells you in plain words.

| problem | fix |
|---|---|
| Private, members-only, region-blocked or removed video | The `Hint:` line says which. Private and removed videos can't be clipped. Members-only works with `--cookies <browser>` when you're logged in as a member. |
| "Sign in to confirm you're not a bot", age-restricted video, or error 403 | Log in to the site in your browser, then ask Claude to retry with your browser's cookies (`--cookies chrome`, `safari` or `firefox`). |
| YouTube downloads suddenly fail | Run setup again (it updates the downloader) and make sure `deno` is installed. |
| "still live on YouTube" | Wait until the stream has ended and the replay is available, then try again. |

## Transcripts and clips

| problem | fix |
|---|---|
| "needs a multilingual Whisper model" | Run setup with `--multilingual`. |
| Prep says `already prepped ... other settings` | That video was prepped with another speech model, language or chunk size (the message lists which). Nothing was redone. Add `--force` to prep it again; chunk numbers can change, so its `picks/` would need redoing. |
| `status` lists a pick under `bad_picks` as "outside chunk N" | A moment belongs to the chunk where it starts, and the pick's `start` is outside that chunk's time range (usually a timestamp copied from another chunk). Render skips it; ask Claude to fix the entry or move it to the right `picks/chunk_NN.json`. |
| `status` lists `stale_picks` or `changed_chunks` | The chunk text was rewritten (prep run again with `--force`) or edited after the picks were made. Ask Claude to pick those chunks again. |
| `render` or `status` says "has not been prepped" | The folder has no finished `manifest.json`: run `prep` for the video. |
| A line in a chunk is marked `LOW-CONF` | Whisper was unsure of those words (lyrics, crosstalk, game or music noise). Claude is told not to pick a moment because of such lines. |
| The transcript is gibberish | The language is wrong. Tell Claude the video's language, or ask it to detect it (`--lang auto --force`). |
| A clip starts with a black screen for a few seconds, and its captions run ahead of the speech | Fixed in 1.0.3: render now checks that the picture starts on the first frame and cuts the caption audio at the exact time. Clips made with an older version can have both problems (mostly at `high` / `max` quality): ask Claude to render them again. |
| Wrong face on top, or speaker cut off | Tell Claude which layout to use for that clip (`full`, `cam` or `facecam`). The streamer is the biggest face that moves; a game with a big moving character face can still fool it. |
| A moment Claude chose is missing from the clips | One of its pick entries was broken (for example no `end`). Render now skips only that entry and logs `skipped chunk_NN.json entry N`; ask Claude to fix it and render again. |
| Fewer clips than asked for | Not enough moments passed the quality bar. Ask for more anyway (`--min-score 6`), or the video may not have more good moments. |
| The streamer's camera looks blurry | The webcam box is small in the original and gets enlarged. Ask for `high quality` (or `max` for 4K videos) and re-render. |
| Rendering is slow | You may be on `high` or `max` quality. `standard` or `fast` render quicker. |
| Transcribing is slow | Use a smaller model (`setup.sh --model base.en`) and process one video at a time (`--jobs 1`). |
| Disk is filling up | Old run folders stay in `~/Video-Clips/`. Delete the ones you've finished with. |

## Known limits

- Each clip gets one layout. A clip that switches between very different scenes partway through may need
  its layout set by hand.
- The `cam` crop is fixed for the whole clip. It doesn't follow a speaker who walks across the frame.
- Chat spikes are only detected for YouTube replays with live chat.
- macOS only.

## Still stuck?

[Open an issue](https://github.com/aliabbosashurov/video-clipper/issues) with the command you ran and the
error message.
