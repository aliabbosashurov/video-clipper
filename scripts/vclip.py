#!/usr/bin/env python3
"""Video Clipper command line. Run it through the wrapper (scripts/vclip), which uses the venv made by setup.sh.

  search QUERY        find long YouTube videos / stream replays to clip
  prep SRC [SRC...]   steps 1+2: audio only, local transcript, loud moments, chat spikes, chunks for the picker
  status RUN          show what a run has and what's left
  render RUN          step 4: the best picks -> vertical clips with hook, captions, cover and post text

Step 3 (picking) is done by the Claude Code session itself (no API keys); see SKILL.md.
The code lives in the videoclipper package next to this file; videoclipper/__init__.py maps it out.
"""
from videoclipper.cli import main

if __name__ == "__main__":
    main()
