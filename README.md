# yt-shorts-factory

Fully-automated YouTube Shorts factory. Pulls a top story from Reddit
(e.g. `r/AmItheAsshole`), rewrites the title into a retention hook,
narrates it with Microsoft Edge's neural TTS (or local Kokoro-82M),
re-transcribes the narration with `faster-whisper` for word-perfect
caption timing, renders TikTok-style "pop word" subtitles (1-3 words,
Bebas Neue, ALL CAPS, yellow highlight), lays the whole thing over
Minecraft Parkour / Subway Surfers B-roll at 1080p source (sharp, not
upscaled), mixes in vine-boom / ding / whoosh SFX placed by the script
content, optionally ducks a music bed under the voice, and renders a
1080×1920 mp4 — all in one CLI command.

No paid APIs. No OAuth. Just `pip install` and a few mp4s.

## Docs

| File | What's in it |
|---|---|
| [CAPABILITIES.md](CAPABILITIES.md) | Full feature list — what every module does today |
| [ROADMAP.md](ROADMAP.md) | What's shipped, in progress, and planned (split by stage) |
| [RESEARCH.md](RESEARCH.md) | Design rationale — why each default exists (hook, voice, captions, ASMR strip, etc.) |
| [LICENSE](LICENSE) | MIT |

## Pipeline

```
Reddit JSON ─► text cleaner ─► hook rewriter ─► niche profile ─► TTS
            ─► faster-whisper word timings (rescaled for atempo)
            ─► SFX placer (?, !, scene markers)
            ─► .ass subtitles ─► ffmpeg compose ─► out/<id>_<slug>.mp4
```

See [CAPABILITIES.md §Pipeline diagram](CAPABILITIES.md#pipeline-diagram)
for the full module map.

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
3.12 via `winget`, sets up `.venv`, installs the package, pre-downloads
the default gameplay sources, and synthesizes the default SFX library
(vine boom, ding, whoosh, suspense — all generated locally by ffmpeg, no
downloads, no licensing concerns).

After the install finishes, activate the venv:

```cmd
:: cmd.exe
.venv\Scripts\activate.bat

:: PowerShell
.\.venv\Scripts\Activate.ps1
```

Flags:
- `-SkipGameplayDownload` — skip the ~5 GB gameplay pull
- `-SkipSfxSynthesis` — skip the (instant) SFX synthesis
- `-WithKokoro` — also install `kokoro-onnx` and download the local Kokoro
  TTS model (~310 MB). Optional; Edge TTS is the free default.

### Linux / macOS

```bash
git clone https://github.com/pablo228sos/yt-shorts-factory.git
cd yt-shorts-factory
./scripts/install.sh
```

### Manual

```bash
pip install -e ".[dev]"
# Linux:   sudo apt-get install -y ffmpeg
# macOS:   brew install ffmpeg
# Windows: winget install --id Gyan.FFmpeg -e
yt-shorts-factory download-gameplay   # populate cache/gameplay/sources/
yt-shorts-factory synthesize-sfx      # generate the default SFX library
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

# High-quality local TTS via Kokoro (~310 MB model, runs on CPU).
yt-shorts-factory generate-cmd --subreddit nosleep --tts kokoro

# Just see which stories pass the filters.
yt-shorts-factory list-stories --subreddit AmItheAsshole --limit 10

# Drop in your own royalty-free music (per-niche under drama/, horror/, …).
yt-shorts-factory generate-cmd --subreddit confession --music-dir cache/music
```

Outputs land in `out/<post_id>_<slugified-title>.mp4` plus an intermediate
work directory under `cache/work/`.

### Niche profiles

The `--niche` flag (default `auto`) picks per-subreddit voice / music
mood / hook style / SFX intensity. See
[CAPABILITIES.md §Niche profiles](CAPABILITIES.md#9-niche-profiles) for
the full mapping.

Pass `--niche horror` to force, or `--niche none` to disable overrides.
Any explicit CLI flag (`--voice`, `--speedup`, `--hook-style`) wins
over the niche profile default.

## Custom config

Pass `--config config.json` with anything you want to override. Example:

```json
{
  "reddit":    { "subreddit": "EntitledParents", "min_chars": 800 },
  "tts":       { "backend": "kokoro" },
  "hook":      { "style": "cliffhanger", "drop_original_title": true },
  "subtitles": { "max_words_per_chunk": 2, "vertical_position": 0.50, "uppercase": true },
  "sfx":       { "enabled": true, "max_sfx_per_video": 8 },
  "music":     { "enabled": true, "music_dir": "cache/music" },
  "gameplay":  { "preferred_height": 1080, "local_files": ["cache/gameplay/parkour.mp4"] }
}
```

Every field is documented in `src/yt_shorts_factory/config.py`.

## Tests

```bash
ruff check .
mypy
pytest
```

CI runs all three on every push — see
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## YouTube monetization notes

YouTube's 2025 "inauthentic / mass-produced" policy demonetizes channels
that publish AI-generated content with no transformative human input.
**Treat this tool as a draft generator, not an auto-uploader.** Before
publishing:

- Review and edit the script per video (10-15 seconds of work).
- Add a unique hook in the first 1.5 seconds.
- Vary voices, B-roll, and aspect framing.
- Don't run multiple channels off the same exact pipeline.

See [RESEARCH.md §10 The "inauthentic content" minefield](RESEARCH.md#10-the-inauthentic-content-minefield)
for the full rationale.
