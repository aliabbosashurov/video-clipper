"""Video Clipper: any long video (link or local file) -> ready-to-post vertical clips.

The pipeline, and the module that owns each step:

    prep    sources -> signals + transcribe -> chunks       (prep.py)
    pick    done by the Claude Code session, see SKILL.md   (picks.py reads the result)
    render  picks -> sources (section) -> layout + captions -> encode -> post   (render.py)

Modules, by responsibility:

    config      paths, settings, quality levels (everything else imports from here)
    util        logging, running commands, time / name formatting
    media       asking ffprobe about a file
    sources     links and local files: metadata, audio + section downloads, error hints
    signals     loud moments in the audio, live-chat spikes
    transcribe  Whisper, transcript cleanup, word timings for captions
    chunks      transcript pieces with markers, for the picker
    manifest    manifest.json: what a run folder is, how it was made, with which model and version
    picks       reading, checking and ranking the picker's moments
    layout      facecam / cam / full detection (the person is tracked over the clip) and the ffmpeg framing for each
    captions    hook box + word-by-word caption overlay (inside the platform safe zone)
    post        the post text next to each clip (title, caption, hashtags)
    prep        command: steps 1 + 2
    render      command: step 4
    search      command: find long videos on YouTube
    status      command: progress of a run
    cli         command-line options -> the commands above
"""
