# MIMIC Architecture Documentation

**Version:** V15.0 — The Personal Editor Mode
**Last Updated:** March 2026
**Status:** Consumer Product — Local Use, Startup-track

> Originally built for the Google Gemini API Developer Competition. Now being optimized as a personal creative tool and potential consumer startup. The focus is output quality — edits must look intentional, professionally paced, and emotionally resonant. "Does this look like a proper Instagram reel?" is the primary quality metric.

---

## I. Project Philosophy

### "Vibe over Math"
MIMIC does not follow BPM grids mechanically. It borrows the rhythm, pacing, energy contour, and text overlay intent from a reference video and uses those as *creative inspiration*, not mathematical contracts. The goal is an edit that captures how the reference *felt*, not a pixel-perfect structural clone.

### "Results Over Code Purity"
If an edit looks great, it worked. If it doesn't, it failed. No other metric matters for the consumer version. System optimizations must be in service of better-looking, better-feeling edits.

### "No Repeats, Ever"
A real editor never reuses the same 3 seconds of a clip in the same video. MIMIC enforces this globally—the system tracks which clips were used across the last 20 renders and applies penalties to prevent repetition across sessions.

### "The Right Clip in the Right Place"
Clips must match the edit's narrative. If the text overlay says "it's about the people," the clips should show people. If the reference was nostalgic and slow-building, the edit should feel slow-building. The Advisor layer enforces this semantic coherence.

### Commercial Direction
This project is local-first right now. The plan is to get perfect edits locally, record demo content, gauge interest from real people, and then decide how to build it into a startup product. Perfect local results come first.

---

## II. Multi-Model Intelligence Stack (Verified from Code)

MIMIC uses a *best model for the job* architecture. NOT Gemini-only.

| Stage | Model | File | Why this model |
|---|---|---|---|
| **Clip Analysis** | `gemini-3-flash-preview` | `brain.py` | Multimodal video understanding — only Gemini 3 can watch raw clips |
| **Reference Analysis** | `gemini-3-flash-preview` | `brain.py` | Same — visual analysis of reference TikTok video |
| **Blueprint Generation (Prompt Mode)** | `DeepSeek V3` (`deepseek-chat`) | `generator.py` | Fast, structured JSON reasoning. Cheaper, deterministic |
| **Advisor (Strategic Director)** | `DeepSeek V3` (`deepseek-chat`) | `gemini_advisor.py` | Same — structured JSON editorial briefs |
| **Vault Report Translation** | `Llama 3.3 70B` via Groq | `reflector.py` | High-quality language generation for human-readable reports |
| **Director's Critique (Reflect)** | `Llama 3.3 70B` via Groq | `reflector.py` | Same — nuanced critical narrative intelligence |
| **Editing Engine** | Python (deterministic) | `editor.py` | AI never controls timestamps. Pure math, score-based matching |

### Key Principle: Gemini Never Owns the Timeline
Gemini provides *semantic understanding* only. All timing, duration, and frame-level decisions are made by deterministic Python code in `editor.py` and `processors.py`. Timeline is sacred. AI is an advisor.

---

## III. The 7-Stage Pipeline (Verified from orchestrator.py)

Everything passes through `orchestrator.py → run_mimic_pipeline()`. It is the single entry point.

```
UI / Frontend (Next.js)
        │ HTTP POST + WebSocket (progress events)
        ▼
main.py (FastAPI)
        │
        ▼
orchestrator.py → run_mimic_pipeline()
        │
        ├── STEP 0 (Prompt Mode ONLY): generate_blueprint_from_text() via DeepSeek V3
        │                               Pre-scans clip library BEFORE blueprint generation
        │
        ├── STEP 1: Validate inputs / Setup session dirs
        │
        ├── STEP 2 (Reference Mode): analyze_reference_video() via Gemini 3
        │           FFmpeg scene detection → BPM analysis → Hybrid cut list → Gemini brain analysis
        │           OR
        │           (Prompt Mode): Skip — blueprint already generated in Step 0
        │
        ├── STEP 3: analyze_all_clips() via Gemini 3
        │           Check persistent standardized cache → Standardize new clips only
        │           Builds ClipIndex with full semantic metadata
        │
        ├── STEP 4: match_clips_to_blueprint() via Python editor (+ DeepSeek Advisor)
        │           Advisor generates editorial brief → editor scores all clips per segment
        │           Returns EDL (Edit Decision List)
        │
        ├── STEP 5: Render via FFmpeg
        │           extract_segment() per clip → concatenate_videos() → merge_audio_video()
        │           Duration Trim Guard (v15.0): trim final video if >0.1s over target
        │
        └── STEP 6: Reflect & Vault via Groq (Llama 3.3 70B)
                    reflect_on_edit() → generate_vault_report()
                    All cached by EDL hash for instant subsequent loads
```

### Output Naming Convention
Every pipeline run generates:
- `data/results/{ref_name}_{session_short_id}_v{iteration}.log` — Full pipeline log
- `data/results/{ref_name}_{session_short_id}_v{iteration}.json` — JSON report (PipelineResult)
- `data/results/{ref_name}_{session_short_id}_v{iteration}.mp4` — Final video

---

## IV. Reference Mode vs Prompt Mode

### Reference Mode (Primary Use Case)
- **Input:** A reference TikTok/Reel + user's clips + music (from reference audio or separate file)
- **Goal:** Capture the vibe, pacing, energy, and text overlay intent of the reference. Recreate it using the user's clips.
- **How it works:**
  1. FFmpeg detects exact visual cut timestamps in the reference.
  2. BPM + music energy from the reference audio is extracted.
  3. Gemini watches the entire reference and classifies each segment: energy, arc stage, vibe, expected hold time, audio driver.
  4. Cut origins are tagged: `"visual"` (where the human editor made a real cut) or `"beat"` (drum-machine fills).
  5. **Sacred Cuts (immutable):** Segments with `cut_origin == "visual"` cannot be subdivided by the algorithm. These are real editorial decisions from the reference creator.
  6. DeepSeek Advisor writes an editorial brief based on this analysis.
  7. Editor matches user clips to segments by score.

**Key difference from old system:** "Structure is Sacred" no longer means we try to hit exact timestamps. The total edit duration IS the reference duration (if music is from the reference). But the per-clip pacing can breathe — a 3.5s segment can use a clip from 2s to 4s if the moment is better.

### Prompt Mode
- **Input:** A text description + music file + user's clips
- **Goal:** Generate an edit from scratch using natural language direction.
- **How it works:**
  1. Clips are scanned first. Their dominant vibes and subjects are summarized into a `library_snapshot`.
  2. DeepSeek V3 receives: the text prompt + music BPM + energy curve + library_snapshot.
  3. DeepSeek generates a `StyleBlueprint` — a 4-stage narrative arc (Intro, Build-up, Peak, Outro) tailored to what clips actually exist.
  4. The rest of the pipeline is identical to Reference Mode from STEP 3 onwards.

**Important:** Prompt Mode pre-scans clips BEFORE generating the blueprint. This prevents the AI from designing segments for vibes/subjects that don't exist in the library.

---

## V. The Data Flow & Caching Architecture

### Directory Map
```
Mimic/
├── backend/
│   ├── engine/                     # All AI and processing logic
│   │   ├── orchestrator.py         # Pipeline controller (single entry point)
│   │   ├── brain.py                # Gemini 3 (clip analysis + reference analysis)
│   │   ├── generator.py            # DeepSeek V3 (Prompt Mode blueprint)
│   │   ├── gemini_advisor.py       # DeepSeek V3 (editorial brief + advisor scoring)
│   │   ├── gemini_advisor_prompt.py # The actual ADVISOR_PROMPT template string
│   │   ├── editor.py               # Python matching + V15.0 Vibe scoring engine
│   │   ├── reflector.py            # Groq Llama 3.3 70B (critique + vault translation)
│   │   ├── vault_compiler.py       # Compiles structured reasoning data for vault
│   │   ├── processors.py           # FFmpeg + Librosa wrappers
│   │   ├── stylist.py              # Text overlay + color grading application
│   │   ├── moment_selector.py      # V14.0 contextual moment selection engine
│   │   └── creative_director.py    # Additional creative layer (music-sync analysis)
│   ├── models.py                   # ALL Pydantic schemas — single source of truth
│   ├── main.py                     # FastAPI server + file management endpoints
│   └── utils/                      # API key manager, hashing utilities
│
├── data/
│   ├── cache/
│   │   ├── standardized/           # std_{hash}.mp4 — re-encoded clips (permanent)
│   │   ├── clips/                  # clip_comprehensive_{hash}.json — Gemini clip analysis
│   │   ├── references/             # ref_{hash}.json — Gemini reference analysis
│   │   ├── blueprints/             # blueprint_{hash}.json — DeepSeek blueprint synthesis
│   │   ├── advisor/                # advisor_{ref_hash}_{lib_hash}.json — Advisor brief
│   │   ├── vault/                  # vault_{edl_hash}.json — Vault report
│   │   ├── critiques/              # critique_{edl_hash}.json — Director's critique
│   │   ├── thumbnails/             # thumb_{hash}.jpg — clip thumbnails
│   │   ├── muted/                  # Muted reference copies for fallback analysis
│   │   ├── clip_history.json       # V15.0 Global render history (last 20 uses per clip)
│   │   ├── hash_registry.json      # MD5 fingerprint lookup cache (speed optimization)
│   │   └── active_sessions.json    # In-memory session state persistence
│   │
│   ├── results/                    # All render outputs
│   │   ├── {ref}_{session}_v{n}.mp4   — Final rendered video
│   │   ├── {ref}_{session}_v{n}.log   — Full pipeline log
│   │   └── {ref}_{session}_v{n}.json  — PipelineResult JSON
│   │
│   └── samples/                    # User-uploaded source material
│       ├── clips/                  # User's video clips (vertical phone clips, MP4)
│       ├── reference/              # Reference TikToks/Reels for Reference Mode
│       └── music/                  # Music tracks for Prompt Mode or reference override
│
└── frontend/                       # Next.js 14 UI
    └── app/                        # Studio, Vault, Library pages
```

### Cache Invalidation Rules
- **Clip analysis cache** (`clips/`): Keyed by MD5 content hash. Never re-analyzed unless file content changes.
- **Reference cache** (`references/`): Keyed by MD5 content hash + `REFERENCE_CACHE_VERSION` string. When the prompt changes version, old caches are invalidated.
- **Advisor cache** (`advisor/`): Keyed by `(blueprint_hash + library_hash)`. Re-generated when either the reference blueprint OR the clip library changes.
- **Vault/Critique cache** (`vault/`, `critiques/`): Keyed by EDL content hash. Re-generated when the actual edit decisions change.
- **Standardized clips** (`standardized/`): Keyed by MD5 hash. Clips are FFmpeg-processed once and stored permanently. Re-encoding only happens when the source file itself changes.

---

## VI. The Editor: Scoring System (V15.0)

`editor.py → match_clips_to_blueprint() → score_clip_smart()`

Every clip is scored against every segment. The highest-scoring clip wins the slot.

### Verified Score Table (from code)

| Factor | Points | Condition |
|---|---|---|
| Base score | +100.0 | All clips start here |
| Random tiebreaker | +0.0 to +8.0 | Per clip per segment (prevents identical renders) |
| **Advisor Primary Carrier** | **+60.0** | Clip filename in `recommended_clips` for this arc stage |
| Standard Advisor bonus | Varies (~+20) | `compute_advisor_bonus()` — vibe/intent alignment |
| Advisor dilution penalty | Varies (~-50) | Clip mismatches Advisor's intent-diluting material |
| **Narrative Anchor (V15.0)** | **+8.0 / +3.0** | Subject matches, penalized down from old +15/+5 |
| Narrative mismatch penalty | -3.0 to -8.0 | Context-aware: only penalizes when narrative clearly disagrees |
| Moment-level reuse penalty | -200.0 (Ref) / -100.0 (Prompt) | Same clip moment (within 0.1s overlap) reused |
| Repeat clip penalty | Graduated | `clip_usage_count` and `clip_last_used_at` tracking |
| Global history penalty | Soft virtual usage | `clip_history.json` adds virtual uses for recently-seen clips |

### Hard Clip Reuse Rule (March 2026)
Any clip with `clip_usage_count >= 1` is excluded from eligibility in both the advisor waterfall and the mechanical backfill. No clip appears more than once per edit. The editor is the only source of truth for actual usage.

### Energy Gating (Hard Filter, Not Soft)
Before scoring, `get_eligible_clips()` hard-filters by energy:
- `High` segment → only `High` or `Medium` clips considered
- `Low` segment → only `Low` or `Medium` clips considered
- `Medium` segment → any clip considered

### V15.0 Smart Micro-Cut Moment Selection
For Reference Mode segments under 1.0 seconds:
1. The editor bypasses the default `best_moment` window.
2. It searches all energy windows for the clip and prioritizes `High > Medium > Low`.
3. It refuses to reuse any window within 0.1s tolerance of a previously committed clip interval.
4. Falls back to energy-matched windows if all high-energy windows are recently used.

---

## VII. Pacing Authority and Sacred Cuts

### Sacred Visual Cuts
- Every reference segment has a `cut_origin`: `"visual"` or `"beat"`.
- `"visual"` = FFmpeg detected a real scene change in the reference. This was an intentional human edit decision.
- Segments with `cut_origin == "visual"` **cannot be subdivided**. This prevents mechanical beat-chop pacing from destroying intentional editorial holds.
- `"beat"` = A fill point from the BPM grid where no visual cut existed. These CAN be subdivided if CDE is Dense.

### Director > Metronome
Beat snapping is optional and secondary. Duration comes from narrative intent first:
1. Calculate how long this segment should be based on `expected_hold`, `arc_stage`, and `CDE`.
2. Optionally snap this duration to the nearest beat (only if `audio_confidence == "Observed"`).
3. Beats are ornament. Narrative duration is law.

### CDE (Cut Density Expectation)
Derived per-segment, no AI calls:
- **Sparse** → `expected_hold == Long` OR `beat_density < 0.08/s` → prefer single clip, resist cuts
- **Moderate** → normal hold + moderate beats → allow 1-2 cuts
- **Dense** → `expected_hold == Short` OR `beat_density > 0.20/s` → encourage sub-segmentation

---

## VIII. The Advisor in Detail

Two files work together:
- **`gemini_advisor_prompt.py`** — The `ADVISOR_PROMPT` template string. This is what is sent to DeepSeek.
- **`gemini_advisor.py`** — The execution layer: caches, calls DeepSeek, parses JSON response, generates `AdvisorHints`.

### What the Advisor Does
1. Receives: Blueprint summary (from reference or prompt) + clip library summary + scarcity report.
2. Outputs: A JSON `AdvisorHints` object that contains:
   - `dominant_narrative`: One sentence defining the edit's core meaning.
   - `primary_narrative_subject`: The ONE subject that must dominate (People-Group, Place-Nature, etc.).
   - `subject_lock_strength`: 0.0–1.0 strength of subject enforcement.
   - `arc_stage_guidance`: For each stage (Intro/Build/Peak/Outro), defines: primary emotional carrier, supporting material, intent-diluting material, exemplar clip filenames.
   - `editorial_motifs`: Continuity patterns to reward (e.g., Motion-Carry, Semantic-Resonance).
   - `library_alignment`: Honest audit of library vs. intent (Strengths, Tradeoffs, Gaps).

### Advisor Cache Key
`advisor_{blueprint_hash}_{library_hash}` — Re-generated when either the reference blueprint OR the set of clip filenames changes.

### Advisor Cache Version Check
The advisor checks that the blueprint's `contract.version == REFERENCE_CACHE_VERSION`. If mismatched (prompt changed), it refuses to use stale guidance and triggers regeneration.

### Advisor vs Editor: Source of Truth (March 2026)
The advisor only returns ranked alternatives per segment. It does not update `used_clips` or `recent_picks`; that would reflect predicted picks, not the clip the editor actually commits. The editor is the single source of truth for which clips were used. Per-segment moment candidates sent to the advisor are ranked by `semantic_score * 0.7 + musical_alignment * 0.3`, then truncated to top 20, and each candidate includes `content_description`, `emotional_tone`, and `primary_subject` for continuity reasoning. When BPM is available, the editor passes it into the advisor; the advisor builds the same beat grid used downstream (`get_beat_grid(blueprint.total_duration, bpm)`) so candidate musical alignment and prompt fields (segment beat count, beat density) use real music data rather than empty grid.

---

## IX. The Clock-Lock (V14.7.2)

Frame-level temporal accuracy:
- **30fps CFR:** `fps=30` + `vsync cfr` in FFmpeg. No variable frame rate containers.
- **Audio Sample Lock:** All audio re-encoded to AAC at 48kHz during concatenation. Eliminates micro-clicks and priming sample drift.
- **Video Duration Authority:** Blueprint total_duration is the contract. Audio is trimmed/padded to match video duration exactly.
- **Duration Trim Guard (V15.0):** If concatenated video exceeds `blueprint.total_duration` by >0.1s, FFmpeg trims it precisely before audio merge.

---

## X. Identity Contract (Hash-Based Caching)

- **Identity = MD5 content hash** of the full file, not filename or path.
- Files can be renamed/moved without triggering re-processing.
- `hash_registry.json` stores `(filename, size, mtime) → hash` as a fingerprint shortcut to avoid re-hashing large files.
- All cache artifacts use the hash: `std_{hash}.mp4`, `clip_comprehensive_{hash}.json`, `thumb_{hash}.jpg`.

---

## XI. Global Novelty System (V15.0)

`clip_history.json` in `data/cache/`:
- **On load:** Previous clip uses are read. Each clip gets virtual usage count based on how recently it appeared in a render (capped to soft penalty, not absolute block).
- **On write:** After each successful render, the actual committed clip intervals (`clip_start`, `clip_end`, per filename) are appended to history. Last 20 uses per clip are retained.
- Effect: Running the same reference 5 times produces 5 increasingly different edits as the system explores the full clip library.

---

## XII. Known Design Decisions and Trade-offs

| Decision | Reason |
|---|---|
| Gemini for video analysis ONLY | No other model can watch raw video. DeepSeek/Groq are text-only LLMs. |
| DeepSeek for Blueprint & Advisor | Faster, cheaper, better at structured JSON than Gemini for text-only tasks. |
| Groq (Llama 3.3 70B) for Vault | High-quality language generation for human reports. Groq gives fast inference. |
| Sacred Visual Cuts | Preserves intentional editorial decisions from reference creators. |
| AI never controls timestamps | LLMs are non-deterministic. Timeline math MUST be reproducible. |
| Hash-based caching everywhere | Idempotent. Same content = same result. Works across sessions. |
| Score rebalancing (V15.0) | Make vibe + energy dominate over rigid subject tagging. |
| Random tiebreaker | Ensure variety across multiple renders of the same reference. |

---

*For current system status and recent change history, see SYSTEM_STATE.md.*
*For quick start and setup, see README.md.*
