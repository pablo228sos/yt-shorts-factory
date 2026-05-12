#!/usr/bin/env bash
# One-shot installer for yt-shorts-factory on Linux / macOS.
# Run from inside the cloned repo:  ./scripts/install.sh
set -euo pipefail

skip_gameplay=0
skip_sfx=0
with_kokoro=0
for arg in "$@"; do
    case "$arg" in
        --skip-gameplay) skip_gameplay=1 ;;
        --skip-sfx) skip_sfx=1 ;;
        --with-kokoro) with_kokoro=1 ;;
        *) echo "Unknown flag: $arg" >&2; exit 1 ;;
    esac
done

step() { printf "\n>> %s\n" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------- ffmpeg ----------
if ! have ffmpeg; then
    if have apt-get; then
        step "Installing ffmpeg via apt-get"
        sudo apt-get update -y && sudo apt-get install -y ffmpeg
    elif have brew; then
        step "Installing ffmpeg via brew"
        brew install ffmpeg
    else
        echo "Install ffmpeg manually (no apt-get/brew detected)." >&2
        exit 1
    fi
fi

# ---------- Python ----------
PYTHON=""
for cand in python3.12 python3.11 python3; do
    if have "$cand"; then
        version=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        case "$version" in
            3.11|3.12|3.13) PYTHON="$cand"; break ;;
        esac
    fi
done
if [ -z "$PYTHON" ]; then
    echo "Need Python 3.11+ on PATH." >&2
    exit 1
fi
step "Using Python: $PYTHON ($($PYTHON --version))"

# ---------- venv ----------
if [ ! -d .venv ]; then
    step "Creating .venv"
    "$PYTHON" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ---------- pip install ----------
step "Installing package"
pip install --upgrade pip
pip install -e ".[dev]"

# ---------- pre-cache gameplay ----------
if [ "$skip_gameplay" -eq 0 ]; then
    step "Pre-downloading default gameplay sources (this can take a few minutes)"
    yt-shorts-factory download-gameplay
fi

# ---------- synthesize SFX library ----------
if [ "$skip_sfx" -eq 0 ]; then
    step "Synthesizing default SFX library (vine boom / ding / whoosh / suspense)"
    yt-shorts-factory synthesize-sfx
fi

# ---------- optional Kokoro TTS download ----------
if [ "$with_kokoro" -eq 1 ]; then
    step "Installing kokoro-onnx + soundfile"
    pip install kokoro-onnx soundfile
    step "Downloading Kokoro model (~310 MB, one-time)"
    yt-shorts-factory download-tts-models
fi

cat <<'EOF'

>> Done!
Activate the venv with:
    source .venv/bin/activate
Then try a generation:
    yt-shorts-factory generate-cmd --subreddit AmItheAsshole -v
EOF
if [ "$with_kokoro" -eq 0 ]; then
    printf "\nTo enable the high-quality local Kokoro TTS later:\n"
    printf "    ./scripts/install.sh --with-kokoro --skip-gameplay\n"
fi
