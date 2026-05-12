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
1080x1920 mp4 - all in one CLI command.

No paid APIs. No OAuth. Just `pip install` and a few mp4s.

## Pipeline

```
Reddit JSON -> text cleaner -> hook rewriter -> niche profile -> TTS
            -> faster-whisper word timings (rescaled for atempo)
            -> SFX placer (?, !, scene markers)
            -> .ass subtitles -> ffmpeg compose -> out/<id>_<slug>.mp4
```

| Stage | Module | Default |
|---|---|---|
| Story source | `sources/reddit.py` | `r/AmItheAsshole`, top of day |
| Text cleaner | `script/cleaner.py` | Strips URLs/edits, expands AITA jargon, censors profanity |
| Hook rewriter | `script/hook.py` | Auto drama / question / verdict / cliffhanger opener |
| Niche profile | `niche/profiles.py` | Per-subreddit voice/music/SFX/hook overrides |
| TTS | `tts/edge.py` (default), `tts/kokoro.py` (opt-in) | `en-US-GuyNeural` (Edge) or `af_heart` (Kokoro local) |
| Voice speedup | `composer.py` atempo chain | 1.18x brainrot pace (per-niche override) |
| Transcription | `transcribe/whisper.py` | `faster-whisper` base model, int8 CPU |
| Subtitles | `render/subtitles.py` | Bebas Neue, 1-3 words/chunk, ALL CAPS, yellow highlight with scale pop |
| SFX engine | `assets/sfx.py` | ffmpeg-synthesized vine boom / ding / whoosh / suspense |
| Music bed | `assets/music.py` | User-provided royalty-free tracks, sidechain ducked under voice |
| B-roll | `assets/gameplay.py` | yt-dlp 1080p Minecraft Parkour / Subway Surfers, sharp lanczos downscale |
| Composer | `render/composer.py` | ffmpeg, 1080x1920 @ 30 fps, sidechain ducking, libx264 CRF 22 |

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
(vine boom, ding, whoosh, suspense - all generated locally by ffmpeg, no
downloads, no licensing concerns).

Flags:
- `-SkipGameplayDownload` - skip the ~5 GB gameplay pull
- `-SkipSfxSynthesis` - skip the (instant) SFX synthesis
- `-WithKokoro` - also install `kokoro-onnx` and download the local Kokoro
  TTS model (~310 MB). Optional; Edge TTS is the free default.

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

# High-quality local TTS via Kokoro (~340 MB model, runs on CPU).
yt-shorts-factory generate-cmd --subreddit nosleep --tts kokoro

# Slower, less brainrot-y pace.
yt-shorts-factory generate-cmd --subreddit AmItheAsshole --speedup 1.0

# Drop in your own royalty-free music (organize per-niche under drama/, horror/, comedy/, lofi/).
yt-shorts-factory generate-cmd --subreddit confession --music-dir cache/music
```

### Niche profiles

The `--niche` flag (default `auto`) picks per-subreddit voice / music
mood / hook style / speedup / SFX intensity. Auto-detected niches:

| Niche | Subreddits | Voice | Mood | Speedup |
|---|---|---|---|---|
| drama | AmItheAsshole, EntitledParents, MaliciousCompliance, BestofRedditorUpdates | Guy | drama | 1.20 |
| horror | nosleep, Glitch_in_the_Matrix, LetsNotMeet, shortscarystories | Brian (slow) | horror | 1.05 |
| comedy | TIFU, confession, IDontWorkHereLady, MaliciousComplianceComedy | Christopher | comedy | 1.22 |
| relationship | relationship_advice, dating_advice, BreakUps | Aria | drama | 1.18 |
| everyday | offmychest, TrueOffMyChest, casualconversation | Jenny | lofi | 1.15 |

Pass `--niche horror` to force, or `--niche none` to disable overrides.

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
  "tts":       { "backend": "kokoro", "audio_speedup": 1.22 },
  "hook":      { "style": "cliffhanger", "drop_original_title": true },
  "subtitles": { "max_words_per_chunk": 2, "vertical_position": 0.55, "uppercase": true },
  "sfx":       { "enabled": true, "max_sfx_per_video": 8 },
  "music":     { "enabled": true, "music_dir": "cache/music" },
  "gameplay":  { "preferred_height": 1080, "local_files": ["cache/gameplay/parkour.mp4"] }
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
