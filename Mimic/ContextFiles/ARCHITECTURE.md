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

### "Co-Pilot Controllability (The Assistant Editor Model)"
MIMIC rejects the "autonomous black-box AI" approach. It is built as a collaborative co-pilot: the AI acts as a tireless **Assistant Editor** (culling footage, mapping tempos, generating structure, matching metadata, and writing briefs), while the human retains the role of **Executive Director**. Controllability is baked into the engine: the human guides style parameters via a conversational intake loop, sets strict formatting boundaries, and can manipulate timelines and overlay styling non-destructively through editable frontend metadata. AI proposes; human directs.

### Commercial Direction
The goal is to deliver commercial-grade visual editing locally first, validate output quality, and position MIMIC as a high-value SaaS product for creators, marketers, and editors. By solving the primary bottlenecks of short-form editing—combing footage, robotic pacing, and black-box editing constraints—MIMIC is designed to serve as a launch-ready creative partner.

---

## II. Multi-Model Intelligence Stack (Verified from Code)

MIMIC uses a *best model for the job* architecture. NOT Gemini-only.

| Stage | Model | File | Why this model |
|---|---|---|---|
| **Intake / Brief Understanding** | `DeepSeek V3` (`deepseek-chat`) | `briefing.py` | Conversational creative brief synthesis — translates user idea to normalized intake parameters and production brief |
| **Clip Analysis** | `gemini-3-flash-preview` | `brain.py` | Multimodal video understanding — only Gemini 3 can watch raw clips |
| **Reference Analysis** | `gemini-3-flash-preview` | `brain.py` | Same — visual analysis of reference TikTok video |
| **Blueprint Generation (Prompt Mode)** | `DeepSeek V3` (`deepseek-chat`) | `generator.py` | Fast, structured JSON reasoning. Cheaper, deterministic |
| **Advisor (Strategic Director)** | `DeepSeek V3` (`deepseek-chat`) | `gemini_advisor.py` | Same — structured JSON editorial briefs |
| **Vault Report Translation** | `Llama 3.3 70B` via Groq | `reflector.py` | High-quality language generation for human-readable reports |
| **Director's Critique (Reflect)** | `Llama 3.3 70B` via Groq | `reflector.py` | Same — nuanced critical narrative intelligence |
| **Editing Engine** | Python (deterministic) | `editor.py` | AI never controls timestamps. Pure math, score-based matching |

> [!WARNING]
> **HACKATHON MODEL CONSTRAINTS:**
> In `brain.py`, the config strictly specifies `MODEL_NAME = "gemini-3-flash-preview"` and `PRO_MODEL = "gemini-3-pro-preview"`. To prevent false positive blocks, safety filters are overridden globally: `SAFETY_SETTINGS` is set to `BLOCK_NONE` for all categories. If these models are swapped with standard API endpoints (e.g. `gemini-2.0-flash`), the initialization settings will fail unless standard configurations are provided. Keep these models hardcoded during evaluation.

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
        ├── STEP 0 (Creator Mode): understand_brief() via DeepSeek V3 in briefing.py
        │                           Translates user's rough idea into approved intake schema
        │
        ├── STEP 0b (Prompt Mode ONLY): generate_blueprint_from_text() via DeepSeek V3
        │                               Pre-scans clip library BEFORE blueprint generation
        │
        ├── STEP 1: Validate inputs / Setup session dirs
        │
        ├── STEP 2 (Reference Mode): analyze_reference_video() via Gemini 3
        │           FFmpeg scene detection (0.12 threshold) → BPM analysis → Hybrid cut list → Gemini brain analysis
        │           OR
        │           (Prompt Mode): Skip — blueprint already generated in Step 0b
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
        │           extract_segment() (frame-exact 30fps) per clip → concatenate_videos() → Duration Trim Guard (V15.0 trim) → merge_audio_video()
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
│   │   ├── briefing.py             # DeepSeek V3 (Creator Mode intake & brief assistant)
│   │   ├── music_profile.py        # Packages BPM, onsets, and energy quarters
│   │   ├── text_safety.py          # Plain-text sanitization utility
│   │   ├── generator.py            # DeepSeek V3 (Prompt Mode blueprint)
│   │   ├── gemini_advisor.py       # DeepSeek V3 (editorial brief + advisor scoring)
│   │   ├── gemini_advisor_prompt.py # The actual ADVISOR_PROMPT template string
│   │   ├── gemini_moment_prompt.py # Moment analysis prompt
│   │   ├── editor.py               # Python matching + V15.0 Vibe scoring engine
│   │   ├── moment_selector.py      # V14.0 contextual moment selection engine
│   │   ├── creative_director.py    # Additional creative layer (music-sync analysis)
│   │   ├── reflector.py            # Groq Llama 3.3 70B (critique + vault translation)
│   │   ├── processors.py           # FFmpeg + Librosa wrappers
│   │   ├── stylist.py              # Text overlay + color grading application
│   │   ├── ENGINE_AUDIT_AND_CLEANUP.txt # Diagnostic state snapshot
│   │   └── vault_compiler.py       # Compiles structured reasoning data for vault
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

## VI.B Contextual Moments: Overlap Penalties and Chaining Mechanics

Moment selection and timing are governed by exact mathematical penalties and fallback loops to maximize variety while maintaining timeline integrity.

### 1. Moment-Level Overlap Penalty Math
When evaluating a clip candidate for a segment, the editor compares the candidate's planned window $[S_{plan}, E_{plan}]$ against all already committed actual intervals $[S_{used}, E_{used}]$ for that clip. It computes the **Overlap Ratio** ($R_{overlap}$):

$$S_{overlap} = \max(S_{plan}, S_{used})$$
$$E_{overlap} = \min(E_{plan}, E_{used})$$
$$D_{overlap} = \max(0, E_{overlap} - S_{overlap})$$
$$R_{overlap} = \frac{D_{overlap}}{E_{plan} - S_{plan}}$$

The system applies the following hard/soft penalties:
*   **$R_{overlap} > 80\%$ (Exact Overlap):** Returns `-999.0` (Hard forbidden, tagged as `🚫SAME_MOMENT`).
*   **$R_{overlap} > 30\%$ (Partial Overlap):** Returns `-200.0` in `REFERENCE` mode or `-100.0` in `PROMPT` mode (tagged as `⚠️OVERLAP_{ratio}%`).
*   **$R_{overlap} \le 30\%$ (Safe Cut):** `0.0` penalty.

### 2. Candidate Pre-filtering and Sorting Math
Before passing segment candidates to the Advisor, `moment_selector.py` normalizes candidates (max 2 per unique clip), ranks them using a combined scoring system, and truncates the list to fit within token thresholds:

$$\text{Combined Score} = (\text{Semantic Score} \times 0.7) + (\text{Musical Alignment} \times 0.3)$$

Only the **Top 20** sorted candidates are passed to the Advisor. Enriched candidate payloads sent to the prompt include `content_description`, `emotional_tone`, and `primary_subject` for sequential continuity.

### 3. Moment Chaining Clip-Switch Rule
If a selected clip's best moment duration is shorter than the segment's required duration ($D_{segment}$), the engine loops to chain consecutive moments until the remaining gap is filled (within a $0.05$s tolerance).
*   To prevent endless looping and guarantee visual variety, the engine tracks `same_clip_count`.
*   If the primary clip is selected $\ge 2$ times within the loop, the system forces `force_different_clip = True`.
*   This triggers a fallback search that excludes the current clip and chains a moment from a different clip entirely.

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

### CDE (Cut Density Expectation) Voting Engine
Derived per-segment with **no AI calls**. In `PROMPT` mode, the CDE is read directly from the blueprint, defaulting to `Moderate`. In `REFERENCE` mode, it is calculated deterministically via a weighted voting engine:

#### 1. Input Signals and Biases
*   **Cut Origin:** If `cut_origin == 'beat'` $\rightarrow$ `origin_bias = "Dense"`. Else `origin_bias = "Moderate"`.
*   **Expected Hold:**
    *   `Long` $\rightarrow$ `hold_bias = "Sparse"`
    *   `Normal` $\rightarrow$ `hold_bias = "Moderate"`
    *   `Short` $\rightarrow$ `hold_bias = "Dense"`
*   **Local Beat Density ($D_{beat}$):** Measured as $D_{beat} = \text{beats\_in\_segment} / \text{duration}$.
    *   $D_{beat} < 0.5$ beats/sec $\rightarrow$ `beat_bias = "Sparse"`
    *   $D_{beat} < 1.5$ beats/sec $\rightarrow$ `beat_bias = "Moderate"`
    *   $D_{beat} \ge 1.5$ beats/sec $\rightarrow$ `beat_bias = "Dense"`
*   **Global Peak Context:**
    *   If `arc_stage == 'Peak'` and global `peak_density == 'Dense'` $\rightarrow$ `peak_bias = "Dense"`
    *   If `arc_stage == 'Intro'` and global `peak_density == 'Sparse'` $\rightarrow$ `peak_bias = "Sparse"`
    *   Else $\rightarrow$ `peak_bias = "Moderate"`

#### 2. Weighted Voting Equation
The system instantiates a tally `votes = {"Sparse": 0, "Moderate": 0, "Dense": 0}` and evaluates:

$$\text{votes}[\text{hold\_bias}] \leftarrow \text{votes}[\text{hold\_bias}] + 3$$
$$\text{votes}[\text{beat\_bias}] \leftarrow \text{votes}[\text{beat\_bias}] + 2$$
$$\text{votes}[\text{origin\_bias}] \leftarrow \text{votes}[\text{origin\_bias}] + 1$$
$$\text{votes}[\text{peak\_bias}] \leftarrow \text{votes}[\text{peak\_bias}] + 1$$

#### 3. Overrides & Resolving Ties
*   **Sub-Second Segment Override:** If segment duration $< 1.0\text{s}$, Sparse is forbidden. If Sparse has the most votes, the engine injects a boost: $\text{votes}[\text{Moderate}] \leftarrow \text{votes}[\text{Moderate}] + 2$ to force at least Moderate pacing.
*   **Long Phrase Boost:** If segment duration $> 3.0\text{s}$, `cut_origin == 'beat'`, and the segment contains $> 3$ beats, the engine adds a boost: $\text{votes}[\text{Dense}] \leftarrow \text{votes}[\text{Dense}] + 1$ to honor musical sync.
*   **Ties:** Resolved by static priority hierarchy: `Moderate` > `Sparse` > `Dense`.

---

## VII.B Timeline Mechanics: Snapping, Gaps & Grids

To guarantee frame-level temporal accuracy and emotional resonance, visual edits are merged with beat structures using strict threshold boundaries.

### 1. Hybrid Scene-Beat Snapping Math
Visual cuts from the reference video are loaded and snapped to the nearest audio beat in `orchestrator.py` only if they fall within a tight temporal window:

$$\text{Nearest Beat} = \text{argmin}_{b \in \text{beat\_grid}} | b - T_{scene} |$$

The cut is snapped if and only if:

$$| \text{Nearest Beat} - T_{scene} | < 0.25\text{s} \quad \text{and} \quad \text{Nearest Beat} > 0.1\text{s}$$

*   **If snapped:** The timestamp is set to `Nearest Beat` and tagged `"visual"`.
*   **If not snapped:** The timestamp remains exactly at $T_{scene}$ and is tagged `"visual"`.

### 2. Midpoint Beat Insertion for Stagnant Gaps
To prevent a mechanical metronome look while avoiding static, lifeless edits, the system scans all adjacent scene cut timestamps.
*   If any visual hold gap exceeds $8.0$ seconds (`max_gap`), the system inserts **exactly one** beat-aligned cut in the middle.
*   It calculates $\text{midpoint} = T_{start} + (\text{gap} / 2)$ and identifies the nearest beat `nearest_mid_beat`.
*   If $T_{start} < \text{nearest\_mid\_beat} < T_{end}$, it splits the stagnant segment by adding a new cut at `nearest_mid_beat` with origin `"beat"`.

### 3. Precision Beat Snapping Tolerances and Offset
For sub-segmentation within `editor.py`, cuts are snapped to audio grids with different priorities and boundaries:
*   **Beat Phase Offset:** The engine applies `BEAT_PHASE_OFFSET = -0.08` seconds. Edits are cut $80$ms *before* the physical beat to align with professional human anticipation.
*   **Allow Snapping Rule:** Beat snapping is only allowed if `cuts_in_segment > 0` (disabled on first cut to let drops breathe), `not is_last_cut_of_segment`, and `mode != "REFERENCE"` (reference mode holds are sacred and must not snap).
*   **Snapping Hierarchy:**
    1.  **Onset Grid (Musical Hits):** Snap to nearest onset with a tight tolerance of **$0.08$ seconds**.
    2.  **BPM Grid (Tempo Beats):** Fall back to nearest BPM beat with a tolerance of **$0.12$ seconds**.
*   **Safety Timing Guard:** Any snapped cut must remain inside the segment boundaries with at least **$100$ms** of breathing room from both segment edges and the current timeline cursor.

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

---

## XII. Creator Mode & Creative Brief Intake

To solve the ambiguity of plain-text description prompts in Prompt Mode, MIMIC introduces a conversational alignment layer prior to rendering.

### 1. The Intake Schema
Rough ideas are parsed into a normalized structure (`models.py → BriefRequest`):
- `main_intent`: Core narrative or viewer reaction goal.
- `subject_priority`: `people/faces` | `scenery/aesthetic` | `product/place` | `action` | `mixed`.
- `emotional_direction`: Target mood (warm, funny, high-energy, cinematic).
- `pacing_style` & `music_sync_style`: Pacing intent.
- `clip_selection_bias`: Human moments vs. details vs. aesthetics.
- `quality_tolerance`: Acceptance threshold for shaky or low-light clips.
- `caption_strategy` & `ending_strategy`: Text styling and climax rules.

### 2. Conversational Alignment (briefing.py)
- **DeepSeek V3** analyzes the prompt against current state data.
- **Clarification Loop:** Instead of guessing missing critical details, it returns up to 4 highly-focused questions (with pre-filled options, placing its recommended default first).
- **Production Brief:** Once approved, it compiles these settings into an optimized internal "production prompt" containing explicit instructions on styling, avoids, and blueprint structural bias, which is fed directly into `generator.py`.

---

## XIII. Structured Music Profiling

Music-driven editing is powered by `music_profile.py`, which compiles raw audio metrics (onsets, BPM, spectrogram curves) into a high-level creative blueprint context.

### 1. Profile Compilation Math
- **Quarterly Segmenting:** Cuts the audio into four quarters and averages the RMS loudness ($E_{rms}$).
- **Energy and Pacing Labeling:** Each quarter is assigned a feel and editorial guideline:
  - $E_{rms} < 0.35$ $\rightarrow$ `"quiet"` energy, `"hold longer shots"`.
  - $0.35 \le E_{rms} < 0.70$ $\rightarrow$ `"moderate"` energy, `"use moderate cuts"`.
  - $E_{rms} \ge 0.70$ $\rightarrow$ `"strong"` energy, `"allow shorter beat-driven cuts"`.
- **Quiet & Strong Ranges:** Group contiguous seconds where energy boundaries are breached to identify holds or build-up areas.
- **Phrase Boundaries:** Marks standard 4-beat musical phrase boundaries using the tempo:
  $$\text{phrase\_seconds} = \frac{60}{\text{BPM}} \times 4$$

### 2. Planning Guidance
The structured musical profile is translated into a prompt injection for the blueprint generator, ensuring that generated segments correspond exactly to musical segments (e.g. holds during quiet ranges, peak cuts during strong ranges, drops placed near the peak loudness second).

---

## XIV. Known Design Decisions and Trade-offs

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
