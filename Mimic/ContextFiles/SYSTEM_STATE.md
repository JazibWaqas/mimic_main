# MIMIC - System State

**Version:** V15.0 — The Personal Editor Mode
**Last Updated:** March 2026
**Status:** Consumer-Optimized / Local Use / Startup-Track

---

## Current Product Direction

MIMIC was originally built as a hackathon submission for the Google Gemini API Developer Competition. It is now being optimized as a personal creative tool and the foundation for a future consumer startup.

**The current priority is simple:** make the best-looking, most professional-feeling edits possible locally. When the output looks like a proper Instagram reel, we iterate from there. Only after local perfection comes the demo, audience validation, and commercial build-out.

**Primary quality metric:** "Does this look like an intentional, well-paced Instagram or TikTok edit?"
- Clips must match the narrative (friends edit → people clips dominate)
- Pacing must feel right (fast then slow, or slow builds — not mechanical metronome)
- Text overlay intent from reference must be honored
- No obviously repeated clips or moments
- Music ends with video (no trailing video or early cut-off)

---

## What's Working (Confirmed)

| Feature | Status | Notes |
|---|---|---|
| Reference Mode pipeline | ✅ Functional | Main mode. All 7 stages tested |
| Prompt Mode pipeline | ✅ Functional | Tested and working; more testing needed |
| Gemini 3 clip analysis | ✅ Functional | Cached after first analysis |
| Gemini 3 reference analysis | ✅ Functional | Cached by content hash |
| DeepSeek V3 blueprint generation | ✅ Functional | Generator.py confirmed |
| DeepSeek V3 strategic advisor | ✅ Functional | gemini_advisor.py confirmed |
| Groq Llama 3.3 70B vault | ✅ Functional | reflector.py confirmed |
| V15.0 Score rebalancing | ✅ Implemented | Subject bonus: 8/3 (was 15/5) |
| V15.0 Random tiebreaker | ✅ Implemented | +0 to +8.0 per clip per segment |
| V15.0 Global history novelty | ✅ Implemented | clip_history.json tracking |
| V15.0 Duration Trim Guard | ✅ Implemented | Trims >0.1s drift in final concat |
| V14.7.2 Clock-Lock (30fps CFR) | ✅ Implemented | vsync cfr, AAC 48kHz |
| V14.0 Contextual moment selection | ✅ Implemented | Full segment whitelist enabled |
| Moment-level reuse penalty | ✅ Implemented | Exact (>80% = -999.0) or partial (>30% = -200/-100) overlap |
| Sacred Visual Cuts | ✅ Implemented | Visual origin = no subdivision |
| Hash-based caching (all stages) | ✅ Implemented | Persistent across sessions |
| Smart Micro-Cut moments (<1.0s) | ✅ Implemented | High-energy windows prioritized; duplicate if start/end overlap < 0.1s |
| Pre-scan clips before blueprint | ✅ Implemented | Prompt Mode only |
| Hard clip reuse (no repeat per edit) | ✅ Implemented | March 2026: skip if usage >= 1 |
| Advisor returns alternatives only (no fake memory) | ✅ Implemented | March 2026: editor is source of truth |
| Candidate ranking before truncation | ✅ Implemented | March 2026: semantic 0.7 + musical 0.3 |
| Richer candidate metadata to advisor prompt | ✅ Implemented | March 2026: content_description, tone, subject |
| Advisor receives real beat grid (music-aware planning) | ✅ Implemented | March 2026: BPM passed in, get_beat_grid used when available |
| Creator Mode Creative Brief Intake | ✅ Functional | May 2026: DeepSeek V3 briefing.py alignment layer |
| Structured Music Profiling | ✅ Functional | May 2026: music_profile.py tempo & loudness curve analysis |
| Duration Trim Guard (v15.0) | ✅ Implemented | Precision FFmpeg trim pass to prevent tail music/drift |
| Snapping Mode Separation | ✅ Implemented | Snap disabled in Reference mode, enabled in Prompt Mode |

---

## Creator Mode, Music Profiling & Snapping Updates (May 2026)

### Problem Being Solved
1. **Intake Ambiguity:** In Prompt Mode, writing a raw text description often led to guessing user intent across many conflicting axes (e.g. funny vs. nostalgic, people vs. scenery, caption strategies). 
2. **Music Blindness:** The engine lacked a structured, high-level summary of the music track's emotional energy curve, limiting Prompt Mode's ability to sync narrative holds and drop build-ups to visual clips.
3. **Pacing Jitter in Reference Mode:** Applying beat snapping to Reference Mode visual cuts destroyed the human timing decisions made in the reference video, introducing visual stutter.
4. **Tail Accumulation Drift:** Small millisecond rounding errors across 10-20 visual segments accumulated into a 0.5s-1.0s video length discrepancy, causing audio/video desync and silent endings.

### Changes Made

**1. Creator Mode Intake Assistant (`briefing.py`)**
- Added a dedicated FastAPI endpoint `/api/brief/understand` powered by DeepSeek V3 in `engine/briefing.py`.
- Sits as a non-mutating pre-generation alignment layer.
- Takes the user's rough idea and normalizes it into a formal intake schema containing:
  - `main_intent`, `subject_priority` (people, aesthetic, action, mixed), `emotional_direction` (mood), `pacing_style`, `music_sync_style`, `clip_selection_bias` (emotion, motion, details), `quality_tolerance`, `caption_strategy`, `ending_strategy`, and `avoid_rules`.
- Generates 2-4 highly-targeted clarifying questions to resolve trade-offs before rendering.
- Compiles an internal, optimized "production prompt" for the downstream blueprint generator (`generator.py`).

**2. Structured Music Profiling (`music_profile.py`)**
- Created `engine/music_profile.py` to compile audio features into a high-level LLM context payload.
- Packages raw Librosa outputs (BPM, onsets) with:
  - **Energy Quarters:** Segments the audio into four quadrants and classifies each by energy level (`quiet`, `moderate`, `strong`) with matching cut guidance (`hold longer shots`, `allow shorter cuts`).
  - **Loudness Ranges:** Detects specific quiet/strong ranges and marks phrase boundaries.
- The blueprint generator uses this structured profile to design a narrative blueprint that is intrinsically aligned with the music's structure.

**3. Snapping Mode Separation (`editor.py` & `orchestrator.py`)**
- `allow_beat_snapping` is now set to `False` in Reference Mode:
  - `allow_beat_snapping = cuts_in_segment > 0 and mode != "REFERENCE"`
  - Preserves the original scene changes detected from the reference video exactly.
- Enabled in `PROMPT` mode using a `0.10s` grid tolerance and `BEAT_PHASE_OFFSET = -0.08` seconds to align cuts slightly before tempo hits, mimicking professional editing.

**4. Frame-Exact Render & Trim Guard (`processors.py` & `orchestrator.py`)**
- Upgraded `extract_segment` to be strictly frame-exact (`EXTRACT_FPS = 30.0`), rounding all clip boundaries to frame offsets, passing exact duration via `-t exact_duration`, and mapping PTS in FFmpeg.
- Added a post-concatenate **Duration Trim Guard**: if the concatenated video exceeds the target duration by more than `0.1s`, FFmpeg trims the stream precisely before audio merging.

---

## Targeted Fixes (March 2026) — Candidate Quality & Consistency

Small, targeted changes to improve editorial accuracy without changing architecture.

**1. Advisor memory drift (gemini_advisor.py)**
- Problem: The advisor was updating `used_clips` and `recent_picks` from `selection.alternatives[0]` during precompute. The editor may later commit a different alternative or fall back to mechanical selection, so that "memory" did not reflect the real timeline.
- Fix: Removed all updates to `used_clips` and `recent_picks` in the advisor. The advisor now only returns ranked alternatives. The editor remains the single source of truth for actual clip usage.

**2. Candidate ranking before truncation (moment_selector.py)**
- Problem: Candidates were normalized (max 2 per clip) then truncated to 20 with no ranking, so the advisor could see an arbitrary slice of the pool instead of the best fits.
- Fix: After normalization, candidates are scored with `combined_score = semantic_score * 0.7 + musical_alignment * 0.3`, sorted descending, then truncated to top 20. The advisor now sees the strongest candidates for the segment.

**3. Richer candidate metadata (moment_selector.py)**
- Problem: The per-segment advisor prompt received only clip filename, energy, moment reason, and numeric scores. It lacked the semantic fields needed to reason about continuity (e.g. "friends laughing" → "escalate to celebration").
- Fix: Each candidate payload sent to the prompt now includes `content_description`, `emotional_tone`, and `primary_subject` from clip metadata. Candidate count is unchanged; only metadata is enriched.

**4. Hard clip reuse rule (editor.py)**
- Problem: Clip reuse was enforced via large penalties (100 / 300 / 900). A clip could still win if other bonuses outweighed the penalty, allowing repeats in edge cases.
- Fix: Reuse is now a hard rule: any clip with `clip_usage_count >= 1` is skipped in both the advisor waterfall and the mechanical backfill eligibility. No clip appears more than once per edit.

**5. Advisor receives real beat grid (gemini_advisor.py + editor.py)**
- Problem: Advisor-side moment planning used `beat_grid = []`, so candidate musical alignment was neutral, segment beat count and beat density in the prompt were zero, and the advisor had no rhythm context even when the pipeline had BPM.
- Fix: Editor passes `bpm` into `get_advisor_suggestions`. Advisor builds `beat_grid = get_beat_grid(blueprint.total_duration, bpm)` when BPM is available and passes it into both `_generate_moment_plans_for_hints` and the fresh-hints segment planning path. When no music is available, `beat_grid` remains empty and behavior is unchanged.

---

## Known Issues / Rough Edges

| Issue | Severity | Notes |
|---|---|---|
| Gemini 3 Flash API 504 timeout | Medium | Happens on first-run of new reference/clip on a large set. Retrying usually works. DO NOT switch model — gemini-3-flash-preview is intentional for best multimodal quality. |
| Prompt Mode under-tested | Low | Works but needs more real-world usage to find edge cases. |
| Advisor cache miss on prompt change | Info | Expected. `REFERENCE_CACHE_VERSION` bump invalidates old advisor caches — feature, not bug. |
| Reflector fallback on schema error | Low | Vault sometimes returns minimal fallback if Llama response doesn't match schema. Edit still renders fine. |

---

## V14.7.2 Changes (February 2026) — The Clock-Lock

**Problem:** Floating-point accumulation and fractional PTS drift caused final video to run 0.3–0.5s longer than target. Music cut-off was audible.

**Fixes:**
- `vsync cfr` enforced during standardization → no fractional frame rate containers
- All audio re-encoded to AAC 48kHz during concatenation (no stream-copy)
- `Blueprint.total_duration` is the ground truth. Audio trimmed/padded to match exactly.

---

## V14.0–14.1 Changes — Contextual Moment Selection

**Problem:** Editor was picking clips at their default "best moment" windows regardless of what the specific segment actually needed.

**Fix:** Introduced `MomentCandidate`, `SegmentMomentPlan` data models. The Advisor now proposes moment windows for key segments based on narrative need. Editor selects from these contextually appropriate windows rather than a global "best" window.

**Three Hard Rules introduced:**
1. **Restraint** — Don't commit to a moment window that has been used before.
2. **Hold Authority** — Sacred visual cuts cannot be subdivided.
3. **Music Precedence** — If music energy demands a cut, it takes priority.

---

## V14.7 Changes — Pacing Authority Model

**Problem:** Beat snapping was forcing too many cuts in emotional holds. Editor was acting as a metronome.

**Fixes:**
- Beat snapping is now optional: calculated only when `audio_confidence == "Observed"`.
- Narrative duration is calculated first (from segment schema). BPM snap is applied after, optionally.
- Max gap for beat subdivision: `8.0s` — holds up to 8s never get force-subdivided.

---

## Architecture Quick-Reference (Model → Stage Mapping)

```
Text Prompt ──────────────────────────────────────► DeepSeek V3 (generator.py)
                                                              │
Reference Video ──► FFmpeg cuts + audio → Gemini 3 (brain.py)│
                                                              │
User Clips ──────────────────────────► Gemini 3 (brain.py)   │
                                                              │
All → StyleBlueprint + ClipIndex → DeepSeek V3 (advisor.py) ─┘
                                              │
                                              ▼
                                       Python Editor (editor.py)
                                              │
                                              ▼
                                        FFmpeg Render
                                              │
                                              ▼
                             Groq Llama 3.3 70B (reflector.py)
                                              │
                                              ▼
                                    PipelineResult.json + .mp4
```

---

## API Keys

All keys in `backend/.env`:
- `GEMINI_API_KEY` — Gemini 3 Flash (clip + reference analysis)
- `DEEPSEEK_API_KEY` — DeepSeek V3 (blueprint generation + advisor)
- `GROQ_API_KEY` — Groq / Llama 3.3 70B (vault + director critique)

---

## Constraints (Hard)

1. **MP4 only** — Input clips and references must be MP4.
2. **Vertical video preferred** — Standardized to 1080x1920 (phone clips). System handles horizontal but optimizes for vertical.
3. **English text overlays** — Reference analysis and semantic matching assumes English-language text overlays.
4. **Single-user local** — Session state is in-memory. No multi-tenancy, no cloud deployment currently.
5. **Gemini for video analysis only** — Cannot be substituted with DeepSeek or Llama (text-only models).
6. **AI is Advisor, not Controller** — LLMs define intent. Python math controls all timestamps.

---

## Assumptions

1. Scene detection is accurate — FFmpeg's threshold `0.12` works for social-media edits. May need tuning for very slow dissolves.
2. Beat detection is optional — System falls back gracefully to narrative-only pacing if BPM fails.
3. Segment 1 always starts at 0.0 with `cut_origin = "visual"`.
4. Max emotional hold without forced subdivision: 8.0 seconds.
5. Clips are handpicked by the user — they are ALL usable. System never dismisses a clip entirely.
6. Target duration = reference video audio duration (when music comes from reference).

---

## Roadmap (Future Ideas, Not Committed)

- [ ] Model fallback strategy for Gemini 3 timeouts (e.g., gemini-2.0-flash on 504 error)
- [ ] Cross-fade / dissolve transitions between segments (audio cross-fade is high priority for feel)
- [ ] Recursive refinement — AI suggests what to re-film, user approves, engine re-runs
- [ ] Multi-arc anthology edits ("My Year" style with multiple acts)
- [ ] Web deployment for sharing with beta users (post-demo)
- [ ] Multi-model ensemble voting for clip scoring

*For detailed architecture and data flow, see ARCHITECTURE.md.*
