# Capabilities — what yt-shorts-factory does today

> Source of truth for "what works right now in this branch."
> If something is on the [Roadmap](ROADMAP.md), it is **not** here.

## TL;DR

One command (`yt-shorts-factory generate-cmd`) takes a top story from
Reddit, narrates it, transcribes the narration back into word-perfect
captions, lays it over real 1080p gameplay, mixes in sound effects
placed by content cues, optionally ducks music under the voice, and
writes a 1080×1920 mp4 ready for YouTube Shorts / TikTok / Reels.

No paid APIs. No OAuth. Everything runs locally except the Reddit JSON
endpoint and Microsoft Edge's free public TTS API (replaceable with
fully-local Kokoro-onnx).

## Pipeline diagram

```
   reddit.json  ─►  cleaner  ─►  hook rewriter  ─►  niche profile
                                                          │
                          ┌───────────────────────────────┘
                          ▼
                  TTS  ─►  voice.mp3
                          │
                          ├──►  faster-whisper  ─►  word timings (re-scaled)
                          │                              │
                          ▼                              ▼
                  SFX placer (?, !, ...)        .ass subtitle gen
                          │                              │
                          └────────────►  ffmpeg  ◄──────┘
                                              │
                          gameplay 1080p  ────┤
                          music (optional) ───┘
                                              │
                                              ▼
                                       out/<id>_<slug>.mp4
```

---

## 1. Story sourcing

| Feature | Status | Module | Notes |
|---|---|---|---|
| Pull top posts from any subreddit | ✓ | `sources/reddit.py` | Uses `https://reddit.com/r/<sub>/top.json` (no OAuth) |
| Time-filter window (`hour` / `day` / `week` / `month` / `year` / `all`) | ✓ | `sources/reddit.py:30` | CLI: `--time-filter day` |
| Minimum-score / min-text-length floors | ✓ | `RedditConfig.min_score`, `min_chars` | Skips low-effort spam |
| Whitelist / blacklist filters | ✓ | Title-substring filters | Mocked-out for tests, real on prod |
| `list-stories` dry-run | ✓ | `cli.py:list_stories_cmd` | Preview candidates before rendering |
| `--story-url <permalink>` override | ✓ | `cli.py` | Pin a specific post |
| Self-post / link-post detection | ✓ | Filters out posts without body text |
| Removed / deleted-post detection | ✓ | Skipped silently |
| Top-level "AITA"-style title slug for filename | ✓ | `pipeline.py:_slug` |

## 2. Text cleaning + hook rewriting

| Feature | Status | Module | Notes |
|---|---|---|---|
| Strip URLs, `[deleted]`, "EDIT:" blocks | ✓ | `script/cleaner.py` |  |
| Expand AITA / NTA / YTA / TIFU / TLDR jargon | ✓ | `cleaner.py` | "AITA" → "Am I the asshole" |
| Sentence segmentation | ✓ | regex split on `.!?` |  |
| Profanity censor | ✓ | `cleaner.py` censor list | Keeps Shorts ad-friendly |
| Hook rewriter | ✓ | `script/hook.py` | 4 styles + auto-pick from sub |
| → `drama` style | ✓ | "OH MY GOD..." + title rephrase |  |
| → `question` style | ✓ | "What would you do if..." |  |
| → `verdict` style | ✓ | "AITA? You decide." |  |
| → `cliffhanger` style | ✓ | "I never thought it would end like this..." |  |
| `--drop-original-title` to remove redundant subject | ✓ | `HookConfig.drop_original_title` |  |
| Per-niche hook style override | ✓ | `niche/profiles.py` |  |

## 3. TTS (text-to-speech)

| Feature | Status | Backend | Notes |
|---|---|---|---|
| Edge TTS (Microsoft Neural) | ✓ | `tts/edge.py` | Default. Online API, free. 7/10 quality |
| Kokoro-onnx (local, CPU) | ✓ | `tts/kokoro.py` | Opt-in via `--tts kokoro`. 8/10 quality, ~310 MB model |
| Voice override via CLI | ✓ | `--voice en-US-AriaNeural` | Edge voices: Guy / Aria / Christopher / Brian / Jenny / others |
| Voice override via config | ✓ | `tts.voice` | Same |
| Audio rate / pitch / volume controls | ✓ | `tts.rate`, `tts.pitch`, `tts.volume` | Edge-specific SSML params |
| Speed-up (ffmpeg `atempo`) | ✓ | `RenderConfig.audio_speedup` | Post-TTS speedup; recommend 1.0 (no speedup) |
| Outro padding before fadeout | ✓ | `RenderConfig.outro_padding_s` | 0.15 s default |
| `download-tts-models` command | ✓ | `cli.py` | Pulls Kokoro v1.0 model + voices |

## 4. Word-level transcription

| Feature | Status | Module | Notes |
|---|---|---|---|
| `faster-whisper` integration | ✓ | `transcribe/whisper.py` | int8 CPU, `base` model |
| Word-level start/end timings | ✓ | `WhisperConfig.word_timestamps=True` |  |
| Atempo timestamp rescaling | ✓ | `transcribe/whisper.py:_rescale_for_atempo` | Keeps subs aligned when voice is sped up |
| Configurable model size / device | ✓ | `WhisperConfig.model_size`, `device` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| Auto-language detection or fixed | ✓ | `WhisperConfig.language` | Default `en` |

## 5. Subtitles

| Feature | Status | Module | Notes |
|---|---|---|---|
| Advanced SubStation Alpha (.ass) output | ✓ | `render/subtitles.py` |  |
| Pop-word animation (1-3 words per chunk) | ✓ | `_chunk_words` |  |
| Active-word highlight in yellow + scale pop | ✓ | `_render_chunk_text` | `\fscx115\fscy115` on current word |
| ALL CAPS rendering | ✓ | `SubtitleStyle.uppercase=True` |  |
| Font fallback chain | ✓ | Bebas Neue → Impact → Arial Black |  |
| Configurable outline / shadow / color | ✓ | `SubtitleStyle` |  |
| Vertical position (0=top, 1=bottom) | ✓ | `SubtitleStyle.vertical_position` |  |
| Word-end punctuation triggers chunk break | ✓ | `,.!?` |  |
| Max-words-per-chunk override | ✓ | `SubtitleStyle.max_words_per_chunk` |  |

## 6. Sound effects (SFX)

| Feature | Status | Module | Notes |
|---|---|---|---|
| Local synthesis via ffmpeg `aevalsrc` | ✓ | `assets/sfx.py` | No downloads, no licensing |
| `synthesize-sfx` CLI command | ✓ | `cli.py` |  |
| `vine_boom.mp3` (50 Hz exponential decay) | ✓ |  | Drama beats |
| `ding.mp3` (1.5 kHz dual-ping) | ✓ |  | Notifications |
| `whoosh.mp3` (filtered white-noise sweep) | ✓ |  | Scene transitions |
| `suspense.mp3` (220 Hz drone + 4 Hz tremolo) | ✓ |  | Horror cliffhangers |
| Auto-placement by content cues | ✓ | `assets/sfx.py:place_sfx` | `?` → ding, `!` → vine boom, …pause… → whoosh |
| Per-cue volume control | ✓ | `SfxConfig.vine_boom_db`, etc. |  |
| Max SFX per video cap | ✓ | `SfxConfig.max_sfx_per_video` | Default 8 |
| Overlap prevention | ✓ | `_spans_overlap` checks |  |
| Per-niche SFX intensity scaler | ✓ | `NicheProfile.sfx_intensity` |  |

## 7. Music bed (optional)

| Feature | Status | Module | Notes |
|---|---|---|---|
| User-provided royalty-free mp3 pool | ✓ | `assets/music.py` | Drop files under `cache/music/<mood>/` |
| Per-niche mood selection | ✓ | `NicheProfile.music_mood` | drama / horror / comedy / lofi |
| Sidechain ducking under voice | ✓ | `render/composer.py:audio_parts` | `sidechaincompress` filter |
| Base volume control | ✓ | `MusicConfig.base_db` |  |
| Disable globally | ✓ | `--no-music` |  |

## 8. B-roll (gameplay background)

| Feature | Status | Module | Notes |
|---|---|---|---|
| Auto-download via yt-dlp at 1080p | ✓ | `assets/gameplay.py:download_source` |  |
| `download-gameplay` CLI | ✓ | `cli.py` |  |
| Two-tier cache (sources/ + segments/) | ✓ | `cache/gameplay/sources/`, `cache/gameplay/segments/` |  |
| Random N-second slicing | ✓ | `_extract_segment` | Default 60 s |
| Lanczos downscale (sharp, not blurry) | ✓ | `render/composer.py:video_parts` | 1080p → 1080x1920 |
| User-provided local files | ✓ | `gameplay.local_files` |  |
| Cache size cap | ✓ | `GameplayConfig.max_disk_mb` | Default 4096 MB |
| Cookies-from-browser for blocked YouTube | ✓ | `GameplayConfig.cookies_from_browser` |  |
| Configurable source URL list | ✓ | `GameplayConfig.sources` | Default: 4 popular parkour / Subway Surfers compilations |

## 9. Niche profiles

| Niche | Subreddits | Voice (Edge) | Music mood | Hook style | Notes |
|---|---|---|---|---|---|
| **drama** | AmItheAsshole, AITAH, EntitledParents, MaliciousCompliance, BORU | en-US-GuyNeural | drama | drama | Heaviest SFX |
| **horror** | nosleep, Glitch_in_the_Matrix, LetsNotMeet, shortscarystories, TwoSentenceHorror | en-US-BrianMultilingualNeural (slow) | horror | cliffhanger | suspense SFX dominant |
| **comedy** | TIFU, confession, IDontWorkHereLady, pettyrevenge | en-US-ChristopherNeural | comedy | drama | Light SFX |
| **relationship** | relationship_advice, dating_advice, BreakUps | en-US-AriaNeural | drama | drama | Female voice default |
| **everyday** | offmychest, TrueOffMyChest, casualconversation, ChoosingBeggars | en-US-JennyNeural | lofi | drama | Calmest mix |

Per-profile fields applied via `niche/profiles.py:apply_profile()`:
voice, audio_speedup (recommended 1.0), hook_style, sfx_intensity,
music_mood. CLI overrides win — `--voice`, `--speedup`, `--no-sfx`, etc.

## 10. Final render

| Feature | Status | Notes |
|---|---|---|
| 1080×1920 @ 30 fps | ✓ | `RenderConfig.width/height/fps` |
| libx264 CRF 22 + AAC 192 kbps | ✓ | YouTube-recommended bitrate band |
| `+faststart` mp4 atom moved to front | ✓ | Fast web-start playback |
| Outro padding (silence + freeze frame) | ✓ | Avoids hard cut on YouTube |
| Atomic file write (`out/<id>_<slug>.mp4`) | ✓ |  |
| Reproducible filename slug | ✓ | `pipeline.py:_slug` |
| Generation result returned to caller | ✓ | `GenerationResult` dataclass |

## 11. CLI surface

| Command | Purpose |
|---|---|
| `yt-shorts-factory generate-cmd` | One-off full pipeline run |
| `yt-shorts-factory list-stories` | Preview Reddit candidates |
| `yt-shorts-factory download-gameplay` | Pre-cache 1080p gameplay |
| `yt-shorts-factory synthesize-sfx` | Generate the default SFX library locally |
| `yt-shorts-factory download-tts-models` | Fetch Kokoro-onnx model weights |

CLI flags (the important ones):

```
--subreddit          target sub (default AmItheAsshole)
--time-filter        hour | day | week | month | year | all (default day)
--config             override JSON config file
--tts edge|kokoro    TTS backend (default edge)
--voice              Edge voice name override
--speedup            atempo factor (1.0 = no change; per-niche default if unset)
--niche auto|<name>  force a niche profile
--hook-style         drama|question|verdict|cliffhanger|auto|none
--caps / --no-caps   ALL CAPS subs toggle
--sfx / --no-sfx     enable/disable sound effects
--music-dir          path to royalty-free music root (per-mood subdirs)
--output-dir         where to write the mp4
--gameplay           force a specific B-roll file
--story-url          force a specific Reddit permalink
-v / --verbose       debug logging
```

## 12. Cross-platform support

| Platform | Status | Notes |
|---|---|---|
| Windows 10 / 11 (cmd.exe) | ✓ | `scripts/install.bat` wraps PowerShell |
| Windows 10 / 11 (PowerShell) | ✓ | `scripts/install.ps1` direct |
| Linux (Debian / Ubuntu) | ✓ | `scripts/install.sh` |
| macOS | ✓ | `scripts/install.sh` |
| CI: lint + mypy strict + pytest | ✓ | `.github/workflows/ci.yml`, Python 3.11 + 3.12 matrix |

## 13. Hardware

| Component | Minimum | Recommended | Notes |
|---|---|---|---|
| CPU | 4 cores | 8+ cores | Edge TTS is network-bound; whisper is CPU-bound |
| RAM | 8 GB | 16 GB | Whisper `base` model peaks ~2 GB |
| Disk | 8 GB | 20 GB | Gameplay cache + Kokoro model |
| GPU | none | none required | All defaults run CPU-only |
| Network | 5 Mbps | 50 Mbps | Initial gameplay download is ~5 GB |

## 14. Test coverage

- **63 unit tests** covering cleaner / hook rewriter / niche resolver /
  composer filter-graph / Reddit parser / TTS dispatch / SFX synth-graph
  invariants / subtitle generator. CI must be green on every PR.
- mypy strict mode passes (no untyped defs, no Any).
- Ruff with default-strict ruleset.

## 15. What is intentionally NOT here

Things you might expect but that we explicitly do not do — see
[ROADMAP](ROADMAP.md) for which are planned.

- ✗ Automatic YouTube upload (manual draft review required)
- ✗ Voice cloning
- ✗ Translation / dubbing
- ✗ Thumbnail generation
- ✗ Automatic title / description / hashtags
- ✗ Series detection ("Part 1 / Part 2" continuity)
- ✗ Multi-account scheduling
- ✗ Stock-footage backgrounds
- ✗ Split-screen ASMR strip (planned — see Roadmap)
- ✗ OpenAI / ElevenLabs TTS (planned — see Roadmap)
- ✗ Image-based Reddit posts (text posts only)
