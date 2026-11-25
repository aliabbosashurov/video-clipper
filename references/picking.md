# Picking moments (step 3)

You're the editor of a clipping page with millions of followers. You're reading one chunk (12 minutes by
default) of a long video's transcript: a podcast, interview, talk, gaming or IRL stream, tutorial, screen
recording, vlog. Find the moments people actually SHARE, score them, and be harsh.

## What a chunk looks like

```
# The Example Show: Episode 212 with Dr. Jane Doe
Chunk 4/11  (00:36:00 to 00:48:00)
Context: science podcast, guest is a sleep researcher
Markers: LOUD(+dB over normal) = speaker got loud. CHAT xN = chat moving N times faster than normal. LOW-CONF = ...

[00:36:02] So I got fired the same morning the app hit number one.   <<LOUD(+11dB)>>
[00:36:06] My manager walks in, I'm refreshing the charts...
   ... (the rest of the 12 minutes) ...
[00:47:41] And that's the moment I knew the company was done.
(end of this chunk. The lines below are the start of the next chunk, for context only: a moment that started above may run into them, but never start a moment below)
[00:48:02] Nobody said a word for a full minute.
[00:48:30] Then the CFO stood up and left.
```

- `[HH:MM:SS]` is where that line starts in the ORIGINAL video. Always use these timestamps.
- **A moment belongs to the chunk where it STARTS.** Every chunk except the last ends with about 90
  seconds of the next chunk, below the `(end of this chunk...)` line. It is only there so you can see how a
  moment that starts near the end finishes. Never start a moment in that part: the next chunk reads it as
  its own. `status` reports a pick whose `start` is outside its chunk, and render skips it.
- Silence and music markers (`[BLANK_AUDIO]`, `[MUSIC]`, `♪♪`) are already removed. Reaction tags like
  `[laughs]`, `(screaming)` or `(applause)` are kept: they're good signals.
- `Context:` (if present) is what the user told you about the video and audience. Use it to judge what matters.
- `<<LOUD(+NdB)>>`: the speaker got N dB louder than the surrounding 3 minutes (yelling, laughing, arguing).
- `<<CHAT xN>>`: live chat (YouTube replays) moved N times faster than normal. Chat reacts a few seconds
  late, so the moment is usually just BEFORE the marker.
- `<<LOW-CONF>>`: Whisper was unsure of the words on that line (song lyrics, crosstalk, game or music noise
  over the voice). The text may be wrong or invented. Never pick a moment because of such a line, and be
  careful with a moment that mostly consists of them. A single low-confidence word inside good speech is fine.

Signals help, they don't decide. A loud line with nothing interesting said is not a clip. A great line with
no marker can be. Calm formats (podcasts, tutorials) have few markers: judge the words.

## What to look for

| category | what it looks like |
|---|---|
| `insight` | a clear, surprising idea or lesson that stands on its own ("the reason most diets fail is...") |
| `story` | a short story with a setup and a payoff: a near-miss, a crazy thing that happened, a turning point |
| `hot_take` | a strong opinion people will argue about in the comments |
| `funny` | a joke, a bit, a roast, a comeback that lands without setup |
| `emotional` | vulnerable, raw, moving: someone opening up, getting choked up, a big admission |
| `reaction` | first-time reactions, disbelief, freakouts, someone losing it (streams, gaming, IRL) |
| `quotable` | one or two sentences people would screenshot, stitch or quote |
| `howto` | a tip or trick that's complete in under a minute (tutorials, screen recordings) |
| `fail` | things going wrong on camera: mistakes, gaffes, deaths in a game, plans falling apart |

## Throw out (score 0, don't include)

- Anything that needs context to make sense: references to earlier ("like I said", "going back to your
  point", "that thing from before"), inside jokes, half of an argument.
- Starts with filler ("uh so yeah", "anyway", "okay so", "um", "that's a great question"). Move the start to
  the first real sentence. If there isn't one, drop it.
- Intros, outros, sponsor reads, ads, "like and subscribe", reading chat / donations, dead air, loading or
  waiting screens, "can you hear me?".
- Whisper junk that slipped through: "Thank you." over and over, text that obviously doesn't match the video.
- Anything hateful, sexual, or about real people's private lives; medical, legal or financial advice that
  could hurt someone once it's cut out of context.

## Scoring (0-10, harsh)

- 9-10: anyone scrolling would stop and share it. Instant payoff, no context needed, strong emotion or idea.
- 7-8: solid clip, clear hook in the first 3 seconds, lands on its own. (Render keeps 7+ by default.)
- 5-6: fine, but nobody shares it. Include only if the chunk has nothing better.
- below 5: don't include.

Most chunks have 0-2 real candidates. Many have none. That's normal.

## Boundaries and timestamps

- Length 20-60 seconds; stories and insights may run to 75 if the payoff needs it. Render cuts anything
  longer than `--max-len` (75 s) and skips anything under 12 s.
- `start` = the timestamp of the line that IS the hook (the first line must grab), not the build-up 30
  seconds earlier.
- `end` = the timestamp of the first line AFTER the payoff (the punchline, the point lands, the reaction
  peaks). Don't trail off. Render snaps both ends to sentence edges.
- A moment that starts in this chunk may end in the lookahead below it: use the real end there. If it still
  isn't finished at the last line you can see, it's too long to be a clip: pick a shorter part or drop it.
  Don't pick the same moment again in the next chunk.
- One broken entry (say, a missing `end`) is skipped on its own; the other moments in the file still count.
- Timestamps are strings `"HH:MM:SS"` (plain seconds as numbers also work). `end` must be after `start`.

## Output: `picks/chunk_NN.json`

One file per chunk, same number as the chunk (`chunks/chunk_04.md` -> `picks/chunk_04.json`). It's a JSON
array, valid JSON only (no comments, no trailing commas).

**Nothing worth clipping? Still write the file, containing exactly `[]`.** The file existing is how
progress is tracked (`status` lists chunks with no picks file as not done yet).

```json
[
  {
    "start": "00:41:12",
    "end": "00:41:58",
    "category": "story",
    "score": 8.5,
    "hook": "HE GOT FIRED THE DAY HIS APP WENT #1",
    "title": "He got fired the same morning his app hit number one",
    "caption": "Imagine refreshing the charts while HR walks in 😭 Would you have quit first?",
    "hashtags": ["#podcast", "#startup", "#entrepreneur", "#storytime"],
    "why": "setup + payoff in 45s, no context needed, host cracks up at the end"
  }
]
```

| field | required | rules |
|---|---|---|
| `start`, `end` | yes | from the chunk's `[HH:MM:SS]` lines, see above |
| `category` | yes | one of the categories in the table |
| `score` | yes | number 0-10, harsh |
| `hook` | yes | on-screen title burned into the clip. Max ~8 words, names the person or subject, says what's happening, makes you need to see it |
| `title` | yes | post title (Shorts / TikTok / Reels), sentence case, under 70 characters. Also names the file |
| `caption` | yes | 1-2 short lines + a question that gets comments. No links |
| `hashtags` | yes | 4-6: the topic, the show / creator tag when known, the format (#podcast, #twitch, #tutorial) |
| `why` | yes | one line: why it works. Helps the user (and you) review |
| `layout` | no | `"facecam"`, `"cam"` or `"full"` to force this clip's framing. Only set it after a render came out wrong |

Write `hook`, `title` and `caption` in the video's language unless the user asked for another one.

### More examples

Gaming stream, a reaction:

```json
[
  {
    "start": "02:14:03",
    "end": "02:14:31",
    "category": "reaction",
    "score": 9,
    "hook": "SHE FINALLY BEATS THE BOSS AFTER 6 HOURS",
    "title": "Six hours of tries and she finally beats the final boss",
    "caption": "The scream at the end 😭 How long did it take you?",
    "hashtags": ["#gaming", "#eldenring", "#twitch", "#streamer"],
    "why": "huge payoff, LOUD +14dB, chat x6, no context needed"
  }
]
```

Tutorial / screen recording, a tip:

```json
[
  {
    "start": "00:07:40",
    "end": "00:08:22",
    "category": "howto",
    "score": 7.5,
    "hook": "THE EXCEL SHORTCUT NOBODY TELLS YOU ABOUT",
    "title": "This one Excel shortcut saves hours every week",
    "caption": "Ctrl + E does WHAT? 🤯 Which shortcut should be next?",
    "hashtags": ["#excel", "#exceltips", "#productivity", "#tutorial"],
    "why": "complete tip in 40s, shows before/after, nothing earlier needed"
  }
]
```

A chunk with only an intro and a sponsor read:

```json
[]
```
