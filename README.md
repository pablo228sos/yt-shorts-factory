# yt-shorts-factory

Fully-automated YouTube Shorts factory. Pulls a top story from Reddit
(e.g. `r/AmItheAsshole`), narrates it with Microsoft Edge's neural TTS,
re-transcribes the narration with `faster-whisper` for word-perfect
caption timing, generates TikTok-style "pop word" subtitles, lays it
over Minecraft Parkour / Subway Surfers B-roll, and renders a 1080×1920
mp4 — all in one CLI command.

No paid APIs. No OAuth. Just `pip install` and a few mp4s.

## Pipeline

```
Reddit JSON → text cleaner → Edge TTS → faster-whisper word timings
            → .ass subtitles → ffmpeg compose → out/<id>_<slug>.mp4
```

| Stage | Module | Default |
|---|---|---|
| Story source | `sources/reddit.py` | `r/AmItheAsshole`, top of day |
| Text cleaner | `script/cleaner.py` | Strips URLs/edits, expands AITA jargon, censors profanity |
| TTS | `tts/edge.py` | `en-US-GuyNeural` via `edge-tts` (free) |
| Transcription | `transcribe/whisper.py` | `faster-whisper` base model, int8 CPU |
| Subtitles | `render/subtitles.py` | Karaoke-style .ass, 3 words/chunk, yellow highlight |
| B-roll | `assets/gameplay.py` | Auto-download Minecraft Parkour / Subway Surfers via `yt-dlp`, slice random 90 s segments |
| Composer | `render/composer.py` | ffmpeg, 1080×1920 @ 30 fps, audio ducking |

## Install

### Windows (one-shot)

From the default Windows Command Prompt (`cmd.exe`):

```cmd
git clone https://github.com/pablo228sos/yt-shorts-factory.git
cd yt-shorts-factory
scripts\install.bat
```

`install.bat` is a thin wrapper that hands off to `install.ps1` with the
right execution policy, so you do not need to switch to PowerShell or run
`Set-ExecutionPolicy` yourself. The installer pulls `ffmpeg` and Python
3.12 via `winget`, sets up `.venv`, installs the package, and
pre-downloads the default gameplay sources. Pass `-SkipGameplayDownload`
to skip the last step.

If you are already in PowerShell you can call the script directly:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install.ps1
```

### Linux / macOS

```bash
git clone https://github.com/pablo228sos/yt-shorts-factory.git
cd yt-shorts-factory
./scripts/install.sh
```

### Manual

```bash
pip install -e ".[dev]"
# Linux:  sudo apt-get install -y ffmpeg
# macOS:  brew install ffmpeg
# Windows: winget install --id Gyan.FFmpeg -e
yt-shorts-factory download-gameplay   # populate cache/gameplay/sources/
```

**Python 3.11 or 3.12 is required** — `faster-whisper` does not yet ship
wheels for Python 3.14. If `py -3.12 --version` errors, install it from
https://www.python.org/downloads/ or via `winget install Python.Python.3.12`.

You can also drop your own `.mp4` into `cache/gameplay/sources/` (or the
legacy top-level `cache/gameplay/`) and skip the auto-download entirely.
The pipeline always prefers local files.

**If YouTube blocks `yt-dlp`** with "Sign in to confirm you're not a bot"
(common on cloud / VPN IPs), point yt-dlp at your logged-in browser:

```json
{ "gameplay": { "cookies_from_browser": "firefox" } }
```

or pre-export cookies and configure manually — see
https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp.

## Run

```bash
# Hands-off: pulls gameplay automatically if cache is empty.
yt-shorts-factory generate-cmd --subreddit AmItheAsshole --time-filter day

# Or pin a specific gameplay file.
yt-shorts-factory generate-cmd \
  --subreddit AmItheAsshole \
  --gameplay cache/gameplay/sources/parkour.mp4 \
  --output-dir out
```

```bash
# Just see which stories pass the filters
yt-shorts-factory list-stories --subreddit AmItheAsshole --limit 10
```

Outputs land in `out/<post_id>_<slugified-title>.mp4` plus an intermediate
work directory under `cache/work/`.

## Custom config

Pass `--config config.json` with anything you want to override. Example:

```json
{
  "reddit":    { "subreddit": "EntitledParents", "min_chars": 800 },
  "tts":       { "voice": "en-US-JennyNeural", "rate": "+12%" },
  "subtitles": { "max_words_per_chunk": 2, "vertical_position": 0.5 },
  "gameplay":  { "local_files": ["cache/gameplay/parkour.mp4"] }
}
```

## Tests

```bash
ruff check .
mypy
pytest
```

CI runs all three on every push (`.github/workflows/ci.yml`).

## YouTube monetization notes

YouTube's 2025 "inauthentic / mass-produced" policy demonetizes channels
that publish AI-generated content with no transformative human input.
**Treat this tool as a draft generator, not an auto-uploader.** Before
publishing:

- Review and edit the script per video (10–15 seconds of work).
- Add a unique hook in the first 1.5 seconds.
- Vary voices, B-roll, and aspect framing.
- Don't run multiple channels off the same exact pipeline.

A future `upload` module is intentionally not included yet.
