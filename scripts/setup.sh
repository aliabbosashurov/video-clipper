#!/usr/bin/env bash
# Video Clipper setup (macOS): checks what's needed, installs what it can, explains the rest,
# and says READY when everything works. Safe to re-run any time.
#
#   bash scripts/setup.sh                    English Whisper model (small.en, ~465 MB)
#   bash scripts/setup.sh --multilingual     also the multilingual model, for non-English videos
#   bash scripts/setup.sh --model base.en    pick another model: tiny(.en) base(.en) small(.en) medium(.en) large-v3-turbo
#
# Locations (all optional). Kept outside the skill folder so plugin updates don't wipe them:
#   VIDEO_CLIPPER_HOME    Python env, config.json             (default: ~/.video-clipper)
#   VIDEO_CLIPPER_MODELS  models + the caption font           (default: $VIDEO_CLIPPER_HOME/models)
#   VIDEO_CLIPS_DIR       where runs and clips are written     (default: ~/Video-Clips)
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${VIDEO_CLIPPER_HOME:-$HOME/.video-clipper}"
VENV="$DATA/venv"
MODELS="${VIDEO_CLIPPER_MODELS:-$DATA/models}"
CLIPS_DIR="${VIDEO_CLIPS_DIR:-$HOME/Video-Clips}"
MODEL="small.en"; MULTI=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="${2:-}"; shift 2 ;;
    --multilingual) MULTI=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)"; exit 2 ;;
  esac
done
case "$MODEL" in
  tiny|tiny.en|base|base.en|small|small.en|medium|medium.en|large-v3|large-v3-turbo) ;;
  *) echo "Unknown Whisper model '$MODEL'. Use one of: tiny tiny.en base base.en small small.en medium medium.en large-v3 large-v3-turbo"; exit 2 ;;
esac

ok()   { printf "  [ok]      %s\n" "$1"; }
inst() { printf "  [install] %s\n" "$1"; }
warn() { printf "  [warn]    %s\n" "$1"; }
fail() { printf "  [MISSING] %s\n" "$1"; FAILED=1; }
FAILED=0
HF="https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

echo "Video Clipper setup"
if [[ "$(uname)" != "Darwin" ]]; then echo "This skill supports macOS only."; exit 1; fi
mkdir -p "$DATA" "$MODELS/fonts" || { echo "Can't create $DATA / $MODELS"; exit 1; }
echo "  [info]    Data folder: $DATA (Python env, models, config)"

# 1. Homebrew is used to install missing tools when it's there, but isn't required
HAVE_BREW=0; command -v brew >/dev/null 2>&1 && HAVE_BREW=1
[[ $HAVE_BREW -eq 1 ]] && ok "Homebrew (used to install anything missing)" \
  || warn "Homebrew not found: missing tools will be listed with install hints instead (https://brew.sh)"

need_tool() {  # need_tool <binary> <brew formula> <hint when there's no brew>
  if command -v "$1" >/dev/null 2>&1; then ok "$1 ($(command -v "$1"))"; return; fi
  if [[ $HAVE_BREW -eq 1 ]]; then
    inst "$2"; brew install "$2" >/dev/null 2>&1 && command -v "$1" >/dev/null 2>&1 && { ok "$1"; return; }
  fi
  fail "$1: $3"
}

# 2. Command-line tools
need_tool ffmpeg      ffmpeg      "brew install ffmpeg, or a static build from https://evermeet.cx/ffmpeg/ (ffmpeg + ffprobe on your PATH)"
need_tool ffprobe     ffmpeg      "comes with ffmpeg"
need_tool whisper-cli whisper-cpp "brew install whisper-cpp, or build https://github.com/ggml-org/whisper.cpp and put build/bin/whisper-cli on your PATH"
if command -v ffmpeg >/dev/null 2>&1 && ! ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264; then
  fail "ffmpeg was built without libx264 (needed to encode clips): install the Homebrew or evermeet.cx build"
fi
if command -v deno >/dev/null 2>&1; then ok "deno (YouTube downloads)"
elif [[ $HAVE_BREW -eq 1 ]]; then inst "deno"; brew install deno >/dev/null 2>&1 && ok "deno" || warn "deno: YouTube links may fail (local files are fine). brew install deno"
else warn "deno not found: YouTube links may fail (local files and most other sites are fine). Install: https://deno.com"; fi

# 3. Python environment inside the skill folder (uv if present, else any python3 >= 3.9)
PY_OK=0
if [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>/dev/null; then PY_OK=1; fi
if [[ $PY_OK -eq 0 ]]; then
  rm -rf "$VENV"
  UV="$(command -v uv || { [[ -x "$HOME/.local/bin/uv" ]] && echo "$HOME/.local/bin/uv"; })"
  if [[ -n "$UV" ]]; then
    inst "Python 3.12 environment (uv)"; "$UV" venv -q --python 3.12 "$VENV" >/dev/null 2>&1
  fi
  if [[ ! -x "$VENV/bin/python" ]] && command -v python3 >/dev/null 2>&1 \
     && python3 -c "import sys; sys.exit(sys.version_info < (3, 9))" 2>/dev/null; then
    inst "Python environment ($(python3 --version))"; python3 -m venv "$VENV" >/dev/null 2>&1
  fi
fi
if [[ -x "$VENV/bin/python" ]]; then
  ok "Python environment: $VENV ($("$VENV/bin/python" --version 2>&1))"
  if [[ -n "$(command -v uv || true)" || -x "$HOME/.local/bin/uv" ]]; then
    "$(command -v uv || echo "$HOME/.local/bin/uv")" pip install --python "$VENV/bin/python" -q -U -r "$SKILL_DIR/requirements.txt" >/dev/null 2>&1
  else
    "$VENV/bin/python" -m pip install -q -U pip >/dev/null 2>&1
    "$VENV/bin/python" -m pip install -q -U -r "$SKILL_DIR/requirements.txt" >/dev/null 2>&1
  fi
  "$VENV/bin/python" -c "import yt_dlp, cv2, PIL, numpy" 2>/dev/null \
    && ok "Python packages (yt-dlp, opencv, pillow, numpy)" || fail "Python packages: $VENV/bin/python -m pip install -r requirements.txt"
else
  fail "Python 3.9+: install from https://www.python.org/downloads/macos/ (or 'xcode-select --install', or uv: https://docs.astral.sh/uv/)"
fi

# 4. Whisper model(s): speech -> text on this Mac. Reuses ~/.cache/whisper-cpp if a copy is already there.
get_model() {  # prints the path of ggml-<name>.bin, downloading it into $MODELS if needed
  local f="ggml-$1.bin"
  for d in "$MODELS" "$HOME/.cache/whisper-cpp"; do [[ -s "$d/$f" ]] && { echo "$d/$f"; return 0; }; done
  printf "  [install] Whisper %s model into %s\n" "$1" "$MODELS" >&2
  curl -fL --retry 3 -s -o "$MODELS/$f.part" "$HF/$f" && mv "$MODELS/$f.part" "$MODELS/$f" && echo "$MODELS/$f" && return 0
  rm -f "$MODELS/$f.part"; return 1
}
WHISPER_EN=""; WHISPER_MULTI=""
if P="$(get_model "$MODEL")"; then
  ok "Whisper model: $P"
  [[ "$MODEL" == *.en ]] && WHISPER_EN="$P" || WHISPER_MULTI="$P"
else fail "Whisper $MODEL model (download from $HF/ggml-$MODEL.bin into $MODELS)"; fi
if [[ $MULTI -eq 1 && -z "$WHISPER_MULTI" ]]; then
  if P="$(get_model "${MODEL%.en}")"; then ok "Whisper multilingual model: $P"; WHISPER_MULTI="$P"
  else fail "Whisper ${MODEL%.en} model"; fi
fi
[[ -z "$WHISPER_MULTI" ]] && echo "  [info]    English only. For other languages re-run with --multilingual"

# 5. Face detector (YuNet, ~230 KB): finds the facecam box / the speaker
YUNET="$MODELS/face_detection_yunet_2023mar.onnx"
if [[ ! -s "$YUNET" ]]; then
  inst "YuNet face detector"
  curl -fL --retry 3 -s -o "$YUNET" https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx || rm -f "$YUNET"
fi
[[ -s "$YUNET" ]] && ok "Face detector" || warn "Face detector download failed: falls back to OpenCV's built-in detector (less accurate)"

# 6. Caption font: Anton (SIL Open Font License) downloaded into the models folder; macOS fonts as fallback
FONT="$MODELS/fonts/Anton-Regular.ttf"
if [[ ! -s "$FONT" ]]; then
  inst "Anton caption font"
  curl -fL --retry 3 -s -o "$FONT" https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf || rm -f "$FONT"
fi
if [[ -s "$FONT" ]]; then ok "Caption font: Anton"
elif [[ -f "/System/Library/Fonts/Supplemental/Arial Black.ttf" ]]; then FONT=""; ok "Caption font: Arial Black (system)"
else FONT=""; warn "No bold caption font found: using Pillow's built-in font. Set VIDEO_CLIPPER_FONT=/path/to/font.ttf for a better look"; fi

# 7. Disk space: audio-only download keeps runs small, but warn early
mkdir -p "$CLIPS_DIR" 2>/dev/null
FREE_GB=$(df -g "$CLIPS_DIR" 2>/dev/null | awk 'NR==2{print $4}')
if [[ -n "$FREE_GB" ]] && (( FREE_GB < 3 )); then warn "Only ${FREE_GB} GB free at $CLIPS_DIR. Each video needs ~0.5-1 GB while it runs."
else ok "Clips folder: $CLIPS_DIR (${FREE_GB:-?} GB free)"; fi

if [[ -x "$VENV/bin/python" ]]; then
  WE="$WHISPER_EN" WM="$WHISPER_MULTI" YU="$YUNET" FO="$FONT" CD="$CLIPS_DIR" "$VENV/bin/python" - "$DATA/config.json" <<'EOF'
import json, os, sys
yunet = os.environ["YU"]
cfg = {"whisper_model": os.environ["WE"], "whisper_model_multi": os.environ["WM"],
       "yunet_model": yunet if os.path.isfile(yunet) and os.path.getsize(yunet) else "",
       "font": os.environ["FO"], "clips_dir": os.environ["CD"]}
open(sys.argv[1], "w").write(json.dumps(cfg, indent=1) + "\n")
EOF
fi

if [[ $FAILED -eq 0 ]]; then
  date > "$DATA/.ready"
  echo; echo "READY. In Claude Code say: clip this video <link or file path>"
else
  rm -f "$DATA/.ready"; echo; echo "NOT READY: fix the [MISSING] items above and re-run: bash \"$SKILL_DIR/scripts/setup.sh\""; exit 1
fi
