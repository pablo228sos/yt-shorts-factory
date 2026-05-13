# Roadmap

Ordered by what's **next** (current PR / next PR / later). Tracks both
shipped features and planned ones — the canonical "where we are vs.
where we're going" file. Pair this with [CAPABILITIES.md](CAPABILITIES.md)
for what already works.

## Status legend

- ✅ Shipped (on `main` or in an open PR being merged)
- 🔧 In progress (this branch / open PR)
- 📋 Planned (next 1-2 PRs)
- 💡 Idea (not yet committed; here to remember it)

---

## Stage 0 — MVP foundation ✅

- ✅ Reddit JSON puller (no OAuth)
- ✅ Edge TTS narration
- ✅ Whisper word-level transcription
- ✅ TikTok-style pop-word captions
- ✅ ffmpeg compose to 1080×1920 mp4
- ✅ Windows + Linux + macOS installers
- ✅ CI: ruff + mypy strict + pytest

## Stage 1 — Quality pass (PR #4) ✅

- ✅ 1080p gameplay source with lanczos downscale (sharp)
- ✅ Hook rewriter (drama / question / verdict / cliffhanger)
- ✅ Kokoro-onnx local TTS backend
- ✅ Bebas Neue ALL CAPS + yellow highlight + scale pop
- ✅ SFX engine (vine boom / ding / whoosh / suspense)
- ✅ Music bed with sidechain ducking
- ✅ Niche profiles (drama / horror / comedy / relationship / confession / everyday)
- ✅ Niche profile respects CLI overrides
- ✅ ffmpeg filter-graph: dangling-pad bug fixed
- ✅ SFX `aevalsrc` synth bug fix (option is `exprs` not `expr`)
- ✅ Subtitle absolute `\pos(x,y)` for deterministic vertical placement (centered, regardless of libass build)
- ✅ Default `audio_speedup=1.0` (no speedup) across all niches — user pref: clarity + intonation
- ✅ Invalidate stale 720p cached segments on source-quality bump

## Stage 2 — Retention + variety (PR #4 continued) ✅

- ✅ **Kokoro as default backend** with auto-fallback to Edge when model files are missing
- ✅ **Auto-pick voice gender** from story POV — heuristic on text
  ("my husband / wife", "I'm a 24F / 32M", "as a woman / man") picks
  female or male Edge / Kokoro voice automatically; CLI `--voice` wins
- ✅ **Per-video variety** — process-local memory of last-5 B-roll picks;
  gameplay + ASMR pickers each avoid back-to-back repeats
- ✅ **Split-screen ASMR strip** — top: 1080×960 gameplay; bottom: 1080×960
  ASMR / cooking / soap-cutting / kinetic-sand / glass-cutting (muted)
- ✅ **ASMR B-roll engine** — `cache/asmr/` separate from gameplay cache;
  shared yt-dlp pipeline, `download-gameplay --kind asmr` CLI
- ✅ **Wider edgy subreddit defaults** — 18-item rotation pool (AITA,
  AITAH, AmIOverreacting, EntitledParents, MaliciousCompliance,
  ProRevenge, JustNoMIL, raisedbynarcissists, relationship_advice,
  survivinginfidelity, nosleep, shortscarystories, TwoSentenceHorror,
  LetsNotMeet, confession, offmychest, TrueOffMyChest,
  BestofRedditorUpdates)
- ✅ **Fresh-content mixing** — `include_fresh=True` pulls `/top` AND
  `/new` and merges, so the pool always contains last-hour posts
- ✅ **SQLite dedup** — `cache/processed.sqlite` records every
  post_id rendered; batch mode never picks a repeat
- ✅ **Batch mode** — `yt-shorts-factory batch --count N --subreddits a,b,c`
  rotates through multi-subreddit list, dedups, tolerates per-video errors,
  sleep between iterations to respect Reddit rate limits

## Stage 3 — Premium TTS + LLM hooks (next PR) 📋

- 📋 **OpenAI gpt-4o-mini-tts backend** — `--tts openai`
  - Accepts text instruction per video: _"emotional first-person
    female narrator, tense build, slight pauses on dramatic words"_
  - Most expressive voice in market for this price tier
    (~$0.015 / video)
  - Needs `OPENAI_API_KEY`
- 📋 **OpenAI gpt-4o-mini hook rewriter** — let the LLM generate the
  first-1.5-second hook from the post body (much stronger than my
  template-based rewriter)
- 📋 **OpenAI moderation pre-check** — skip posts flagged as
  hate / sexual-minor / etc. to keep the channel monetizable
- 📋 **Voice-instruction cascade** — pull tone from niche + body
  sentiment ("anxious / smug / shocked / sympathetic") and pipe into
  the TTS instruction field

## Stage 4 — Distribution & growth 📋

- 📋 **Title / description / hashtag generator** — per-niche prompt
  with `[trending], [niche], [hook]` slots
- 📋 **Thumbnail generator** — frame at the most dramatic word,
  add big-text overlay
- 📋 **YouTube uploader** — `yt-shorts-factory upload <mp4>` using
  the YouTube Data API v3. Manual review required (compliance with
  "inauthentic content" policy)
- 📋 **TikTok uploader** via web upload (no public API)
- 📋 **Instagram Reels uploader** via Graph API
- 📋 **Scheduling** — `yt-shorts-factory schedule --daily 4` queues
  per-day batches at uniformly-spaced times

## Stage 5 — Advanced retention 💡

- 💡 **Mid-roll cliffhanger insertion** — splice in
  _"…but then she sent me one more text…"_ at 25 s to bait the
  algorithm's second-3 click-replay metric
- 💡 **Series detection** — BORU "Part 2" auto-link in description
- 💡 **A/B test runner** — render the same story with 2 different
  hooks, compare 24h analytics, learn winning hook style per niche
- 💡 **Image / meme inserts** — for confession / TIFU posts that have
  inline imgur links, mid-video B-roll cut to the image for 1-2 s

## Stage 6 — Polish 💡

- 💡 Multi-language support (RU / ES / DE) — Whisper + Edge already
  handle these; cleaner + hook templates need translation
- 💡 GPU TTS path — Coqui XTTS-v2 or Orpheus-TTS for 4080+ users
- 💡 Style transfer for gameplay — recoloring / stylization to keep
  channel content visually unique
- 💡 "Beat-sync" subtitle pops on the SFX cues

---

## Non-goals (won't do, here for clarity)

- ❌ Voice cloning of real people (legal liability, also bannable on YT)
- ❌ Hard adult / NSFW subreddit support (demonetizes channel)
- ❌ Cross-posting to channels we don't own
- ❌ Buying view-bots / engagement
- ❌ Anything that violates YouTube's "inauthentic and mass-produced
  content" policy. The tool generates **drafts**; human review per
  video is required for monetization eligibility.
