# Capabilities — what yt-shorts-factory does today

> Source of truth for "what works right now in this branch."
> If something is on the [Roadmap](ROADMAP.md), it is **not** here.

## TL;DR

One command (`yt-shorts-factory generate-cmd`) takes a fresh wild story
from a rotation pool of 18 high-engagement subreddits (AITA, AITAH,
BORU, JustNoMIL, survivinginfidelity, raisedbynarcissists, nosleep,
TwoSentenceHorror, TrueOffMyChest, …), narrates it with the best-rated
open-source TTS (Kokoro-82M) using a voice that auto-matches the
narrator's gender, transcribes back into word-perfect captions, lays
everything over real 1080p gameplay **plus** a muted ASMR / cooking /
soap-cutting strip in the bottom half for retention, mixes in sound
effects placed by content cues, optionally ducks music under the voice,
and writes a 1080×1920 mp4 ready for YouTube Shorts / TikTok / Reels.

For non-stop production, `yt-shorts-factory batch --count 50` renders
50 unique videos in a row, rotating subreddits and B-roll sources and
deduping every story through a persistent SQLite db so you never see
the same post twice.

No paid APIs. No OAuth. Everything runs locally except the Reddit JSON
endpoint. TTS defaults to fully-local Kokoro-onnx; the free Microsoft
Edge endpoint is used as an automatic fallback when the Kokoro model
file is missing.

## Pipeline diagram

```
   reddit (multi-sub, top + new mix)
            |
            v
       dedup db filter (SQLite)
            |
            v
       cleaner -> hook rewriter -> niche profile (per-sub overlay)
            |
            v
       gender detector (regex on narrator markers)
            |
            v
       Kokoro <- fallback -> Edge TTS  ->  voice.mp3
            |
            +-> faster-whisper -> word timings
            |
            v
       SFX placer + .ass subs (\pos x,y centered)
            |
            v
       ffmpeg compose
          - top  : gameplay 1080p (rotated, no back-to-back repeats)
          - bot  : ASMR / cooking 1080x960 (muted, vstack)
          - mix  : voice + SFX + ducked music + ducked gameplay audio
            |
            v
       out/<id>_<slug>.mp4
```

---

## 1. Story sourcing

| Feature | Status | Module | Notes |
|---|---|---|---|
| Pull posts from any subreddit | ✓ | `sources/reddit.py` | Uses `https://reddit.com/r/<sub>/<sort>.json` (no OAuth) |
| **Multi-subreddit rotation pool (18 defaults)** | ✓ | `RedditConfig.subreddits` | AITA, AITAH, AmIOverreacting, EntitledParents, MaliciousCompliance, ProRevenge, JustNoMIL, raisedbynarcissists, relationship_advice, survivinginfidelity, nosleep, shortscarystories, TwoSentenceHorror, LetsNotMeet, confession, offmychest, TrueOffMyChest, BestofRedditorUpdates |
| **Fresh-content mixing** | ✓ | `RedditConfig.include_fresh` (default True) | Merges `/top` + `/new` so the pool always has last-hour posts |
| Configurable sort (top / hot / new / rising) | ✓ | `RedditConfig.sort` | CLI `--sort` |
| Time-filter window (`hour` / `day` / `week` / `month` / `year` / `all`) | ✓ | `RedditConfig.time_filter` | CLI `--time-filter` |
| Min/max story length filter | ✓ | `RedditConfig.min_chars / max_chars` | 600 – 3500 chars default |
| Skip NSFW + stickied posts | ✓ | `RedditConfig.skip_nsfw / skip_stickied` |  |
| **Persistent dedup (SQLite)** | ✓ | `sources/dedup.py`, `cache/processed.sqlite` | Every rendered post recorded; future runs skip it. `dedup-status` / `dedup-reset` CLI commands |
| **Graceful per-sub degradation** | ✓ | `_fetch_via` | A single sub's 503 doesn't poison the batch (logs + skips) |
| `list-stories` dry-run | ✓ | `cli.py:list_stories_cmd` | Preview candidates before rendering |
| Top-level title slug for filename | ✓ | `pipeline.py:_slugify` |  |

## 2. Text cleaning + hook rewriting

| Feature | Status | Module | Notes |
|---|---|---|---|
| Strip URLs, `[deleted]`, "EDIT:" blocks | ✓ | `script/cleaner.py` |  |
| Expand AITA / NTA / YTA / TIFU / TLDR jargon | ✓ | `cleaner.py` | "AITA" → "Am I the asshole" |
| Expand `(25F)` / `(M32)` shorthand into prose | ✓ | `cleaner.py` | Keeps Whisper from stumbling on parens |
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
| **Kokoro-onnx (local, CPU) — DEFAULT** | ✓ | `tts/kokoro.py` | Top-rated open-weight TTS model on TTS Arena (2025). ~310 MB one-time download. Fully local, no internet, no API key |
| Edge TTS (Microsoft Neural) — fallback | ✓ | `tts/edge.py` | Used automatically when Kokoro model isn't on disk. Free, online |
| **Auto-detect narrator gender** | ✓ | `script/gender.py` | Heuristic regex scoring: `I'm a 24F`, `my husband`, `as a guy`, etc. Picks `am_michael` / `af_heart` (Kokoro) or Christopher / Aria (Edge) accordingly |
| **Per-batch voice rotation** | ✓ | `pipeline._pick_gendered_voice` | Each story uses a different voice from the male/female pool, seeded by post id |
| Voice override via CLI | ✓ | `--voice <name>` | Wins over auto-gender |
| `audio_speedup = 1.0` (no speedup) | ✓ | `TtsConfig.audio_speedup` | User pref: clarity + intonation, not artificial speed |
| Audio rate / pitch / volume controls | ✓ | `tts.rate / pitch / volume` | Edge-specific SSML params |
| Outro padding before fadeout | ✓ | `RenderConfig.outro_padding_s` |  |
| `download-tts-models` CLI | ✓ | `cli.py` | Pulls Kokoro v1.0 model + voices |
| Auto-fallback when Kokoro missing | ✓ | `pipeline._maybe_fallback_to_edge` | No interruption — logs a warning and uses Edge |

## 4. Word-level transcription

| Feature | Status | Module | Notes |
|---|---|---|---|
| `faster-whisper` integration | ✓ | `transcribe/whisper.py` | int8 CPU, `base` model |
| Word-level start/end timings | ✓ | `WhisperConfig.word_timestamps=True` |  |
| Atempo timestamp rescaling | ✓ | `pipeline._rescale_words` | Keeps subs aligned when voice is sped up (no-op at speedup=1.0) |
| Configurable model size / device | ✓ | `WhisperConfig.model_size`, `device` | `tiny` / `base` / `small` / `medium` / `large-v3` |
| Auto-language detection or fixed | ✓ | `WhisperConfig.language` | Default `en` |

## 5. Subtitles

| Feature | Status | Module | Notes |
|---|---|---|---|
| Advanced SubStation Alpha (.ass) output | ✓ | `render/subtitles.py` |  |
| **Absolute `\pos(x,y)` positioning** (deterministic centering) | ✓ | `build_ass` | Replaces `Alignment + MarginV` so different libass builds agree on "centered" |
| Pop-word animation (1-3 words per chunk) | ✓ | `_chunk_words` |  |
| Active-word highlight in yellow + scale pop | ✓ | `_render_chunk_text` | `\fscx115\fscy115` on current word |
| ALL CAPS rendering | ✓ | `SubtitleStyle.uppercase=True` |  |
| Font fallback chain | ✓ | Bebas Neue → Impact → Oswald → Arial Black |  |
| Configurable outline / shadow / color | ✓ | `SubtitleStyle` |  |
| Vertical position (0=top, 1=bottom) | ✓ | `SubtitleStyle.vertical_position` (default 0.55) | Slightly above true center, classic Shorts placement |
| Word-end punctuation triggers chunk break | ✓ | `,.!?` |  |

## 6. Sound effects (SFX)

| Feature | Status | Module | Notes |
|---|---|---|---|
| Local synthesis via ffmpeg `aevalsrc` | ✓ | `assets/sfx.py` | Fixed `aevalsrc=exprs=` syntax (vs broken `expr=` previously) |
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
| Base volume control | ✓ | `MusicConfig.base_volume_db` |  |
| Disable globally | ✓ | `--music-dir` empty or missing dir |  |

## 8. B-roll (gameplay top half + ASMR bottom half)

### Gameplay (top)

| Feature | Status | Module | Notes |
|---|---|---|---|
| Auto-download via yt-dlp at 1080p | ✓ | `assets/gameplay.py:download_source` | `bv*[height<=1080][ext=mp4]+ba` format selector |
| `download-gameplay --kind gameplay` CLI | ✓ | `cli.py` |  |
| Two-tier cache (sources/ + segments/) | ✓ | `cache/gameplay/sources/`, `cache/gameplay/segments/` |  |
| Random 90-second slicing | ✓ | `_extract_segment` |  |
| **Auto-prune stale low-res segments** | ✓ | `prune_low_res_segments` | When `preferred_height` is bumped to 1080, old 720p slices are deleted automatically |
| **Avoid back-to-back repeats** | ✓ | `_pick_non_recent` | Process-local memory of last 5 picks; consecutive batch videos use visually different B-roll |
| Lanczos downscale (sharp, not blurry) | ✓ | `composer._build_filter_graph` |  |
| User-provided local files | ✓ | `gameplay.local_files` |  |
| Cache size cap | ✓ | `GameplayConfig.max_disk_mb` | Default 8192 MB |
| Cookies-from-browser for blocked YouTube | ✓ | `GameplayConfig.cookies_from_browser` |  |
| Configurable source URL list | ✓ | `GameplayConfig.sources` | Default mix of direct URLs + `ytsearch1:` fallbacks |

### ASMR overlay (bottom)

| Feature | Status | Module | Notes |
|---|---|---|---|
| **Split-screen render** | ✓ | `composer._build_filter_graph` | Top: gameplay (W × (H - asmr_height)); bottom: ASMR (W × asmr_height); vstacked |
| ASMR audio muted | ✓ | composer skips mapping ASMR audio | Voice + music + SFX bus stays clean |
| Default sources: soap cutting / cooking / kinetic sand / glass cutting | ✓ | `_DEFAULT_ASMR_SOURCES` | `ytsearch1:` queries, kept current with content |
| Separate cache `cache/asmr/` | ✓ | `AsmrConfig.cache_dir` | Won't collide with gameplay cache |
| `download-gameplay --kind asmr` | ✓ | `cli.py` | Pre-fetches every ASMR source |
| Rotated independently of gameplay | ✓ | shared `_RECENT_SEGMENTS` memory | ASMR clips also don't repeat back-to-back |
| Toggle on/off | ✓ | `--asmr / --no-asmr` |  |
| Adjustable height | ✓ | `AsmrConfig.asmr_height` | Default 960 (50% of 1920) |

## 9. Niche profiles

| Niche | Subreddits | Voice (Edge fallback) | Music mood | Hook style | Notes |
|---|---|---|---|---|---|
| **drama** | AITA, AITAH, EntitledParents, MaliciousCompliance, BORU, AmIOverreacting, ProRevenge | en-US-ChristopherNeural | drama | drama | Heaviest SFX, male voice for conflict |
| **horror** | nosleep, Glitch_in_the_Matrix, LetsNotMeet, shortscarystories, TwoSentenceHorror | en-US-ChristopherNeural | horror | cliffhanger | suspense SFX dominant |
| **comedy** | TIFU, IDontWorkHereLady, pettyrevenge | en-US-ChristopherNeural | comedy | drama | Light SFX |
| **relationship** | relationship_advice, survivinginfidelity, adultery, cheating_stories, BreakUps | en-US-AriaNeural | drama | cliffhanger | Female voice default for betrayal/relationship stories |
| **confession** | offmychest, TrueOffMyChest, raisedbynarcissists, JustNoMIL | en-US-AriaNeural | drama | cliffhanger | Dark personal confessions |
| **everyday** | casualconversation, ChoosingBeggars | en-US-JennyNeural | lofi | drama | Calmest mix |

All profiles use `audio_speedup = 1.0` (no artificial speedup). Per-profile
fields applied via `niche/profiles.py:apply_profile()`: voice,
hook_style, sfx_intensity, music_mood. CLI overrides win — `--voice`,
`--speedup`, `--no-sfx`, etc.

Niche voice values are overridden again per-story by the gender
detector when `auto_gender=True` (default), so a story whose narrator
says *"I'm a 32F"* in a drama subreddit will still get a female Kokoro
voice.

## 10. Final render

| Feature | Status | Notes |
|---|---|---|
| 1080×1920 @ 30 fps | ✓ | `RenderConfig.width/height/fps` |
| libx264 CRF 22 + AAC 192 kbps | ✓ | YouTube-recommended bitrate band |
| `+faststart` mp4 atom moved to front | ✓ | Fast web-start playback |
| Outro padding (silence + freeze frame) | ✓ | Avoids hard cut on YouTube |
| Atomic file write (`out/<id>_<slug>.mp4`) | ✓ |  |
| Reproducible filename slug | ✓ | `pipeline.py:_slugify` |
| Generation result returned to caller | ✓ | `GenerationResult` dataclass — includes `asmr_path`, `detected_gender` |

## 11. CLI surface

| Command | Purpose |
|---|---|
| `yt-shorts-factory generate-cmd` | One-off full pipeline run |
| **`yt-shorts-factory batch --count N`** | **Non-stop production: N unique videos in a row, rotating subs + B-roll, dedup-aware** |
| `yt-shorts-factory list-stories` | Preview Reddit candidates |
| `yt-shorts-factory download-gameplay --kind gameplay\|asmr` | Pre-cache 1080p B-roll for top or bottom panel |
| `yt-shorts-factory synthesize-sfx` | Generate the default SFX library locally |
| `yt-shorts-factory download-tts-models` | Fetch Kokoro-onnx model weights |
| `yt-shorts-factory dedup-status` | Show how many posts the dedup db has logged |
| `yt-shorts-factory dedup-reset` | Wipe the dedup db (lets previously rendered posts back into the pool) |

CLI flags (the important ones):

```
--subreddit          pin a single sub (skip the rotation pool)
--subreddits a,b,c   override the rotation pool (comma-separated)
--time-filter        hour | day | week | month | year | all (default day)
--sort               top | hot | new | rising (default top)
--fresh / --no-fresh additionally mix "new" alongside the chosen sort (default on)
--tts kokoro|edge    TTS backend (default kokoro, auto-fallback to edge)
--voice              Manual voice override (wins over auto-gender)
--speedup            atempo factor (default 1.0; user pref: clarity not speed)
--niche auto|<name>  drama | horror | comedy | relationship | confession | everyday | none
--caps / --no-caps   ALL CAPS subs toggle (default on)
--sfx / --no-sfx     SFX toggle (default on)
--asmr / --no-asmr   split-screen ASMR overlay toggle (default on)
--music-dir          path to royalty-free music root (per-mood subdirs)
--output-dir         where to write the mp4(s)
--gameplay           force specific B-roll file(s) (repeatable)
--count N            batch: how many videos to render (default 10)
--sleep S            batch: seconds between iterations (default 2.0)
--skip-dedup         batch: render even posts already in the dedup db
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
| CPU | 4 cores | 8+ cores | Kokoro + whisper are CPU-bound |
| RAM | 8 GB | 16 GB | Whisper `base` model peaks ~2 GB, Kokoro ~1.5 GB |
| Disk | 12 GB | 30 GB | Gameplay + ASMR caches + Kokoro model |
| GPU | none | none required | All defaults run CPU-only |
| Network | 5 Mbps | 50 Mbps | Initial gameplay + ASMR download is ~10 GB |

## 14. Test coverage

- **66 unit tests** covering cleaner / hook rewriter / niche resolver /
  composer filter-graph / Reddit parser (single + multi-sub + fresh-mix
  + graceful HTTP error degradation) / TTS dispatch / SFX synth-graph
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
- ✗ Stock-footage backgrounds (we use gameplay + ASMR overlays instead)
- ✗ OpenAI / ElevenLabs TTS (planned — see Roadmap)
- ✗ Image-based Reddit posts (text posts only)
