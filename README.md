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
| B-roll | `assets/gameplay.py` | Local files or `yt-dlp`-cached clips |
| Composer | `render/composer.py` | ffmpeg, 1080×1920 @ 30 fps, audio ducking |

## Install

```bash
pip install -e ".[dev]"
sudo apt-get install -y ffmpeg   # or: brew install ffmpeg
```

You will also want **at least one gameplay clip**. The classic choice is
public-domain Minecraft Parkour or Subway Surfers gameplay. Drop any
`.mp4` into `cache/gameplay/` or pass it with `--gameplay path/to/clip.mp4`.

## Run

```bash
# Use a local gameplay clip
yt-shorts-factory generate-cmd \
  --subreddit AmItheAsshole \
  --time-filter day \
  --gameplay cache/gameplay/parkour.mp4 \
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
