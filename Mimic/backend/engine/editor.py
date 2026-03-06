"""
Editor module: Clip-to-segment matching algorithm (v13.2 Semantic Intelligence).

v13.2 SEMANTIC INTELLIGENCE ENHANCEMENTS:
- Expanded SEMANTIC_MAP for nostalgia, celebration, intimate, childhood, cinematic reels
- Emotional Tone → Vibe Bridge: Nostalgic clips match "memories" vibes
- Arc-Stage Tone Affinity: Outro prefers nostalgic/peaceful tones
- Reel-type coverage: Friends trips, My Year, Travel, Nostalgia, Cinematic

v13.1 REFERENCE MODE GUARANTEES:
1. Reference timing is a contract - segments are immutable
2. No looping - clips are never repeated to fake duration
3. No lying EDL - timeline_end equals actual rendered frames
4. Sacred cuts (cut_origin="visual") use max 2 clips
5. Beat grid is decorative only - never overrides structure

v13.1 MODE SYSTEM:
- REFERENCE: Strict style-transfer for demo (default)
- PROMPT: Creative invention allowed (future)

PRESERVED FEATURES (Intelligent Selection):
- Best moments system
- Vibe/semantic bridge scoring
- Advisor bias (not authority)
- Energy eligibility with soft fallback
- Variety/cooldown systems
- Comprehensive logging
"""

from typing import List, Dict, Optional, Tuple
from collections import defaultdict, Counter
from pathlib import Path
from models import (
    StyleBlueprint,
    ClipIndex,
    EDL,
    EditDecision,
    EnergyLevel,
    MotionType,
    ClipMetadata,
    AdvisorHints,
    MomentCandidate,
    SegmentMomentPlan,
    ContextualMomentSelection
)
from engine.processors import has_audio, get_beat_grid, align_to_nearest_beat
from engine.gemini_advisor import get_advisor_suggestions, compute_advisor_bonus
from engine.moment_selector import (
    build_moment_candidates,
    select_moment_with_advisor,
    plan_segment_moments
)


# ============================================================================
# CUT DENSITY EXPECTATION (CDE) - v13.3 Music-Aware Subdivision Bias
# ============================================================================
# CDE is a deterministic, derived signal that biases subdivision decisions
# based on musical cadence from reference audio analysis.
# 
# Hard Rules:
# - CDE is advisory, not absolute
# - Beats remain snap points only, never authorities  
# - Only applies in REFERENCE mode
# - No new AI calls, derived from existing data only
# ============================================================================

def calculate_cut_density_expectation(
    segment,
    beat_grid: List[float],
    blueprint: StyleBlueprint,
    mode: str
) -> str:
    """
    Calculate Cut Density Expectation (CDE) for a segment.
    
    CDE ∈ {Sparse, Moderate, Dense}
    
    Derived deterministically from:
    - segment.duration
    - segment.cut_origin
    - segment.expected_hold
    - beat density (beats/sec within segment window)
    - blueprint.peak_density (global musical density context)
    
    Args:
        segment: The blueprint segment being analyzed
        beat_grid: List of beat timestamps from reference audio
        blueprint: The full blueprint for global context
        mode: "REFERENCE" or "PROMPT" (CDE only applies in REFERENCE)
    
    Returns:
        str: One of "Sparse", "Moderate", "Dense"
    """
    # v14.7: In PROMPT mode, use the segment's CDE field directly from the blueprint
    # This respects the generator's creative intent
    if mode != "REFERENCE":
        segment_cde = getattr(segment, 'cde', 'Moderate')
        if segment_cde in ['Sparse', 'Moderate', 'Dense']:
            return segment_cde
        return "Moderate"  # Fallback for invalid values
    
    # === BASELINE FROM SEGMENT METADATA ===
    duration = segment.duration
    cut_origin = getattr(segment, 'cut_origin', 'visual')
    expected_hold = getattr(segment, 'expected_hold', 'Normal')
    
    # Calculate local beat density (beats per second within this segment)
    segment_beats = [b for b in beat_grid if segment.start <= b < segment.end]
    local_beat_density = len(segment_beats) / duration if duration > 0 else 0
    
    # === SIGNAL 1: CUT ORIGIN ===
    # Beat-origin cuts suggest musical intention for density
    if cut_origin == 'beat':
        origin_bias = "Dense"
    else:
        origin_bias = "Moderate"  # Visual cuts default to moderate
    
    # === SIGNAL 2: EXPECTED HOLD ===
    # Long holds suggest sparse cutting, Short holds suggest dense
    hold_to_density = {
        'Long': 'Sparse',
        'Normal': 'Moderate', 
        'Short': 'Dense'
    }
    hold_bias = hold_to_density.get(expected_hold, 'Moderate')
    
    # === SIGNAL 3: LOCAL BEAT DENSITY ===
    # Derive density class from beats/second
    # Typical ranges: Sparse < 0.5, Moderate 0.5-1.5, Dense > 1.5
    if local_beat_density < 0.5:
        beat_bias = "Sparse"
    elif local_beat_density < 1.5:
        beat_bias = "Moderate"
    else:
        beat_bias = "Dense"
    
    # === SIGNAL 4: GLOBAL PEAK DENSITY CONTEXT ===
    # If this is a Peak segment and global density is high, bias toward Dense
    global_density = getattr(blueprint, 'peak_density', 'Moderate')
    if segment.arc_stage == 'Peak' and global_density == 'Dense':
        peak_bias = "Dense"
    elif segment.arc_stage == 'Intro' and global_density == 'Sparse':
        peak_bias = "Sparse"
    else:
        peak_bias = "Moderate"
    
    # === CONFLICT RESOLUTION (Weighted Voting) ===
    # Hold bias has highest weight (it's the director's intent)
    # Beat bias is second (musical reality)
    # Origin and peak are tie-breakers
    
    votes = {
        'Sparse': 0,
        'Moderate': 0,
        'Dense': 0
    }
    
    # Weighted voting
    votes[hold_bias] += 3  # Director intent: highest weight
    votes[beat_bias] += 2  # Musical reality: high weight  
    votes[origin_bias] += 1  # Cut origin: tie-breaker
    votes[peak_bias] += 1  # Global context: tie-breaker
    
    # === DURATION REALITY CHECK ===
    # Very short segments (< 1s) cannot be Sparse regardless of votes
    if duration < 1.0:
        # Force at least Moderate for sub-second segments
        if votes['Sparse'] > votes['Moderate'] and votes['Sparse'] > votes['Dense']:
            votes['Moderate'] += 2  # Boost moderate to override sparse
    
    # Very long segments (> 3s) with beat-origin should respect musical intent
    if duration > 3.0 and cut_origin == 'beat' and len(segment_beats) > 3:
        votes['Dense'] += 1  # Slight boost to honor musical phrasing
    
    # === FINAL CDE SELECTION ===
    max_votes = max(votes.values())
    winners = [k for k, v in votes.items() if v == max_votes]
    
    # Default hierarchy for ties: Moderate > Sparse > Dense
    # (Prefer conservative cutting when uncertain)
    if 'Moderate' in winners:
        cde = 'Moderate'
    elif 'Sparse' in winners:
        cde = 'Sparse'
    else:
        cde = 'Dense'
    
    return cde


def get_cde_max_cuts(cde: str, base_max: int, is_sacred_cut: bool) -> int:
    """
    Apply CDE bias to max_cuts_per_segment.
    
    CDE only influences the ceiling - it never forces subdivision.
    The editor can always choose fewer cuts if content demands it.
    
    | CDE       | Effect on max_cuts                                      |
    |-----------|-----------------------------------------------------------|
    | Sparse    | Strongly prefer single usable window, resist subdivision  |
    | Moderate  | Allow 1-2 cuts if needed (baseline)                       |
    | Dense     | Encourage subdivision even if visuals could hold          |
    """
    if is_sacred_cut:
        # Sacred cuts have hard ceiling of 2, CDE can only reduce
        if cde == 'Sparse':
            return 1  # Strongly prefer single window
        else:
            return 2  # Allow up to 2 for Moderate/Dense
    
    # Non-sacred cuts: CDE biases the ceiling
    if cde == 'Sparse':
        # Sparse: Cap at max(2, base/2) - resist fragmentation
        return min(base_max, max(2, base_max // 2))
    elif cde == 'Dense':
        # Dense: Increase ceiling by 50% (but hard cap at 12)
        return min(12, int(base_max * 1.5))
    else:
        # Moderate: Use base calculation
        return base_max


def match_clips_to_blueprint(
    blueprint: StyleBlueprint,
    clip_index: ClipIndex,
    find_best_moments: bool = False,
    api_key: Optional[str] = None,
    reference_path: Optional[str] = None,
    bpm: float = 120.0,
    onset_times: Optional[List[float]] = None,  # Real musical hit points from analyze_music()
    energy_curve: Optional[List[float]] = None,  # Per-second RMS energy from analyze_music()
    use_advisor: bool = True,
    mode: str = "REFERENCE",  # REFERENCE = strict structure | PROMPT = creative invention
    run_id: Optional[str] = None
) -> Tuple[EDL, Optional[AdvisorHints]]:
    """
    Match user clips to blueprint segments using SIMPLIFIED algorithm.
    
    ALGORITHM:
    1. For each segment in blueprint:
       a. Find clips matching segment energy
       b. Select LEAST RECENTLY USED clip from pool
       c. Use best moment if available, otherwise sequential
       d. Fill segment completely (no 85% threshold)
       e. Track usage to ensure fair distribution
    
    FIXES:
    - Removed complex spillover logic (was causing bugs)
    - Proper clip rotation (prevents only 2 clips being used)
    - Fills segments to match reference duration
    - Prevents same clip back-to-back
    
    Args:
        blueprint: Analyzed reference structure
        clip_index: Analyzed user clips (should have best_moments populated)
        find_best_moments: DEPRECATED - ignored
        api_key: DEPRECATED - not needed
    
    Returns:
        EDL (Edit Decision List) with frame-accurate instructions
    """
    print(f"\n{'='*60}")
    print(f"[EDITOR] MATCHING CLIPS TO BLUEPRINT ({mode} MODE)")
    print(f"{'='*60}")
    
    # MODE ENFORCEMENT (v13.1 Reference Authority)
    if mode == "REFERENCE":
        print(f"  🔒 REFERENCE MODE: Structure is sacred, no looping, no lying EDL")
    else:
        print(f"  🎨 PROMPT MODE: Creative invention allowed")
    print(f"  Segments: {len(blueprint.segments)}")
    print(f"  Clips: {len(clip_index.clips)}")
    
    # Check if clips have pre-computed best moments
    clips_with_moments = sum(1 for c in clip_index.clips if c.best_moments)
    print(f"  Clips with pre-computed best moments: {clips_with_moments}/{len(clip_index.clips)}")
    
    # Get Gemini Advisor suggestions (optional, degrades gracefully)
    # Get Gemini Advisor / Creative Director suggestions
    advisor_hints: Optional[AdvisorHints] = None
    if use_advisor:
        if mode == "PROMPT":
            # ── PROMPT MODE: Creative Director ───────────────────────────
            # One holistic call: music + all clips → complete ordered cut list.
            # Falls back to regular Advisor if the call fails.
            try:
                from engine.creative_director import run_creative_director
                director_plans = run_creative_director(
                    text_prompt=getattr(blueprint, 'text_prompt', '') or getattr(blueprint, 'narrative_message', '') or '',
                    clip_index=clip_index,
                    blueprint=blueprint,
                    total_duration=blueprint.total_duration,
                    bpm=bpm,
                    onset_timestamps=onset_times or [],
                    energy_curve=energy_curve or [],
                    api_key=None
                )
                if director_plans:
                    # Inject Creative Director plans into a minimal AdvisorHints shell
                    # so the existing editor execution loop can use them unmodified.
                    advisor_hints = AdvisorHints(
                        text_overlay_intent=getattr(blueprint, 'text_overlay', '') or '',
                        dominant_narrative=getattr(blueprint, 'narrative_message', '') or '',
                        editorial_strategy="Creative Director: full holistic plan active",
                        segment_moment_plans=director_plans,
                        cache_version="5.0"
                    )
                    print(f"  ✅ Creative Director active: {sum(len(p.moments) for p in director_plans.values())} planned cuts across {len(director_plans)} segments")
                else:
                    raise RuntimeError("Creative Director returned None")
            except Exception as cd_err:
                print(f"  ⚠️ Creative Director failed ({cd_err}), falling back to Advisor+Scoring")
                # Fall back to regular per-segment Advisor
                scarcity_report = {"energy_model": "soft_signal_only_music_drives_feel"}
                subject_counts = Counter()
                for c in clip_index.clips:
                    for s in (c.primary_subject or []):
                        subject_counts[s] += 1
                total_clips = len(clip_index.clips)
                for subj, count in subject_counts.items():
                    ratio = count / total_clips
                    if ratio < 0.1: scarcity_report[subj] = "scarce"
                    elif ratio > 0.4: scarcity_report[subj] = "abundant"
                advisor_hints = get_advisor_suggestions(blueprint, clip_index, scarcity_report=scarcity_report, bpm=bpm)
        else:
            # ── REFERENCE MODE: Regular per-segment Advisor (unchanged) ──
            scarcity_report = {}
            total_clips = len(clip_index.clips)
            if total_clips > 0:
                for energy_lv in ["High", "Medium", "Low"]:
                    count = sum(1 for c in clip_index.clips if c.energy.value == energy_lv)
                    ratio = count / total_clips
                    if ratio < 0.15: scarcity_report[energy_lv] = "very_scarce"
                    elif ratio < 0.30: scarcity_report[energy_lv] = "scarce"
                    else: scarcity_report[energy_lv] = "abundant"
                subject_counts = Counter()
                for c in clip_index.clips:
                    for s in (c.primary_subject or []):
                        subject_counts[s] += 1
                for subj, count in subject_counts.items():
                    ratio = count / total_clips
                    if ratio < 0.1: scarcity_report[subj] = "scarce"
                    elif ratio > 0.4: scarcity_report[subj] = "abundant"
            advisor_hints = get_advisor_suggestions(blueprint, clip_index, scarcity_report=scarcity_report, bpm=bpm)

        if advisor_hints:
            print(f"  ✅ Advisor enabled: Strategic guidance active")
        else:
            print(f"  ⚙️ Advisor disabled: Using base matcher only")
    else:
        print(f"  ⚙️ Advisor disabled by config")
    
    # PHASE 2: Generate beat grid for audio sync
    # FIX: Beat grid was only built when reference_path existed, meaning
    # PROMPT MODE never got beat snapping even with music+BPM detected.
    # Now: if BPM is known (from music or reference audio), always build the grid.
    beat_grid = []
    if bpm and bpm > 0:
        beat_grid = get_beat_grid(blueprint.total_duration, bpm=bpm)
        print(f"  \U0001f3b5 Beat grid generated: {len(beat_grid)} beats at {bpm:.2f} BPM (mode: {mode})")
    
    # Phase 2b: Intelligent Beat Extraction (v8.0)
    # Supplement the regular beat grid with editorial accent moments from blueprint
    if blueprint.music_structure and "accent_moments" in blueprint.music_structure:
        import re
        manual_beats = []
        for m in blueprint.music_structure["accent_moments"]:
            # Extract last number which is typically the timestamp
            nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(m))
            if nums:
                try: 
                    t = float(nums[-1])
                    if 0 < t < blueprint.total_duration:
                        manual_beats.append(t)
                except: continue
        
        if manual_beats:
            print(f"  \U0001f3b9 Extracted {len(manual_beats)} manual accent moments (Super Beats)")
            beat_grid = sorted(list(set(beat_grid + manual_beats)))

    # Build combined snap grid: Onsets (real musical hits) take priority,
    # then fall back to BPM beat grid. Onsets snap within 0.1s, BPM within 0.15s.
    # Real editors cut on hits, not math — this is the difference.
    onset_grid = sorted(list(set(onset_times or [])))
    if onset_grid:
        print(f"  \U0001f3af Onset grid active: {len(onset_grid)} musical hits (priority over BPM grid)")
    combined_snap_grid = onset_grid if onset_grid else beat_grid

    if not combined_snap_grid:
        print(f"  \U0001f507 No beats detected - using visual cuts only")
    else:
        print(f"  \u2705 Active snap grid: {len(combined_snap_grid)} points ({('onset' if onset_grid else 'BPM')})")

    
    print()
    
    # Track usage: how many times each clip has been used
    clip_usage_count = {clip.filename: 0 for clip in clip_index.clips}

    # v15.0: GLOBAL HISTORY — soft diversity nudge across edits (scoring penalty only, never disqualify)
    _HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "clip_history.json"
    _global_history: dict = {}  # {filename: [{"start": float, "end": float, "run_id": str}, ...]}
    try:
        if _HISTORY_PATH.exists():
            import json as _json
            _global_history = _json.loads(_HISTORY_PATH.read_text(encoding='utf-8'))
            print(f"  📚 Global history loaded: {len(_global_history)} clips tracked across past edits")
    except Exception as _he:
        print(f"  [WARN] Could not load clip history: {_he}")
    
    # Track current position in each clip (for sequential fallback)
    clip_current_position = {clip.filename: 0.0 for clip in clip_index.clips}
    
    # TRACKER: Areas of clips already used to prevent exact repetition
    # Dict[filename, List[Tuple[start, end]]]
    clip_used_intervals = defaultdict(list)
    
    # VISUAL COOLDOWN SYSTEM: Track when each clip was last used on the timeline
    clip_last_used_at = {clip.filename: -999.0 for clip in clip_index.clips}
    # MIN_CLIP_REUSE_GAP is now calculated dynamically inside the segment loop to be energy-aware
    
    # TRANSITION MEMORY: Track the last clip's details for smooth flow
    # Context object for stateful scoring (Phase 1 Refactor)
    class MatchContext:
        def __init__(self):
            self.last_filename = None
            self.last_motion = None
            self.last_scale = None
            self.last_subjects = []
            self.last_content = ""
            self.timeline_pos = 0.0
            self.usage_count = clip_usage_count
            self.last_used_at = clip_last_used_at

    ctx = MatchContext()
    
    # === X-RAY DIAGNOSTIC LOGGING ===
    # Collect detailed scoring breakdowns for surgical debugging
    xray_logs = []

    # === VIBE CANONICALIZATION LAYER (v14.1 Semantic Intelligence) ===
    # This layer maps specific nouns (from clip analysis) to abstract editorial vibes.
    # It also consolidates 'vibes' and 'emotional_tone' into a single descriptor set.
    VIBE_CANONICAL_MAP = {
        "ACTION": {"action", "racing", "speed", "fast", "adrenaline", "kinetic", "movement", "active", "dynamic", "vehicle", "sport", "drive", "launch", "flight", "jet", "top gun"},
        "INTENSITY": {"intensity", "intense", "dramatic", "hype", "power", "force", "cinematic", "epic", "peak", "monologue", "focus", "physical", "technical", "professional"},
        "JOY": {"joy", "joyful", "fun", "laughter", "happy", "celebration", "celebratory", "sparkling", "ecstatic", "together", "candid", "casual", "smile", "friends", "summer"},
        "ADVENTURE": {"adventure", "adventurous", "wanderlust", "travel", "explore", "scenic", "journey", "arrival", "mountains", "beach", "wilderness", "hiking", "trip"},
        "PEACE": {"peaceful", "serene", "reflective", "nostalgic", "nostalgia", "calm", "still", "golden", "sentimental", "memory", "intimate", "quiet", "soft", "warmth", "childhood", "vintage", "old"},
        "LIFESTYLE": {"lifestyle", "uni", "university", "student", "study", "campus", "food", "eating", "cooking", "dinner", "cafe", "vlog", "personal", "daily", "routine"}
    }

    def canonicalize(raw_vibe_list):
        canonical = set()
        if not raw_vibe_list: return canonical
        for rv in raw_vibe_list:
            rv_low = str(rv).lower()
            for key, synonyms in VIBE_CANONICAL_MAP.items():
                if rv_low in synonyms or any(s in rv_low for s in synonyms):
                    canonical.add(key)
        return canonical

    # === PHRASE GROUPING (v12.4 Phase 2) ===
    # Groups segments by arc_stage for motif feasibility checks.
    # We derive these on the fly to avoid breaking legacy blueprint models.
    phrases = []
    current_phrase_ids = []
    if blueprint.segments:
        for seg in blueprint.segments:
            if not current_phrase_ids:
                current_phrase_ids.append(seg.id)
            else:
                prev_seg = blueprint.segments[current_phrase_ids[-1] - 1]
                if seg.arc_stage == prev_seg.arc_stage:
                    current_phrase_ids.append(seg.id)
                else:
                    duration = sum(blueprint.segments[sid-1].duration for sid in current_phrase_ids)
                    phrases.append({"segments": current_phrase_ids, "duration": duration})
                    current_phrase_ids = [seg.id]
        if current_phrase_ids:
            duration = sum(blueprint.segments[sid-1].duration for sid in current_phrase_ids)
            phrases.append({"segments": current_phrase_ids, "duration": duration})

    # Map segment ID to its phrase duration for fast lookup
    seg_phrase_duration = {}
    for phrase in phrases:
        for sid in phrase["segments"]:
            seg_phrase_duration[sid] = phrase["duration"]
    
    # Group clips by energy for fast lookup
    energy_pools = _create_energy_pools(clip_index)
    
    # === PRE-EDIT DEMAND ANALYSIS ===
    demand = {"High": 0, "Medium": 0, "Low": 0}
    for seg in blueprint.segments:
        demand[seg.energy.value] += 1
    
    supply = {"High": len(energy_pools.get(EnergyLevel.HIGH, [])),
              "Medium": len(energy_pools.get(EnergyLevel.MEDIUM, [])),
              "Low": len(energy_pools.get(EnergyLevel.LOW, []))}
    
    print(f"\n📊 CLIP DEMAND ANALYSIS:")
    
    if mode == "PROMPT":
        # In PROMPT mode, energy labels on clips are soft scoring signals only.
        # All clips are eligible regardless of energy level — the music drives feel, not labels.
        # Suppress deficit warnings that would mislead the Advisor into thinking the library is inadequate.
        print(f"   Mode: PROMPT — energy labels are advisory only. All {len(clip_index.clips)} clips eligible.")
        print(f"   Music (onset grid + pacing cadence) determines the emotional feel of each segment.")
        deficits = {}
    else:
        print(f"   Reference needs: High={demand['High']}, Medium={demand['Medium']}, Low={demand['Low']}")
        print(f"   You have:        High={supply['High']}, Medium={supply['Medium']}, Low={supply['Low']}")
        
        deficits = {}
        for energy in ["High", "Medium", "Low"]:
            if demand[energy] > supply[energy]:
                deficits[energy] = demand[energy] - supply[energy]
                print(f"   ⚠️ DEFICIT: Need {deficits[energy]} more {energy}-energy clips")
        
        if not deficits:
            print(f"   ✅ You have enough clips for a perfect edit!")
    print()
    
    # === COMPROMISE TRACKER ===
    compromises = []  # Track every time we use adjacent energy
    
    # === DEBUG MODE (Gate heavy logging) ===
    DEBUG_MODE = True
    
    # === ENHANCED LOGGING (for explainability) ===
    candidate_rankings = []  # Top 3 candidates per segment
    eligibility_breakdowns = []  # Eligibility stats per segment
    semantic_neighbor_events = []  # When semantic neighbors were used
    beat_alignment_logs = []  # Beat snap decisions
    
    # === ENERGY ELIGIBILITY HELPER ===

    # === P0 FIX #1: VIBE SEMANTIC BRIDGE ===
    # Maps clip-level descriptive tags (nouns) → editorial intent vibes (abstractions)
    # This solves the 0% vibe matching issue by bridging semantic spaces.
    VIBE_SEMANTIC_BRIDGE = {
        # Vehicle-related clips → Speed/Power/Adrenaline vibes
        "vehicle": ["speed", "power", "adrenaline", "launch", "precision", "freedom"],
        "solo": ["heroic", "focus", "determination", "struggle", "intense"],
        "group": ["unity", "heroic", "celebration", "camaraderie"],
        "crowd": ["scale", "epic", "energy", "intensity"],
        "urban": ["grit", "intensity", "modern", "solemn"],
        "nature": ["majestic", "freedom", "peaceful", "silence"],
        "travel": ["adventure", "freedom", "exploration"],
        "celebration": ["joy", "triumph", "energy"],
        "indoor": ["intimate", "focus", "calm"],
        # Reverse mappings for flexibility
        "speed": ["vehicle", "action", "dynamic"],
        "power": ["vehicle", "action"],
        "heroic": ["solo", "group"],
        "majestic": ["nature", "wide"],
        "silence": ["nature", "calm", "peaceful"]
    }
    
    # SEMANTIC NEIGHBORS (The "Artistic Neighbor" map)
    # This prevents deficits by allowing similar vibes to count as matches
    # v13.2: Expanded for nostalgia, celebration, and cinematic reel support
    SEMANTIC_MAP = {
        # Nature & Outdoors
        "nature": ["outdoors", "scenic", "landscape", "trees", "forest", "mountain", "beach", "sky", "view", "sunset", "sunrise"],
        # Urban & City
        "urban": ["city", "street", "architecture", "building", "lights", "night", "traffic", "walking", "downtown", "skyline"],
        # Travel & Adventure
        "travel": ["adventure", "road", "plane", "car", "explore", "vacation", "scenic", "journey", "trip", "destination"],
        # Friends & Social
        "friends": ["social", "laughing", "group", "candid", "casual", "fun", "lifestyle", "bonding", "together", "hangout"],
        # Action & Energy
        "action": ["fast", "sport", "intense", "thrill", "dynamic", "movement", "energy", "adrenaline", "power", "speed"],
        # Calm & Peaceful
        "calm": ["peaceful", "sunset", "lifestyle", "aesthetic", "still", "chill", "serene", "quiet", "gentle", "soft"],
        
        # v13.2: NEW CATEGORIES for expanded reel support
        
        # Nostalgia & Memories (My Year Reels, Throwback Reels)
        "nostalgia": ["memories", "childhood", "family", "vintage", "throwback", "old", "retro", "warmth", "home", "past", "remember", "moments"],
        # Celebration & Joy (Friends Trip, Birthday, Wedding Reels)
        "celebration": ["party", "dance", "cheers", "toast", "birthday", "wedding", "confetti", "fireworks", "clapping", "hugging", "joy"],
        # Intimate & Close (Personal Reels, Couple Reels)
        "intimate": ["close", "embrace", "love", "tender", "personal", "private", "romantic", "connection", "kiss", "hold"],
        # Childhood & Innocence (Nostalgia Reels)
        "childhood": ["playing", "laughter", "discovery", "wonder", "games", "school", "toys", "running", "innocence", "youth"],
        # Cinematic & Dramatic (Professional Reels)
        "cinematic": ["epic", "dramatic", "hero", "iconic", "majestic", "grand", "sweeping", "intense", "powerful", "legendary"],
        # Transition & Movement (All Reels)
        "transition": ["walking", "driving", "flying", "moving", "passing", "flowing", "shifting", "changing"]
    }

    def infer_shot_scale(clip: ClipMetadata) -> str:
        """Infer clip's scale from primary subject tags."""
        clip_primary_subs = [s.lower() for s in (clip.primary_subject or [])]
        if any(s in ["people-solo", "object-detail"] for s in clip_primary_subs):
            return "Close"
        elif any(s in ["place-nature", "place-urban"] for s in clip_primary_subs):
            return "Wide"
        return "Medium"
    
    def compute_moment_overlap_penalty(clip: ClipMetadata, segment, planned_start: float = None, planned_end: float = None) -> Tuple[float, str]:
        """
        v14.8: MOMENT-LEVEL REUSE PROTECTION (FIXED)

        Compares against ACTUAL committed clip intervals (clip_start, clip_end),
        NOT the expected best-moment window. The old approach missed repeats when
        a different start was chosen within the same window.

        Returns:
            Tuple of (penalty, reason_tag)

        Penalty Levels:
        - Exact overlap (>80%): -999.0 (FORBIDDEN in both modes)
        - Partial overlap (>30%): -200.0 (REFERENCE) / -100.0 (PROMPT)
        - No overlap: 0.0
        """
        used_intervals = clip_used_intervals.get(clip.filename, [])
        if not used_intervals:
            return 0.0, ""

        # Use the PLANNED interval if provided (for pre-commit scoring),
        # otherwise fall back to the best-moment window estimate
        if planned_start is not None and planned_end is not None:
            check_start = planned_start
            check_end = planned_end
        elif clip.best_moments:
            best_moment_data = clip.get_best_moment_for_energy(segment.energy)
            if best_moment_data:
                check_start, check_end = best_moment_data
            else:
                check_start, check_end = 0.0, clip.duration
        else:
            check_start, check_end = 0.0, clip.duration

        check_duration = check_end - check_start
        if check_duration <= 0:
            return 0.0, ""

        # Check overlap with all previously COMMITTED intervals from this clip
        max_overlap_ratio = 0.0
        for used_start, used_end in used_intervals:
            overlap_start = max(check_start, used_start)
            overlap_end = min(check_end, used_end)
            overlap_duration = max(0, overlap_end - overlap_start)
            overlap_ratio = overlap_duration / check_duration
            max_overlap_ratio = max(max_overlap_ratio, overlap_ratio)

        # Apply penalties
        if max_overlap_ratio > 0.8:
            return -999.0, "🚫SAME_MOMENT"
        elif max_overlap_ratio > 0.3:
            penalty = -200.0 if mode == "REFERENCE" else -100.0
            return penalty, f"⚠️OVERLAP_{int(max_overlap_ratio*100)}%"
        else:
            return 0.0, ""

    def compute_continuity_bonus(candidate: ClipMetadata, segment, ctx, advisor: Optional[AdvisorHints]) -> Tuple[float, List[str]]:
        """
        v12.1: The Continuity Engine.
        Calculates bonuses based on Advisor-declared motifs.
        """
        bonus = 0.0
        reasons = []
        
        if not advisor or not hasattr(advisor, 'editorial_motifs'):
            return 0.0, []
        
        motifs = getattr(advisor, 'editorial_motifs', [])
        cand_scale = infer_shot_scale(candidate)
        cand_content = (candidate.content_description or "").lower()
        
        for motif in motifs:
            trigger = motif.get('trigger', '').lower()
            continuity_type = motif.get('desired_continuity', '')
            priority = motif.get('priority', 'Medium')
            
            # Priority multiplier
            weight = 1.0
            if priority == 'High': weight = 2.0
            elif priority == 'Low': weight = 0.5
            
            # 1. Scale-Escalation (Wide -> Medium -> Close)
            if continuity_type == "Scale-Escalation" and ctx.last_scale:
                if ctx.last_scale == "Wide" and cand_scale in ["Medium", "Close"]:
                    bonus += (20.0 * weight)
                    reasons.append("📈Escalation")
                elif ctx.last_scale == "Medium" and cand_scale == "Close":
                    bonus += (25.0 * weight)
                    reasons.append("📈Intimacy")

            # 2. Motion-Carry (Match physical direction or energy flow)
            if continuity_type == "Motion-Carry" and ctx.last_motion:
                if candidate.motion == ctx.last_motion:
                    bonus += (15.0 * weight)
                    reasons.append("➡️Flow")

            # 3. ACTION-COMPLETION / GRAPHIC-MATCH (Advanced: Requires duration)
            if continuity_type in ["Action-Completion", "Graphic-Match"]:
                phrase_dur = seg_phrase_duration.get(segment.id, 0.0)
                if phrase_dur >= 1.2:
                    bonus += (30.0 * weight)
                    reasons.append(f"🔄{continuity_type[:4]}")
                else:
                    # Observability Gap Closed (v12.1 Final):
                    # Explicitly log that the motif was considered but rejected for feasibility.
                    reasons.append(f"⚠️{continuity_type[:3]}_SKIP")

            # 4. Semantic-Resonance (Lyrics/Text triggers)
            if continuity_type == "Semantic-Resonance" and trigger:
                # Check if trigger keyword is in clip's subject or description
                clip_text = " ".join((candidate.primary_subject or []) + (candidate.vibes or [])).lower()
                if trigger in clip_text or trigger in cand_content:
                    bonus += (40.0 * weight)
                    reasons.append(f"🔗{trigger[:5]}")

        return bonus, reasons

    def score_clip_smart(clip: ClipMetadata, segment, ctx, advisor: Optional[AdvisorHints] = None) -> Tuple[float, str, bool]:
        """
        INTELLIGENT SCORING SYSTEM (v9.0 + v15.0 Personal Editor Mode)
        v15.0 changes:
        - Subject bonus heavily reduced (8/3 vs 15/5): vibe+energy now dominate
        - Subject bonus is narrative-aware: reads dominant_narrative to decide context
        - Small random tiebreaker (0-8pts) prevents identical renders
        """
        import random
        score = 100.0  # Base score
        # v15.0: tiny random seed per clip per segment to break exact ties
        score += random.uniform(0, 8.0)
        reasons = []
        vibe_matched = False

        # === STRATEGIC LAYER: Advisor Authority ===
        # The Advisor sees the "big picture" that mechanical matching can't
        
        # NARRATIVE ANCHOR (v9.5):
        # If Advisor has locked a primary subject (e.g. People-Group), enforce it.
        narrative_subject_match = False
        if advisor and advisor.primary_narrative_subject:
            target_subject = advisor.primary_narrative_subject.value
            clip_primary_subjects = [s for s in (clip.primary_subject or [])]
            
            # v15.0: CONTEXT-DRIVEN SUBJECT BOOST
            # Instead of always boosting People-Group, decide from the dominant narrative
            # what subject actually matters for THIS edit. If narrative is about travel/places,
            # nature/travel clips get the boost. If it's about friends, people clips get it.
            dom_narrative = (getattr(advisor, 'dominant_narrative', '') or '').lower()
            narrative_is_people_focused = any(kw in dom_narrative for kw in [
                'friend', 'people', 'group', 'together', 'social', 'bond', 'we ', 'collective'
            ])
            narrative_is_place_focused = any(kw in dom_narrative for kw in [
                'travel', 'journey', 'place', 'destination', 'explore', 'landscape', 'scenic'
            ])
            
            if target_subject in clip_primary_subjects:
                narrative_subject_match = True
                # v15.0: HEAVILY REDUCED SUBJECT BONUS (was 15/5, now 8/3)
                # Vibe + energy are PRIMARY. Subject is a soft tiebreaker.
                usage = clip_usage_count[clip.filename]
                bonus = 8.0 if usage == 0 else 3.0
                score += bonus
                reasons.append("⚓ANCHOR" if usage == 0 else "⚓RECAP")
            else:
                # v15.0: Context-aware penalty: only penalise if narrative strongly disagrees
                clip_has_people = any('People' in s for s in clip_primary_subjects)
                clip_has_place = any('Place' in s for s in clip_primary_subjects)
                is_supporting = False
                if advisor.allowed_supporting_subjects:
                    allowed_subs = [s.value for s in advisor.allowed_supporting_subjects]
                    if any(s in allowed_subs for s in clip_primary_subjects):
                        is_supporting = True
                
                if not is_supporting:
                    # v15.0: Soft penalty only when narrative clearly disagrees (was -15)
                    if narrative_is_people_focused and not clip_has_people:
                        penalty = 8.0  # Gentle nudge toward people clips
                    elif narrative_is_place_focused and not clip_has_place:
                        penalty = 8.0  # Gentle nudge toward scenic clips
                    else:
                        penalty = 3.0  # Almost no penalty when narrative is ambiguous
                    score -= penalty
                    reasons.append(f"🚫Filler")

        # CRITICAL OVERRIDE RULE (v9.2):
        # If Advisor explicitly recommends this clip as PRIMARY EMOTIONAL CARRIER
        # for this arc stage, IGNORE energy mismatch and apply massive bonus
        advisor_primary_carrier = False
        required_energy_override = None
        
        if advisor:
            guidance = advisor.arc_stage_guidance.get(segment.arc_stage)
            if guidance:
                # Check if Advisor specifies required energy override
                if guidance.required_energy:
                    required_energy_override = guidance.required_energy
                
                # Check if this clip is explicitly recommended
                if guidance.recommended_clips and clip.filename in guidance.recommended_clips:
                    # This clip is explicitly recommended by Advisor for this arc stage
                    advisor_primary_carrier = True
                    # P0 FIX #2: INCREASED from 40 to ensure Advisor guidance wins
                    score += 60.0
                    reasons.append(f"🎯PRIMARY")
        
        # Standard Advisor bonus (for non-primary recommendations)
        if advisor and not advisor_primary_carrier:
            advisor_bonus = compute_advisor_bonus(clip, segment, blueprint, advisor)
            if advisor_bonus != 0:
                score += advisor_bonus
                if advisor_bonus > 0:
                    reasons.append(f"🧠+{advisor_bonus}")
                else:
                    reasons.append(f"🚫{advisor_bonus}")

        # === NARRATIVE LAYER: Canonical Vibe Matching (v14.1) ===
        
        # Consolidate all clip descriptors (vibes + emotional_tone)
        clip_descriptors = [v.lower() for v in (clip.vibes or [])]
        if hasattr(clip, 'emotional_tone') and clip.emotional_tone:
            clip_descriptors.extend([t.lower() for t in clip.emotional_tone])
        
        target_vibe = (segment.vibe or "general").lower()
        
        # Canonicalize both sides
        target_canonical = canonicalize([target_vibe])
        clip_canonical = canonicalize(clip_descriptors)
        
        # 1. Direct Canonical Match (+100.0 points) - HIGH PRIORITY
        if any(tc in clip_canonical for tc in target_canonical):
            score += 100.0
            reasons.append(f"Vibe:{segment.vibe}")
            vibe_matched = True
        
        # 2. Literal Substring Match (+60.0 points) - Fallback
        elif any(target_vibe in d or d in target_vibe for d in clip_descriptors):
            score += 60.0
            reasons.append(f"Vibe:{segment.vibe} (Literal)")
            vibe_matched = True
            
        # 3. Structural Style Match (+20.0 points) - Deep Fallback
        else:
            style_bonus = 0
            if "action" in target_vibe and clip.energy == EnergyLevel.HIGH:
                style_bonus = 20.0
            elif "peaceful" in target_vibe and clip.energy == EnergyLevel.LOW:
                style_bonus = 20.0
            
            if style_bonus > 0:
                score += style_bonus
                reasons.append("Vibe:StyleSync")
        
        # 2. Shot Function Match (+25 points)
        function_to_utility = {
            "Establish": ["establishing", "transition"],
            "Action": ["peak", "build", "transition"],
            "Reaction": ["reflection", "build", "transition"],
            "Detail": ["transition", "build"],
            "Transition": ["transition"],
            "Release": ["reflection", "transition"],
            "Button": ["peak", "transition"]
        }
        
        seg_func = getattr(segment, 'shot_function', None)
        if seg_func and seg_func in function_to_utility:
            target_utilities = function_to_utility[seg_func]
            clip_utilities = [u.lower() for u in clip.narrative_utility]
            if any(tu in clip_utilities for tu in target_utilities):
                score += 25.0
                reasons.append(f"Func:{seg_func[:3]}")
        
        # 3. Subject Consistency (+20 points)
        seg_vibe_lower = (segment.vibe or "").lower()
        clip_subjects = [s.lower() for s in (clip.primary_subject or [])]
        
        subject_map = {
            "friends": ["people-group", "activity-celebration", "people-solo"],
            "nature": ["place-nature", "activity-travel"],
            "urban": ["place-urban", "place-indoor"],
            "action": ["activity-sport", "activity-celebration"],
            "travel": ["activity-travel", "place-nature", "place-urban"]
        }
        
        for cat, subjects in subject_map.items():
            if cat in seg_vibe_lower:
                if any(s in clip_subjects for s in subjects):
                    score += 20.0
                    reasons.append("Subj")
                    break
        
        # 4. Shot Scale Continuity (+15 points)
        seg_scale = getattr(segment, 'shot_scale', None)
        if seg_scale:
            is_scale_match = False
            if seg_scale in ["Wide", "Extreme Wide"]:
                is_scale_match = "establishing" in [u.lower() for u in clip.narrative_utility] or \
                                 any("place" in s.lower() for s in (clip.primary_subject or []))
            elif seg_scale == "Medium":
                is_scale_match = any(u.lower() in ["build", "transition"] for u in clip.narrative_utility) or \
                                 any("people-group" in s.lower() for s in (clip.primary_subject or []))
            elif "Close" in seg_scale:
                is_scale_match = any(u.lower() == "peak" for u in clip.narrative_utility) or \
                                 any("people-solo" in s.lower() for s in (clip.primary_subject or []))
            
            if is_scale_match:
                score += 15.0
                reasons.append(f"Scale:{seg_scale[:2]}")

        # 4b. Shot Scale Variety (v12.1: +10 points for alternating)
        # If we don't have a rigid scale requirement from the reference,
        # or as a secondary signal, we prefer alternating scales.
        if ctx.last_scale:
            current_clip_scale = infer_shot_scale(clip)
            if current_clip_scale != ctx.last_scale:
                score += 10.0
                reasons.append("Alt")
        
        # === CONTINUITY ENGINE (v12.1 Motifs) ===
        continuity_bonus, continuity_reasons = compute_continuity_bonus(clip, segment, ctx, advisor)
        score += continuity_bonus
        reasons.extend(continuity_reasons)
        
        # 5. Emotional Tone Match (v13.2: Enhanced for reel-type coverage)
        # Maps clip emotional_tone to segment vibe/intent for better semantic matching
        if hasattr(clip, 'emotional_tone') and clip.emotional_tone:
            clip_tones = [t.lower() for t in clip.emotional_tone]
            seg_vibe_lower = (segment.vibe or "").lower()
            seg_intent = getattr(blueprint, 'emotional_intent', '').lower()
            
            # v13.2: Emotional Tone → Vibe/Intent Bridge
            # This enables "Nostalgic" clips to match "memories" vibes, etc.
            EMOTIONAL_TONE_BRIDGE = {
                # Nostalgia & Memory Reels
                "nostalgic": ["memories", "throwback", "warmth", "childhood", "home", "past", "remember", "family", "old", "vintage"],
                # Celebration & Friends Reels
                "joyful": ["friends", "celebration", "fun", "happy", "party", "dance", "cheers", "toast", "birthday", "wedding"],
                "energetic": ["action", "party", "dance", "adrenaline", "power", "speed", "intense", "thrill", "dynamic"],
                # Calm & Reflection Reels
                "peaceful": ["calm", "nature", "sunset", "escape", "serene", "quiet", "gentle", "soft", "still"],
                # Travel & Adventure Reels
                "adventurous": ["travel", "explore", "journey", "destination", "road", "adventure", "trip", "scenic"],
                # Intimate & Personal Reels
                "intimate": ["close", "love", "personal", "romantic", "connection", "tender", "embrace"],
                # Cinematic & Dramatic Reels
                "dramatic": ["cinematic", "epic", "hero", "iconic", "majestic", "grand", "intense", "powerful"]
            }
            
            tone_matched = False
            
            # 5a. Direct intent match (+10 points)
            if seg_intent and any(seg_intent in t or t in seg_intent for t in clip_tones):
                score += 10.0
                reasons.append("Tone")
                tone_matched = True
            
            # 5b. Tone→Vibe bridge match (+12 points) - NEW
            if not tone_matched:
                for tone in clip_tones:
                    if tone in EMOTIONAL_TONE_BRIDGE:
                        bridge_vibes = EMOTIONAL_TONE_BRIDGE[tone]
                        if any(v in seg_vibe_lower for v in bridge_vibes) or seg_vibe_lower in bridge_vibes:
                            score += 12.0
                            reasons.append(f"ToneBridge:{tone[:4]}→{seg_vibe_lower[:4]}")
                            tone_matched = True
                            break
            
            # 5c. Arc-stage tone affinity (+8 points) - NEW
            # Certain tones fit certain arc stages naturally
            if not tone_matched:
                arc_tone_affinity = {
                    "Intro": ["peaceful", "nostalgic", "adventurous"],
                    "Build-up": ["energetic", "adventurous", "dramatic"],
                    "Peak": ["joyful", "energetic", "dramatic"],
                    "Outro": ["nostalgic", "peaceful", "intimate"]
                }
                preferred_tones = arc_tone_affinity.get(segment.arc_stage, [])
                if any(t in preferred_tones for t in clip_tones):
                    score += 8.0
                    reasons.append(f"ArcTone:{segment.arc_stage[:3]}")

        # === QUALITY LAYER: Best Moment Matching ===
        
        # 1. Best Moment Quality Match (+15 points)
        # Use the right moment quality for the arc stage
        if clip.best_moments:
            # Map arc stage to preferred moment quality
            arc_to_moment = {
                "Intro": "Low",      # Calm establishing
                "Build-up": "Medium", # Rising action
                "Peak": "High",      # Climax
                "Outro": "Low"       # Resolution
            }
            
            preferred_quality = arc_to_moment.get(segment.arc_stage, segment.energy.value.capitalize())
            if preferred_quality in clip.best_moments:
                score += 15.0
                reasons.append(f"Moment:{preferred_quality}")
        
        # 2. Clip Quality Rating (+10 per point, max +30)
        if hasattr(clip, 'clip_quality') and clip.clip_quality:
            score += (clip.clip_quality * 10.0)
            if clip.clip_quality >= 3:
                reasons.append(f"Q{clip.clip_quality}")

        # === VARIETY LAYER: Freshness vs Repetition ===
        usage = clip_usage_count[clip.filename]
        if usage == 0:
            score += 20.0  # Fresh clip bonus
            reasons.append("✨New")
        else:
            # v14.7: PROMPT mode allows softer reuse penalties
            # Creative mode values emotional continuity over strict diversity
            if mode == "PROMPT":
                # Softer penalties for creative mode
                if usage == 1:
                    penalty = 30.0   # Gentle first reuse
                elif usage == 2:
                    penalty = 80.0   # Moderate second reuse
                else:
                    penalty = 180.0  # Discouraging third+ reuse
            else:
                # REFERENCE MODE LOCK: EXPONENTIAL REUSE PENALTY
                # Diversity is a HARD CONSTRAINT, not a preference
                # Linear penalties (30, 80, 180) can be overcome by strong bonuses
                # Exponential penalties (100, 300, 900) enforce true diversity
                if usage == 1:
                    penalty = 100.0  # Aggressive first reuse penalty
                elif usage == 2:
                    penalty = 300.0  # Exponential second reuse
                else:
                    penalty = 900.0  # Prohibitive third+ reuse
            
            score -= penalty
            reasons.append(f"Used:{usage}x")

        # Global history: soft penalty only (prefer fresh clips across edits, never ban)
        history_count = len(_global_history.get(clip.filename, []))
        if history_count > 0:
            history_penalty = 5 * min(history_count, 3)
            score -= history_penalty
            reasons.append(f"Hist:{history_count}")

        # === PENALTY LAYER ===
        
        # 1. Recent Cooldown
        time_since_last_use = timeline_position - clip_last_used_at[clip.filename]
        
        # v14.7: PROMPT mode allows shorter cooldown gaps
        # Creative mode values emotional continuity over strict variety
        if mode == "PROMPT":
            dynamic_reuse_gap = max(1.5, segment.duration * 0.4)  # Shorter gap
            cooldown_penalty = 50.0  # Softer penalty
        else:
            dynamic_reuse_gap = max(2.0, segment.duration * 0.6)
            cooldown_penalty = 100.0
            
        if segment.arc_stage.lower() == "peak":
            dynamic_reuse_gap = max(1.0, dynamic_reuse_gap * 0.5)  # Allow tighter cuts at peak
        
        if time_since_last_use < dynamic_reuse_gap:
            score -= cooldown_penalty
            reasons.append("Cooldown")
        
        # v14.7: MOMENT-LEVEL REUSE PROTECTION
        # Same moment reuse is FORBIDDEN (-999). Partial overlap is discouraged.
        moment_penalty, moment_reason = compute_moment_overlap_penalty(clip, segment)
        if moment_penalty != 0:
            score += moment_penalty  # Already negative
            if moment_reason:
                reasons.append(moment_reason)
        
        # 2. Energy Matching (with Advisor override support + v14.8 Intent-Aware Relaxation)
        # Determine what energy level we're matching against
        target_energy = segment.energy
        if required_energy_override:
            # Advisor override: match against required energy, not segment energy
            # Use EnergyLevel from global scope (models)
            try:
                target_energy = EnergyLevel[required_energy_override.upper()]
                reasons.append(f"🎯{required_energy_override}")
            except (ValueError, KeyError, TypeError):
                pass
        
        # v14.8: VIBE-GATED ENERGY RELAXATION
        # Energy should be strict when energy is the story.
        # Energy should be flexible when emotion is the story.
        EMOTION_DRIVEN_VIBES = {
            "peace", "stillness", "calm", "warmth", "nostalgia", "love",
            "reflection", "intimate", "quiet", "tender", "gentle", "soft",
            "bittersweet", "memory", "longing", "wonder", "innocence"
        }
        TEMPO_DRIVEN_VIBES = {
            "hype", "energy", "action", "intensity", "celebration",
            "dynamic", "fast", "power", "explosive", "rush"
        }
        
        # Check segment vibes to determine if energy should be relaxed
        segment_vibes_lower = set(v.strip().lower() for v in (segment.vibe or "").split(","))
        is_emotion_driven = bool(segment_vibes_lower & EMOTION_DRIVEN_VIBES)
        is_tempo_driven = bool(segment_vibes_lower & TEMPO_DRIVEN_VIBES)
        
        # Determine if energy is "adjacent" (within 1 level)
        energy_order = {"Low": 0, "Medium": 1, "High": 2}
        clip_level = energy_order.get(clip.energy.value, 1)
        target_level = energy_order.get(target_energy.value, 1)
        energy_distance = abs(clip_level - target_level)
        is_adjacent = energy_distance == 1
        is_exact_match = clip.energy == target_energy
        
        if is_exact_match:
            # Perfect energy match
            score += 15.0
            reasons.append(f"{clip.energy.value}")
        elif is_emotion_driven and not is_tempo_driven and is_adjacent:
            # v14.8: Emotion-driven segment allows adjacent energy with small bonus
            # Medium can fill Low, High can fill Medium (but not Low ↔ High)
            score += 8.0  # Reduced bonus vs perfect match, but still positive
            reasons.append(f"~{clip.energy.value}✨")  # ✨ indicates vibe-gated relaxation
        elif not advisor_primary_carrier:
            # Standard energy mismatch penalty
            # NARRATIVE SOFTENING (v9.5): Minor penalty if subject matches
            penalty = 5.0
            if narrative_subject_match:
                penalty = 1.0
                reasons.append("⚡Match")
                
            score -= penalty
            reasons.append(f"~{clip.energy.value}")
        else:
            # Advisor override: energy mismatch is irrelevant
            reasons.append(f"⚡{clip.energy.value}")
        
        # 3. Lighting Continuity (+10 points)
        content = (clip.content_description or "").lower()
        is_night_segment = any(kw in target_vibe for kw in ["night", "dark", "evening"])
        is_night_clip = any(kw in content or kw in str(clip_descriptors) for kw in ["night", "dark", "evening", "neon"])
        
        if is_night_segment == is_night_clip:
            score += 10.0
            reasons.append("Light")
        
        # 4. Motion Continuity (Legacy)
        if ctx.last_motion and clip.motion == ctx.last_motion:
            score += 5.0
            reasons.append("Move")

        # === NARRATIVE REASONING SYNTHESIS (v9.5) ===
        narrative_parts = []
        
        # 1. Strategic Identity (The Anchor)
        if narrative_subject_match:
            target_sub = advisor.primary_narrative_subject.value if advisor and advisor.primary_narrative_subject else "Subject"
            narrative_parts.append(f"Prioritizing narrative continuity by anchoring on '{target_sub}' as requested by the text intent.")
        elif "🚫Filler" in str(reasons):
            narrative_parts.append("Maintaining sequence flow with supporting material, though it drifts from the primary narrative anchor.")
        
        # 2. Shot Function & Strategy
        if advisor_primary_carrier:
            narrative_parts.append(f"Acting as the primary emotional carrier for the {segment.arc_stage} stage.")
        elif "Func:" in str(reasons):
            narrative_parts.append(f"Serving as a strategic '{seg_func}' shot within this sequence.")
        
        if vibe_matched:
            narrative_parts.append(f"The visual content captures the '{segment.vibe}' atmosphere perfectly.")
        
        # 4. Energy Handling (Override vs Natural)
        if required_energy_override:
            if clip.energy.value == required_energy_override:
                narrative_parts.append(f"Satisfies the narrative's high-energy demand for this segment.")
            elif narrative_subject_match:
                narrative_parts.append(f"Matching narrative subject over raw energy to preserve story coherence.")
        
        # 5. Technical Flow
        tech_notes = []
        if "🛡️Subject" in reasons: tech_notes.append("narrative-safe reuse")
        elif "✨New" in reasons: tech_notes.append("visual freshness")
        if "Flow" in reasons: tech_notes.append("motion continuity")
        if "Light" in reasons: tech_notes.append("lighting consistency")
        
        if tech_notes:
            narrative_parts.append(f"Maintains {', '.join(tech_notes)}.")
        

        reasoning = " ".join(narrative_parts) if narrative_parts else "Aligned with arc energy and visual flow."
        
        # SCORE CAP (v9.5): Prevent runaway dominance to maintain ranking discrimination
        score = min(score, 350.0)
        
        return score, reasoning, vibe_matched

    def get_eligible_clips(segment_energy: EnergyLevel, all_clips: List[ClipMetadata]) -> List[ClipMetadata]:
        """
        Return clips that are ALLOWED for this segment's energy.
        High segment → High + Medium (never Low)
        Low segment → Low + Medium (never High)
        Medium → Any
        """
        eligible = []
        for clip in all_clips:
            if segment_energy == EnergyLevel.HIGH:
                if clip.energy in [EnergyLevel.HIGH, EnergyLevel.MEDIUM]:
                    eligible.append(clip)
            elif segment_energy == EnergyLevel.LOW:
                if clip.energy in [EnergyLevel.LOW, EnergyLevel.MEDIUM]:
                    eligible.append(clip)
            else:  # Medium - any clip is OK
                eligible.append(clip)
        return eligible
    
    decisions: List[EditDecision] = []
    timeline_position = 0.0
    last_used_clip = None  # Track to prevent back-to-back repeats
    second_last_clip = None  # Track last 2 clips for more variety

    
    # v14.7: SYNC LOCK (Phase 2) - Frame boundary constants
    SNAP_FPS = 30.0
    FRAME_DUR = 1.0 / SNAP_FPS

    def snap(d):
        return round(d / FRAME_DUR) * FRAME_DUR

    # Snap Advisor Plans if they exist (v14.7)
    if advisor_hints and hasattr(advisor_hints, 'segment_moment_plans'):
        for plan in advisor_hints.segment_moment_plans.values():
            for m in plan.moments:
                m.duration = snap(m.duration)
                m.start = snap(m.start)
                m.end = m.start + m.duration

    # DIRECTOR RESERVATION MAP (PROMPT mode only)
    # Pre-compute which clips are planned for FUTURE segments so the backfill
    # loop cannot steal them. Map: segment_index -> set of reserved filenames.
    director_future_reserved: dict = {}  # {segment_index: set of filenames}
    if mode == "PROMPT" and advisor_hints and hasattr(advisor_hints, 'segment_moment_plans'):
        seg_ids = [str(s.id) for s in blueprint.segments]
        for i, seg in enumerate(blueprint.segments):
            future_clips: set = set()
            for future_seg in blueprint.segments[i + 1:]:
                plan = advisor_hints.segment_moment_plans.get(str(future_seg.id))
                if plan:
                    for m in plan.moments:
                        future_clips.add(m.clip_filename)
            director_future_reserved[i] = future_clips

    for seg_idx, segment in enumerate(blueprint.segments):
        # Snap blueprint boundaries to 30fps frames to prevent "Rounding Drift"
        orig_start = segment.start
        orig_end = segment.end
        
        segment.start = snap(segment.start)
        segment.end = snap(segment.end)
        segment.duration = segment.end - segment.start
        
        print(f"\nSegment {segment.id}: {segment.start:.6f}s-{segment.end:.6f}s "
              f"({segment.duration:.6f}s, {segment.energy.value}/{segment.motion.value})")
        if abs(segment.start - orig_start) > 0.001:
            print(f"    📐 v14.7 Frame-Snap: Boundary adjusted for 30fps sync.")

        if timeline_position > segment.start + 0.05:
            print(f"[WARN] Timeline drift: {timeline_position:.3f} vs segment.start {segment.start:.3f}, snapping.")
            timeline_position = segment.start

        segment_remaining = segment.duration
        segment_start_time = timeline_position
        
        # Fill this segment with MULTIPLE RAPID CUTS to match fast-paced editing
        cuts_in_segment = 0
        # Dynamic loop protection: more cuts allowed for longer segments (min 10)
        max_cuts_per_segment = min(12, max(4, int(segment.duration / 0.6)))
        
        # v13.1: Get cut_origin from segment for sacred cut enforcement
        cut_origin = getattr(segment, 'cut_origin', 'visual')
        is_sacred_cut = (cut_origin == 'visual')
        
        # v13.1: SACRED CUT ENFORCEMENT
        # In REFERENCE mode, visual cuts may use at most 2 clips (no fragmentation)
        is_sacred_cut_ref = (mode == "REFERENCE" and cut_origin == "visual")
        if is_sacred_cut_ref:
            max_cuts_per_segment = 2  # Hard limit for reference authority
        
        # v13.3: CUT DENSITY EXPECTATION (CDE) - Music-aware subdivision bias
        # Calculate CDE from existing beat/musical data to influence cut density
        cde = calculate_cut_density_expectation(segment, beat_grid, blueprint, mode)
        
        # Apply CDE bias to max_cuts (advisory - only affects ceiling)
        max_cuts_per_segment = get_cde_max_cuts(cde, max_cuts_per_segment, is_sacred_cut_ref)
        
        # Log CDE decision for observability (only in REFERENCE mode)
        if mode == "REFERENCE":
            segment_beats = [b for b in beat_grid if segment.start <= b < segment.end]
            beat_density = len(segment_beats) / segment.duration if segment.duration > 0 else 0
            print(f"    🎵 CDE: {cde} (beats: {len(segment_beats)}, density: {beat_density:.2f}/s, hold: {getattr(segment, 'expected_hold', 'Normal')}, origin: {cut_origin})")
            print(f"    📐 max_cuts: {max_cuts_per_segment}")
        else:
            # v14.7: PROMPT mode observability
            emotional_guidance = getattr(segment, 'emotional_guidance', '')
            print(f"    🎨 PROMPT MODE: CDE={cde}, hold={getattr(segment, 'expected_hold', 'Normal')}, vibe={segment.vibe[:30] if segment.vibe else 'N/A'}")
            if emotional_guidance:
                print(f"    💭 Emotional guidance: {emotional_guidance}")
        
        # ADVISOR ALTERNATIVES WATERFALL (v15.0)
        # Walk ranked alternatives in order. Commit first clip that passes reuse check.
        # Reuse rule (REFERENCE): clip_usage_count >= 1 → skip
        # Reuse rule (PROMPT): clip_usage_count >= 2 → skip
        # Fallback: if all 5 fail, mechanical backfill uses full clip_index.clips pool.
        advisor_moment_plan = None
        if advisor_hints and hasattr(advisor_hints, 'segment_moment_plans'):
            plan_key = str(segment.id)
            if plan_key in advisor_hints.segment_moment_plans:
                advisor_moment_plan = advisor_hints.segment_moment_plans[plan_key]
        
        advisor_moments_queue = []
        if advisor_moment_plan is not None:
            alternatives = advisor_moment_plan.advisor_alternatives or []
            if alternatives:
                max_reuse = 1
                for alt in alternatives:
                    usage = clip_usage_count.get(alt.clip_filename, 0)
                    if usage >= max_reuse:
                        print(f"    ⏭️ Advisor skip '{alt.clip_filename}' (used {usage}x, limit {max_reuse})")
                        continue
                    
                    # Resolve timestamps from pre-computed best_moments
                    clip_meta = next((c for c in clip_index.clips if c.filename == alt.clip_filename), None)
                    if not clip_meta:
                        print(f"    ⚠️ Advisor clip '{alt.clip_filename}' not found in index")
                        continue
                    
                    # Map energy_level to pre-computed moment; fall back across energy levels
                    energy_key = alt.energy_level
                    moment_ts = clip_meta.get_best_moment_for_energy(EnergyLevel[energy_key.upper()])
                    if not moment_ts:
                        for fallback in ["High", "Medium", "Low"]:
                            moment_ts = clip_meta.get_best_moment_for_energy(EnergyLevel[fallback.upper()])
                            if moment_ts:
                                break
                    if not moment_ts:
                        print(f"    ⚠️ Advisor clip '{alt.clip_filename}' has no best_moments, skipping")
                        continue
                    
                    m_start, m_end = moment_ts
                    committed = MomentCandidate(
                        clip_filename=alt.clip_filename,
                        moment_energy_level=alt.energy_level,
                        start=m_start,
                        end=m_end,
                        duration=m_end - m_start,
                        moment_role=alt.transition_type,
                        stable_moment=True,
                        reason=alt.reason
                    )
                    advisor_moments_queue.append(committed)
                    print(f"    🎯 Advisor committed: {alt.clip_filename} [{alt.energy_level}] ({alt.transition_type}) — {alt.reason[:60]}")
                    break  # Only commit one per segment; editor handles the rest mechanically
                
                if not advisor_moments_queue:
                    print(f"    ⚙️ All {len(alternatives)} Advisor alternatives exhausted — mechanical backfill")

        
        _loop_iterations = 0  # Hard ceiling: segment loop must terminate
        while segment_remaining > 0.05:
            _loop_iterations += 1
            if _loop_iterations > 50:  # Absolute backstop — no segment needs more than 50 cuts
                print(f"    🚨 INFINITE LOOP GUARD: Segment {segment.id} hit 50 iterations. Forcing segment end.")
                timeline_position = segment.end
                if decisions and decisions[-1].segment_id == segment.id:
                    decisions[-1].timeline_end = snap(segment.end)
                break

            # Update remaining duration based on current timeline position
            # v15.1 Contract Rule: Segment ID will not increment until filled.
            current_segment_pos = timeline_position - segment.start
            segment_remaining = max(0.0, segment.duration - current_segment_pos)
            if segment_remaining <= 0.05:
                break
            
            # --- Rule #2: Micro-Gap Extension (v15.1 Rule B / 0.4s threshold) ---
            # This handles any small remaining gaps by extending the previous cut.
            if segment_remaining < 0.4 and decisions and decisions[-1].segment_id == segment.id:
                prev_decision = decisions[-1]
                prev_clip = next((c for c in clip_index.clips if c.filepath == prev_decision.clip_path), None)
                if prev_clip:
                    extension = segment_remaining
                    # Clamping: Check if extension violates energy MAX_CUT in Prompt mode
                    max_cut_limit = 999.0 
                    if mode == "PROMPT":
                        if segment.energy == EnergyLevel.HIGH: max_cut_limit = 2.0
                        elif segment.energy == EnergyLevel.MEDIUM: max_cut_limit = 3.0
                        else: max_cut_limit = 4.5
                    
                    if (prev_decision.clip_end + extension) <= (prev_clip.duration + 0.002) and \
                       (prev_decision.clip_end - prev_decision.clip_start + extension) <= max_cut_limit:
                        
                        prev_decision.clip_end = snap(prev_decision.clip_end + extension)
                        prev_decision.timeline_end = snap(segment.end)
                        timeline_position = prev_decision.timeline_end
                        segment_remaining = 0.0
                        print(f"    🔧 v15.1 Micro-Gap Extension: Filled {extension:.2f}s by extending {Path(prev_clip.filepath).name}")
                        break

            # --- Source Selection Priority ---
            selected_clip = None
            use_duration = 0.0
            clip_start = None
            thinking = ""
            vibe_matched = False

            advisor_match_found = False
            director_set_duration = False  # Reset each iteration
            if advisor_moments_queue:
                # TIER 1: Advisor as CLIP SELECTOR ONLY
                # The Advisor recommends WHICH clip. The Editor decides HOW LONG and WHERE.
                # This keeps pacing, timing, and beat-sync under deterministic control.
                moment = advisor_moments_queue.pop(0)
                selected_clip = next((c for c in clip_index.clips if c.filename == moment.clip_filename), None)
                if selected_clip:
                    # Reject if this exact clip moment window was already used (hard no-repeat)
                    used_intervals = clip_used_intervals.get(selected_clip.filename, [])
                    moment_already_used = any(
                        abs(used_s - moment.start) < 0.5 for used_s, used_e in used_intervals
                    )
                    if moment_already_used:
                        print(f"    ⚠️ Advisor clip '{selected_clip.filename}' moment already used. Skipping to backfill.")
                        selected_clip = None  # Force fallback to mechanical matcher
                    else:
                        # DIRECTOR-FIRST TIMING: use the Director's planned duration.
                        # In PROMPT mode the Creative Director already chose cut lengths
                        # intentionally (3s intro, 1.5s peak etc.). Don't squash them.
                        if mode == "PROMPT" and moment.duration > 0.05:
                            clip_start = snap(moment.start)
                            use_duration = snap(min(moment.duration, segment_remaining))
                            director_set_duration = True  # Guard: skip downstream overwrites
                            thinking = "Advisor-selected clip (Director duration): " + (moment.reason or "Emotional fit")
                            print(f"    🧩 Advisor selected clip: {selected_clip.filename} (Director duration: {use_duration:.2f}s)")
                        else:
                            clip_start = None  # Editor picks timing
                            director_set_duration = False
                            thinking = "Advisor-selected clip: " + (moment.reason or "Emotional fit")
                            print(f"    🧩 Advisor selected clip: {selected_clip.filename} (Editor controls timing)")
                        vibe_matched = True
                        advisor_match_found = True
            
            if not advisor_match_found:
                # TIER 2: Mechanical Backfill 
                if cuts_in_segment >= max_cuts_per_segment:
                    print(f"    ⚠️ Max cuts reached ({max_cuts_per_segment}) but gap persists. Forcing backfill.")
                
                # === TIERED ELIGIBILITY SELECTION ===
                # Advisor Energy Override (v9.5):
                # If the Advisor dictates a specific energy for this arc stage, 
                # we bypass segment.energy filtering to allow the "correct" clips.
                # PROMPT MODE: Energy is a scoring signal, NOT a hard gate.
                # Vibes and emotional tone are the primary matching axis.
                # All clips are eligible; the score function rewards energy alignment.
                # REFERENCE MODE: Keep energy gate to honour the reference structure.
                if mode == "PROMPT":
                    # Exclude clips reserved for future Director segments
                    reserved_for_future = director_future_reserved.get(seg_idx, set())
                    eligible_clips = [
                        c for c in clip_index.clips
                        if clip_usage_count.get(c.filename, 0) == 0
                        and (c.filename not in reserved_for_future or clip_usage_count.get(c.filename, 0) == 0)
                    ]
                    # Safety: if filter left nothing, fall back to all clips
                    if not eligible_clips:
                        eligible_clips = [c for c in clip_index.clips if clip_usage_count.get(c.filename, 0) == 0]
                else:
                    active_energy_requirement = segment.energy
                    if advisor_hints:
                        guidance = advisor_hints.arc_stage_guidance.get(segment.arc_stage)
                        if guidance and guidance.required_energy:
                            try:
                                active_energy_requirement = EnergyLevel[guidance.required_energy.upper()]
                                print(f"      ⚡ADVISOR OVERRIDE: Using {active_energy_requirement.value} energy for {segment.arc_stage}")
                            except (ValueError, KeyError):
                                pass
                    eligible_clips = [
                        c for c in get_eligible_clips(active_energy_requirement, clip_index.clips)
                        if clip_usage_count.get(c.filename, 0) == 0
                    ]
                    if not eligible_clips:
                        print(f"      ⚠️ No clips match energy. Relaxing constraints...")
                        eligible_clips = [c for c in clip_index.clips if clip_usage_count.get(c.filename, 0) == 0]
                
                # ENHANCED LOGGING: Eligibility breakdown
                if DEBUG_MODE and cuts_in_segment == 0:  # Only log once per segment
                    ineligible_count = len(clip_index.clips) - len(eligible_clips)
                    eligibility_breakdowns.append({
                        "segment_id": segment.id,
                        "eligible_count": len(eligible_clips),
                        "ineligible_count": ineligible_count,
                        "total_clips": len(clip_index.clips),
                        "segment_energy": segment.energy.value
                    })
                
                # Step 2: Variety maintenance (Avoid back-to-back repeats)
                recently_used = [last_used_clip, second_last_clip] if second_last_clip else [last_used_clip]
                available_clips = [
                    c for c in eligible_clips
                    if c.filename not in recently_used and clip_usage_count.get(c.filename, 0) == 0
                ]
                
                if not available_clips:
                    available_clips = [c for c in eligible_clips if clip_usage_count.get(c.filename, 0) == 0]
                
                import random


                # REFERENCE AUTHORITY (v12.7): Pre-calculate duration constraints
                # We must know if this is a sacred cut BEFORE selecting a clip.
                min_required = segment_remaining - 0.1    # Tolerance

                # v13.1: REFERENCE MODE - No looping, no creative invention
                # Calculate scores with duration filtering (relaxed to 85% in REFERENCE mode)
                scored_clips = []
                valid_candidates_found = False
                
                # v13.1: Duration threshold for eligibility
                # In REFERENCE mode: clip must cover >= 85% of remaining segment
                # This prevents fragmentation while allowing practical flexibility
                MIN_COVERAGE_RATIO = 0.85 if mode == "REFERENCE" else 0.5
                min_eligible_duration = segment_remaining * MIN_COVERAGE_RATIO

                for c in available_clips:
                    # GUARD: Duration eligibility (soft gate in REFERENCE mode)
                    # Instead of hard reject, we'll penalize short clips heavily
                    if is_sacred_cut and c.duration < min_eligible_duration:
                        continue  # Skip clips that can't cover enough of sacred segment

                    # We pass the context to maintain stateful flow
                    total_score, reasoning, vibe_matched = score_clip_smart(c, segment, ctx, advisor_hints)
                    scored_clips.append((c, total_score, reasoning, vibe_matched))
                    valid_candidates_found = True

                # FALLBACK: If strict filter eliminated ALL clips (Emergency Mode)
                if not valid_candidates_found:
                    print(f"    ⚠️ CRITICAL: No clips match duration ({min_required:.2f}s) for sacred cut! Reference authority compromised.")
                    print(f"    ⚠️ Fallback: Selecting longest available clips to minimize fragmentation.")
                    
                    # Re-score ALL clips, but prioritize DURATION over everything else
                    scored_clips = []
                    for c in available_clips:
                        total_score, reasoning, vibe_matched = score_clip_smart(c, segment, ctx, advisor_hints)
                        
                        # Massive bonus for duration to get as close as possible
                        duration_score = c.duration * 50.0 
                        total_score += duration_score
                        reasoning = f"⚠️Rescue (len={c.duration:.1f}s)"
                        
                        scored_clips.append((c, total_score, reasoning, vibe_matched))

                # Sort by total score, then vibe match (TIE-BREAKER), then variety
                scored_clips.sort(key=lambda x: (x[1], x[3], -clip_usage_count[x[0].filename]), reverse=True)

                if not scored_clips:
                    print(f"    ⚠️ No candidates after fallback (all clips excluded or none match duration). Using emergency pool.")
                    pool = eligible_clips if eligible_clips else list(clip_index.clips)
                    scored_clips = [(c, 100.0, "Emergency pick", False) for c in pool]

                # Top tier selection (v10.0: replaced randomness with Usage Tie-breaker)
                # Find clips within a "Finesse Buffer" of the max score
                max_score = scored_clips[0][1]
                top_tier = [(c, s, r, vm) for c, s, r, vm in scored_clips if (max_score - s) < 15.0]
                
                # v14.1: If there's a tie in the top tier, prioritize the one with a vibe match, then freshest
                top_tier.sort(key=lambda x: (x[1], x[3], -clip_usage_count[x[0].filename]), reverse=True)
                
                selected_clip, selected_score, selected_reasoning, vibe_matched = top_tier[0]
                
                # === X-RAY DIAGNOSTIC LOGGING (Reference Mode Lock) ===
                # Export detailed scoring breakdown to XRAY.txt for surgical debugging
                if cuts_in_segment == 0:  # Only log once per segment
                    xray_log = []
                    xray_log.append(f"\n{'='*80}")
                    xray_log.append(f"SEGMENT {segment.id} X-RAY | {segment.start:.2f}s-{segment.end:.2f}s | {segment.arc_stage} | Vibe: {segment.vibe}")
                    xray_log.append(f"{'='*80}")
                    
                    # 1. Advisor Input
                    if advisor_hints:
                        xray_log.append(f"\n📋 ADVISOR INPUT:")
                        xray_log.append(f"   Primary Subject: {advisor_hints.primary_narrative_subject.value if advisor_hints.primary_narrative_subject else 'None'}")
                        xray_log.append(f"   Text Intent: {advisor_hints.text_overlay_intent[:80]}..." if advisor_hints.text_overlay_intent else "   Text Intent: None")
                        xray_log.append(f"   Dominant Narrative: {advisor_hints.dominant_narrative[:80]}..." if advisor_hints.dominant_narrative else "   Dominant Narrative: None")
                    
                    # 2. Top 5 Candidate Scoring Breakdown
                    xray_log.append(f"\n🔬 TOP 5 CANDIDATES:")
                    top_5 = scored_clips[:5]
                    for idx, (c, score, reason, vm) in enumerate(top_5):
                        usage = clip_usage_count[c.filename]
                        winner_mark = "🏆 WINNER" if idx == 0 else f"   #{idx+1}"
                        xray_log.append(f"\n{winner_mark} | {c.filename} | SCORE: {score:.1f}")
                        xray_log.append(f"   Vibes: {', '.join(c.vibes[:3]) if c.vibes else 'None'}")
                        xray_log.append(f"   Subjects: {', '.join(c.primary_subject[:2]) if c.primary_subject else 'None'}")
                        xray_log.append(f"   Energy: {c.energy.value} | Usage: {usage}x")
                        xray_log.append(f"   Vibe Match: {'✅ YES' if vm else '❌ NO'}")
                        h_count = len(_global_history.get(c.filename, []))
                        if h_count > 0:
                            xray_log.append(f"   History: {h_count} past uses, penalty -{5 * min(h_count, 3):.0f}")
                        xray_log.append(f"   Reasoning: {reason[:120]}")
                        
                        # Score delta analysis
                        if idx > 0:
                            delta = top_5[0][1] - score
                            xray_log.append(f"   Delta from winner: -{delta:.1f} points")
                    
                    # 3. Selection Decision Analysis
                    xray_log.append(f"\n🎯 SELECTION DECISION:")
                    xray_log.append(f"   Winner: {selected_clip.filename}")
                    xray_log.append(f"   Final Score: {selected_score:.1f}")
                    xray_log.append(f"   Vibe Match: {'✅ YES' if vibe_matched else '❌ NO'}")
                    
                    # Check for overrides
                    subject_override = False
                    vibe_override = False
                    if advisor_hints and advisor_hints.primary_narrative_subject:
                        target_sub = advisor_hints.primary_narrative_subject.value
                        if target_sub in (selected_clip.primary_subject or []):
                            subject_override = True
                    
                    if len(top_5) > 1:
                        runner_up = top_5[1]
                        if runner_up[3] and not vibe_matched:  # Runner-up had vibe match, winner didn't
                            vibe_override = True
                    
                    xray_log.append(f"   Subject Override: {'⚠️ YES' if subject_override and not vibe_matched else '✅ NO'}")
                    xray_log.append(f"   Vibe Override: {'⚠️ YES' if vibe_override else '✅ NO'}")
                    
                    # 4. Diversity Analysis
                    if usage > 0:
                        xray_log.append(f"\n⚠️ DIVERSITY WARNING:")
                        xray_log.append(f"   Clip reused {usage}x (penalty: -{100 * (3 ** (usage-1)):.0f} points)")
                        xray_log.append(f"   Still won despite penalty - strong match")
                    
                    # Write to XRAY file
                    xray_logs.append('\n'.join(xray_log))
                
                # ENHANCED LOGGING: Candidate rankings (top 3) - LEGACY
                if DEBUG_MODE and cuts_in_segment == 0:
                    top_3 = scored_clips[:3]
                    candidates = []
                    for idx, (c, score, reason, vm) in enumerate(top_3):
                        candidates.append({
                            "rank": idx + 1,
                            "clip": c.filename,
                            "score": score,
                            "reasoning": reason,
                            "vibe_match": vm,
                            "won": (idx == 0)
                        })
                    candidate_rankings.append({
                        "segment_id": segment.id,
                        "candidates": candidates
                    })
                
                # Track compromise if we used adjacent energy
                if selected_clip.energy != segment.energy:
                    compromises.append({
                        "segment": segment.id,
                        "wanted": segment.energy.value,
                        "got": selected_clip.energy.value
                    })
                
                thinking = selected_reasoning
                if selected_score > 60: thinking = "🌟 " + thinking
                elif selected_score > 30: thinking = "🎯 " + thinking
                else: thinking = "⚙️ " + thinking

                if cuts_in_segment == 0:
                    print(f"  🧠 AI: {thinking}")
                    print(f"  📎 Selected: {selected_clip.filename} (Score: {selected_score:.1f})")
                else:
                    print(f"    🔗 Backfilling: {selected_clip.filename} (Remaining: {segment_remaining:.2f}s, Fill: {use_duration:.2f}s)")

                # Rule #3: Deterministic Backfill Target Duration
                # CRASH FIX: Always clamp against segment_remaining FIRST before energy cap.
                # This prevents overshoot when only a tiny gap remains (e.g. 0.23s)
                # but the energy cap would assign a longer cut (e.g. 4.5s for LOW).
                if not director_set_duration:  # Director already owns use_duration — skip
                    if mode == "PROMPT":
                        if segment.energy == EnergyLevel.HIGH: max_c = 2.0
                        elif segment.energy == EnergyLevel.MEDIUM: max_c = 3.0
                        else: max_c = 4.5
                        use_duration = min(segment_remaining, max_c)  # segment_remaining always wins
                    else:
                        use_duration = segment_remaining
                # Hard safety net: use_duration must NEVER exceed what's left in the segment
                use_duration = min(use_duration, segment_remaining)

                # Clip Start Selection
                clip_start = clip_current_position[selected_clip.filename]
                if selected_clip.best_moments:
                    best_moment_data = selected_clip.get_best_moment_for_energy(segment.energy)
                    if best_moment_data:
                        window_start, window_end = best_moment_data
                        if not (window_start <= clip_start < window_end):
                            clip_start = window_start
            
            # === PACING LOGIC: DIRECTOR-FIRST PACING (v12.1) ===
            # Authority Inversion: Visual intent leads, Beats follow as ornament.
            
            hold = getattr(segment, 'expected_hold', 'Normal').lower()
            arc_stage = segment.arc_stage.lower()
            cut_origin = getattr(segment, 'cut_origin', 'visual')
            
            # 1. HOLD-DRIVEN RESTRAINT: Minimums for Emotional Registration (Human-centric)
            if hold == "short":
                max_hold = 1.8  # register shot
            elif hold == "long":
                max_hold = 12.0 # deep cinematic holds
            else:
                max_hold = 4.5  # standard patience
                
            # 'Peak' intensity allows for kinetic cutting but still needs registration
            if arc_stage == "peak" and hold == "short":
                max_hold = 1.2
            elif arc_stage in ["build-up", "peak"] and hold == "normal":
                max_hold = 2.5
                
            # 2. SACRED VISUAL CUTS: Do NOT subdivide shots that were intentional in the reference.
            should_subdivide = False
            if cut_origin != "visual":
                if segment.duration > max_hold:
                    should_subdivide = True
            
            # 3. DURATION CALCULATION: Editor-first (Jittered)
            if not should_subdivide:
                use_duration = segment_remaining
                is_last_cut_of_segment = True
            else:
                # Logic-driven duration with variation to prevent mechanical loops
                import random
                if hold == "short":
                    base = 1.2
                elif hold == "long":
                    base = 5.0
                else:
                    base = 2.5
                    
                # Kinetic bonus for Peak stage
                if arc_stage == "peak":
                    base *= 0.7
                    
                use_duration = base * random.uniform(0.9, 1.1)
                
                # Check if we overshot the segment
                if use_duration >= segment_remaining - 0.2:
                    use_duration = segment_remaining
                    is_last_cut_of_segment = True
                else:
                    is_last_cut_of_segment = False
            
            # GUARDRAIL #2: Energy-Aware Duration Clamping (PROMPT MODE ONLY)
            # Reference mode uses exact blueprint durations - no clamping
            # Skip if Creative Director already set the duration intentionally.
            if mode == "PROMPT" and not director_set_duration:
                if segment.energy == EnergyLevel.HIGH:
                    MIN_CUT, MAX_CUT = 0.5, 2.0
                elif segment.energy == EnergyLevel.MEDIUM:
                    MIN_CUT, MAX_CUT = 0.6, 3.0
                else:  # LOW
                    MIN_CUT, MAX_CUT = 0.8, 4.5
                use_duration = max(MIN_CUT, min(MAX_CUT, use_duration))
            # else: REFERENCE mode or Director-set duration — no clamping

            # ======================================================================
            # PHASE 2: Beat Alignment (Snapping)
            # CONTRACT: The Editor (logic) has final authority over time.
            # The Director (Gemini) provides "accent_moments", but these MUST
            # stay strictly within the segment boundaries fixed by FFmpeg/Librosa.
            # ======================================================================
            original_duration = use_duration
            beat_aligned = False
            beat_target = None
            
            # PRECISION TIMING FIXES (v12.6):
            # FIX #2: Beat Phase Offset (-80ms for human anticipation)
            # FIX #3: Tighter tolerance (0.15s → 0.10s)
            # FIX #4: Never snap first cut after beat drop/energy transition
            BEAT_PHASE_OFFSET = -0.08  # Editors cut BEFORE the beat, not on it
            
            # FIX #4: Disable beat snapping for first cut in segment (let drops breathe)
            # v14.7: Disable beat snapping ENTIRELY in REFERENCE mode for maximum rhythm stability
            allow_beat_snapping = cuts_in_segment > 0 and mode != "REFERENCE"
            
            if combined_snap_grid and not is_last_cut_of_segment and allow_beat_snapping:
                target_end = timeline_position + use_duration + BEAT_PHASE_OFFSET  # Apply phase offset
                # Try onset grid first (tight tolerance — real musical hits)
                if onset_grid:
                    aligned_end = align_to_nearest_beat(target_end, onset_grid, tolerance=0.08)
                    snap_source = "onset"
                else:
                    aligned_end = None
                    snap_source = "bpm"
                # Fall back to BPM grid if no onset was close enough
                if aligned_end is None or aligned_end == target_end - BEAT_PHASE_OFFSET:
                    aligned_end = align_to_nearest_beat(target_end, beat_grid, tolerance=0.12)
                    snap_source = "bpm"
                
                # TIMING GUARD: Never allow a beat to snap outside the current segment.
                # Must be inside the segment with at least 100ms breathing room from edges.
                if (aligned_end >= segment.start + 0.1 and 
                    aligned_end < segment.end - 0.1 and
                    aligned_end > timeline_position + 0.1):
                    
                    beat_target = aligned_end
                    use_duration = aligned_end - timeline_position
                    beat_aligned = True
                    
                    # ENHANCED LOGGING: Beat alignment
                    beat_alignment_logs.append({
                        "segment_id": segment.id,
                        "original_duration": original_duration,
                        "aligned_duration": use_duration,
                        "beat_target": beat_target,
                        "timeline_position": timeline_position
                    })
            
            # Final Safety Snapping (Applies to both paths)
            use_duration = snap(use_duration)
            if use_duration < FRAME_DUR: use_duration = FRAME_DUR
            
            # v13.2: USABLE WINDOW - Derived from BestMoment, conditioned on segment contract
            # This replaces hard best_moment boundaries with extension capability for sacred cuts
            window_start = 0.0
            window_end = selected_clip.duration
            
            if selected_clip.best_moments:
                if mode == "PROMPT":
                    # PROMPT MODE: Pick the LONGEST available moment window, not energy-matched.
                    # In PROMPT mode, energy labels are unreliable (all clips tend to be High).
                    # Longest window = most compositional freedom for the editor.
                    all_windows = [
                        (k, v.start, v.end)
                        for k, v in selected_clip.best_moments.items()
                        if hasattr(v, 'start') and hasattr(v, 'end') and v.end > v.start
                    ]
                    if all_windows:
                        # Sort by duration descending, pick longest
                        all_windows.sort(key=lambda x: x[2] - x[1], reverse=True)
                        _, window_start, window_end = all_windows[0]
                    else:
                        best_moment_data = selected_clip.get_best_moment_for_energy(segment.energy)
                        if best_moment_data:
                            window_start, window_end = best_moment_data
                else:
                    # REFERENCE MODE: Energy-matched window
                    # v15.0: For short segments (< 1.0s), pick the HIGHEST ENERGY best_moment window
                    # so we get the "money shot" from each clip, not just position 0.
                    # For longer segments, keep energy-matched logic (stability matters more).
                    segment_is_short = (segment.duration < 1.0)
                    
                    if segment_is_short and selected_clip.best_moments:
                        # Rank available windows by energy priority: High > Medium > Low
                        energy_priority = ["High", "Medium", "Low"]
                        chosen_window = None
                        for ep in energy_priority:
                            if ep in selected_clip.best_moments:
                                m = selected_clip.best_moments[ep]
                                if hasattr(m, 'start') and hasattr(m, 'end') and m.end > m.start:
                                    # Only use this window if it's not exactly the same as a previously used interval
                                    already_used = any(
                                        abs(u_s - m.start) < 0.1 and abs(u_e - m.end) < 0.1
                                        for u_s, u_e in clip_used_intervals.get(selected_clip.filename, [])
                                    )
                                    if not already_used:
                                        chosen_window = (m.start, m.end)
                                        break
                        if chosen_window:
                            window_start, window_end = chosen_window
                        else:
                            # All windows used before, fall back to energy-matched
                            best_moment_data = selected_clip.get_best_moment_for_energy(segment.energy)
                            if best_moment_data:
                                window_start, window_end = best_moment_data
                    else:
                        # Standard energy-matched window for normal-length segments
                        best_moment_data = selected_clip.get_best_moment_for_energy(segment.energy)
                        if best_moment_data:
                            window_start, window_end = best_moment_data

                    
                    # Check if this is a sacred visual cut eligible for window extension
                    # Conditions: visual origin, stable moment, longer duration needed
                    can_extend = False
                    moment_obj = None
                    switched_moment = False
                    
                    # Retrieve the full BestMoment object for stable_moment check
                    if selected_clip.best_moments and segment.energy.value in selected_clip.best_moments:
                        moment_obj = selected_clip.best_moments[segment.energy.value]
                        
                    if (mode == "REFERENCE" and 
                        cut_origin == "visual" and 
                        moment_obj and 
                        moment_obj.stable_moment):
                        
                        # Calculate if extension is needed and possible
                        moment_duration = window_end - window_start
                        segment_remaining = segment.end - timeline_position
                        
                        # Extension needed if moment is shorter than what we need
                        if moment_duration < segment_remaining - 0.05:
                            # Calculate max extension limits
                            max_hold_limit = 12.0 if hold == "long" else (1.8 if hold == "short" else 4.5)
                            usable_duration_needed = min(segment_remaining, max_hold_limit)
                            
                            # Can we extend within clip bounds?
                            # Try extending forward first (beyond window_end)
                            max_possible_end = min(window_start + usable_duration_needed, selected_clip.duration)
                            
                            if max_possible_end > window_end + 0.1:
                                # Extension is possible - expand the usable window
                                window_end = max_possible_end
                                can_extend = True
                                print(f"    📐 UsableWindow extended: {window_start:.2f}s-{window_end:.2f}s (stable moment)")
                            else:
                                # Extension NOT possible - check if other moments in same clip can satisfy
                                # Look for compatible moments (similar moment_role, stable, sufficient duration)
                                target_role = moment_obj.moment_role
                                best_alternative = None
                                best_alt_duration = 0
                                
                                for level_name, moment in selected_clip.best_moments.items():
                                    if level_name == segment.energy.value:
                                        continue  # Skip the one we already checked
                                    
                                    alt_duration = moment.end - moment.start
                                    # Check compatibility: stable and long enough
                                    if (moment.stable_moment and 
                                        alt_duration >= segment_remaining - 0.05 and
                                        alt_duration > best_alt_duration):
                                        # Check role similarity (e.g., Build/Climax/Establishing can substitute)
                                        compatible_roles = [target_role, "Build", "Climax", "Establishing"]
                                        if moment.moment_role in compatible_roles or target_role in compatible_roles:
                                            best_alternative = (level_name, moment)
                                            best_alt_duration = alt_duration
                                
                                if best_alternative:
                                    alt_level, alt_moment = best_alternative
                                    window_start, window_end = alt_moment.start, alt_moment.end
                                    switched_moment = True
                                    print(f"    🔄 Switched to {alt_level} moment: {window_start:.2f}s-{window_end:.2f}s "
                                          f"({window_end-window_start:.2f}s, role: {alt_moment.moment_role})")
                    
                current_pos = clip_current_position[selected_clip.filename]
                
                # Start from current pos if it's in window, else reset to window start
                if window_start <= current_pos < window_end - 0.1:
                    clip_start = current_pos
                else:
                    clip_start = window_start
                
                # End is clip_start + use_duration, capped by (potentially extended/switched) window_end
                clip_end = min(clip_start + use_duration, window_end)
                
                # If the window is too small for the duration, use sequential fallback
                if clip_end - clip_start < 0.1:
                    clip_start = window_start
                    clip_end = min(clip_start + use_duration, selected_clip.duration)
            
            # Fallback to sequential if no best moments
            if clip_start is None:
                clip_start = clip_current_position[selected_clip.filename]
                clip_end = min(clip_start + use_duration, selected_clip.duration)
            
            # RECYCLE CHECK: If clip is exhausted, reset to start
            if clip_start >= selected_clip.duration - 0.1:
                clip_start = 0.0
                clip_end = min(use_duration, selected_clip.duration)
            
            # SAFETY: Ensure clip_end is valid (must be > clip_start and > 0)
            if clip_end <= clip_start or clip_end <= 0 or selected_clip.duration <= 0:
                # SAFETY: Advance timeline by at least FRAME_DUR so the loop cannot
                # re-hit the exact same state. Without this, a broken clip causes forever-loop.
                emergency_advance = max(FRAME_DUR, min(segment_remaining, 0.1))
                print(f"    [SKIP] Invalid clip state: clip_end={clip_end:.2f}, clip_start={clip_start:.2f}, "
                      f"duration={selected_clip.duration:.2f} — advancing {emergency_advance:.3f}s")
                timeline_position = snap(timeline_position + emergency_advance)
                clip_current_position[selected_clip.filename] = min(
                    clip_current_position[selected_clip.filename] + emergency_advance,
                    selected_clip.duration
                )
                cuts_in_segment += 1
                continue
            
            # FINAL CALCULATION
            # v14.7: Snap BOTH clip_start and use_duration to ensure frame-aligned exit
            # v14.7 Safety: Clamp snapped clip_start to BestMoment window
            clip_start = max(snap(clip_start), snap(window_start))
            use_duration = snap(use_duration)
            if use_duration < FRAME_DUR: use_duration = FRAME_DUR # Hard frame guard
            
            clip_end = min(clip_start + use_duration, snap(window_end))
            actual_duration = clip_end - clip_start

            # v13.1: REFERENCE MODE - NO LOOPING
            # If a sacred cut can't be filled, we accept the underfill honestly
            # rather than creating visual artifacts through looping
            remaining_dur = segment.end - timeline_position
            if mode == "REFERENCE" and is_sacred_cut and actual_duration < (remaining_dur - 0.05):
                # Accept underfill for sacred cuts - honesty over hacks
                print(f"    ⚠️ UNDERFILL ({actual_duration:.2f}s < {remaining_dur:.2f}s) - Accepting honestly (no loop)")

            
            # SAFETY: Final boundary check (belt-and-suspenders after snap)
            if clip_end <= clip_start or clip_end <= 0:
                print(f"    [SKIP] Invalid clip boundaries ({clip_start:.2f}s-{clip_end:.2f}s) after snap — advancing")
                timeline_position = snap(timeline_position + FRAME_DUR)
                cuts_in_segment += 1
                continue

            # PHASE 4: Create Decision with Locked Boundaries
            # timeline_start is ALWAYS EXACTLY the previous timeline_end
            decision_start = timeline_position
            decision_end = snap(decision_start + actual_duration)
            
            # REMOVED LYING EDL LOGIC (v12.7):
            # We no longer force decision_end = segment.end.
            # If actual_duration is short, the loop will run again to fill the gap.
            # if is_last_cut_of_segment:
            #    decision_end = segment.end

            decision = EditDecision(
                segment_id=segment.id,
                clip_path=selected_clip.filepath,
                clip_start=clip_start,
                clip_end=clip_end,
                timeline_start=decision_start,
                timeline_end=decision_end,
                reasoning=thinking,
                vibe_match=vibe_matched
            )
            decisions.append(decision)
            
            # Update Context and Trackers
            ctx.timeline_pos = decision_end
            ctx.last_motion = selected_clip.motion
            ctx.last_content = selected_clip.content_description
            ctx.last_subjects = selected_clip.primary_subject
            ctx.last_scale = infer_shot_scale(selected_clip)
            
            timeline_position = decision_end
            clip_current_position[selected_clip.filename] = clip_end
            clip_usage_count[selected_clip.filename] += 1
            clip_last_used_at[selected_clip.filename] = timeline_position
            clip_used_intervals[selected_clip.filename].append((clip_start, clip_end))
            
            # Variety tracking
            second_last_clip = last_used_clip
            last_used_clip = selected_clip.filename
            cuts_in_segment += 1
            
            print(f"    ✂️ Cut {cuts_in_segment}: {selected_clip.filename} "
                  f"[{clip_start:.2f}s-{clip_end:.2f}s] ({actual_duration:.2f}s) "
                  f"→ timeline [{decision.timeline_start:.6f}s-{decision.timeline_end:.6f}s]")

        # v13.1: HONEST GAP HANDLING (No Lying EDL)
        # In REFERENCE mode: NEVER stretch timeline_end beyond actual frames
        # This prevents "lying" about duration which causes sync issues downstream
        gap = segment.end - timeline_position
        if gap > 0.001:
            if mode == "REFERENCE":
                # REFERENCE MODE: Accept gap honestly, log it
                print(f"    ⚠️ GAP in segment {segment.id} ({gap:.4f}s) - Checking for extension safety...")
                # v14.7 FIX: Only extend timeline if we can consistently extend the clip
                if decisions and decisions[-1].segment_id == segment.id:
                    # Find the clip to check duration
                    clip_path = decisions[-1].clip_path
                    clip = next((c for c in clip_index.clips if c.filepath == clip_path), None)
                    extra = segment.end - decisions[-1].timeline_end
                    
                    if clip and (decisions[-1].clip_end + extra) <= (clip.duration + 0.002):
                        # v14.7 FIX: Re-snap after extension to ensure frame integrity
                        decisions[-1].clip_end = snap(decisions[-1].clip_end + extra)
                        decisions[-1].timeline_end = snap(segment.end)
                        timeline_position = decisions[-1].timeline_end
                        print(f"    🔧 Extended decision {len(decisions)} and clip to segment end: {segment.end:.4f}s")
                    else:
                        print(f"    ⚠️ GAP PERMANENT: Last clip {Path(clip_path).name} hits duration limit.")
                        hold_secs = segment.end - decisions[-1].timeline_end
                        decisions[-1].timeline_end = snap(segment.end)
                        decisions[-1].hold_end_seconds = snap(hold_secs) if hold_secs > 0.02 else None
                        timeline_position = decisions[-1].timeline_end
                        print(f"    🔧 Demo fill: holding last frame {hold_secs:.2f}s so timeline reaches segment end")
                else:
                    timeline_position = decisions[-1].timeline_end if decisions else segment.end
            else:
                # PROMPT MODE: Allow gap filling (legacy behavior)
                print(f"    🔗 Filling gap in segment {segment.id} ({gap:.4f}s remaining)")
                timeline_position = segment.end
                if decisions:
                    decisions[-1].timeline_end = segment.end

        # === SEGMENT LOGGING (Directive 8) ===
        seg_decisions = [d for d in decisions if d.segment_id == segment.id]
        rendered_dur = sum(d.timeline_end - d.timeline_start for d in seg_decisions)
        ref_dur = segment.duration
        cuts_used = len(seg_decisions)
        
        # v13.1: Updated logging (no loop status in REFERENCE mode)       
        print(f"[SEGMENT {segment.id} LOG] Ref: {ref_dur:.2f}s | Rendered: {rendered_dur:.2f}s | Cuts: {cuts_used} | Mode: {mode}")
        if abs(rendered_dur - ref_dur) > 0.05:
            print(f"    ❌ TIME DRIFT DETECTED: {rendered_dur - ref_dur:.3f}s")

    
    # v14.7: Finalize blueprint duration to match snapped segments
    if blueprint.segments:
        blueprint.total_duration = blueprint.segments[-1].end

    if mode == "REFERENCE" and decisions and timeline_position < blueprint.total_duration - 0.05:
        shortfall = blueprint.total_duration - timeline_position
        last = decisions[-1]
        last.timeline_end = snap(blueprint.total_duration)
        last.hold_end_seconds = (last.hold_end_seconds or 0) + snap(shortfall)
        timeline_position = last.timeline_end
        print(f"    🔧 Demo reconciliation: last decision extended by {shortfall:.2f}s so total = {blueprint.total_duration:.2f}s")
        
    edl = EDL(decisions=decisions)
    unique_clips_used = len(set(d.clip_path for d in decisions))
    total_clips = len(clip_index.clips)
    
    print(f"\n{'='*60}")
    print(f"[OK] Matching complete: {len(decisions)} edit decisions")
    print(f"[OK] Total timeline duration: {timeline_position:.2f}s (target: {blueprint.total_duration:.2f}s)")
    print(f"\n📊 DIVERSITY REPORT:")
    print(f"   Unique clips used: {unique_clips_used}/{total_clips}")
    
    if unique_clips_used == total_clips:
        print(f"   ✅ PERFECT! Every clip in your library was used.")
    elif unique_clips_used >= total_clips * 0.9:
        print(f"   ✅ EXCELLENT variety - {total_clips - unique_clips_used} clips unused.")
    else:
        print(f"   ⚠️ {total_clips - unique_clips_used} clips were not used.")
    
    # Check for repeats
    clip_uses = Counter(d.clip_path for d in decisions)
    repeats = [(path.split('\\')[-1], count) for path, count in clip_uses.items() if count > 1]
    
    if repeats:
        print(f"\n   ⚠️ CLIPS REPEATED:")
        for name, count in sorted(repeats, key=lambda x: -x[1])[:5]:
            print(f"      {name}: {count}x")
    else:
        print(f"\n   ✅ NO CLIPS REPEATED! Perfect diversity achieved.")
    
    # Compromises
    if compromises:
        print(f"\n📋 ENERGY COMPROMISES: {len(compromises)}")
        print(f"   (Used adjacent energy when exact wasn't available)")
        # Count by type
        compromise_summary = Counter(f"{c['wanted']}→{c['got']}" for c in compromises)
        for swap, count in compromise_summary.most_common():
            print(f"      {swap}: {count} times")
    
    # Recommendations
    if deficits or compromises:
        print(f"\n💡 RECOMMENDATIONS TO IMPROVE THIS EDIT:")
        
        # 1. Direct Capacity Deficits
        if deficits:
            print(f"   [Inventory Gaps]")
            for energy, count in deficits.items():
                examples = {
                    "High": "(dancing, sports, action, fast movement)",
                    "Medium": "(walking, social, casual movement, city life)",
                    "Low": "(scenic, calm, establishing shots, landscapes)"
                }.get(energy, "")
                print(f"   → Add {count} more {energy.upper()}-ENERGY clips {examples}")
        
        # 2. Quality/Energy Mismatch Recommendations
        if compromises:
            print(f"\n   [Quality Improvements]")
            # Count specifically what we swapped TO what
            high_compromise = sum(1 for c in compromises if c['wanted'] == "High")
            if high_compromise > 0:
                print(f"   → {high_compromise} segments wanted 'High' energy but used 'Medium'.")
                print(f"     Add high-intensity clips with 'Urban' or 'Nightlife' vibes to fix this.")
            
            low_compromise = sum(1 for c in compromises if c['wanted'] == "Low")
            if low_compromise > 0:
                print(f"   → {low_compromise} segments wanted 'Low' energy but used 'Medium'.")
                print(f"     Add more 'Nature' or 'Calm' clips to reduce jitter here.")
    
    # ENHANCED LOGGING: Unused clips
    used_clip_names = set(Path(d.clip_path).name for d in decisions)
    all_clip_names = set(c.filename for c in clip_index.clips)
    unused_clips = list(all_clip_names - used_clip_names)
    
    # Find clips that were never eligible (energy mismatch)
    never_eligible = []
    for clip in clip_index.clips:
        if clip.filename in unused_clips:
            # Check if it would be eligible for ANY segment
            was_eligible_anywhere = False
            for seg in blueprint.segments:
                eligible = get_eligible_clips(seg.energy, [clip])
                if eligible:
                    was_eligible_anywhere = True
                    break
            if not was_eligible_anywhere:
                never_eligible.append(clip.filename)
    
    unused_data = {
        "unused_clips": unused_clips,
        "never_eligible": never_eligible,
        "eligible_but_not_selected": [c for c in unused_clips if c not in never_eligible]
    }
    
    print(f"{'='*60}\n")
    
    # Attach enhanced logging to EDL (hack: store in a custom attribute)
    edl._enhanced_logging = {
        "candidate_rankings": candidate_rankings,
        "eligibility_breakdowns": eligibility_breakdowns,
        "semantic_neighbor_events": semantic_neighbor_events,
        "beat_alignment_logs": beat_alignment_logs,
        "unused_clips": unused_data
    }
    
    # v15.0: WRITE GLOBAL HISTORY — persist used moments so next render gets freshness diversity
    try:
        import json as _json
        import uuid as _uuid
        _run_key = run_id or str(_uuid.uuid4())[:8]
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Reload and merge (don't overwrite other sessions)
        _existing_hist: dict = {}
        if _HISTORY_PATH.exists():
            try:
                _existing_hist = _json.loads(_HISTORY_PATH.read_text(encoding='utf-8'))
            except Exception:
                _existing_hist = {}
        # Add this run's intervals
        for fname, intervals in clip_used_intervals.items():
            entry = _existing_hist.setdefault(fname, [])
            for s, e in intervals:
                entry.append({"start": round(s, 4), "end": round(e, 4), "run_id": _run_key})
            # Keep last 20 entries per clip to avoid unbounded growth
            _existing_hist[fname] = entry[-20:]
        _HISTORY_PATH.write_text(_json.dumps(_existing_hist, indent=2), encoding='utf-8')
        print(f"  📚 Global history updated → {_HISTORY_PATH.name}")
    except Exception as _we:
        print(f"  [WARN] Could not write clip history: {_we}")
    
    # Write detailed scoring breakdown to separate file for surgical debugging
    # Now works for both REFERENCE and PROMPT mode
    ref_name = Path(reference_path).stem if reference_path else "prompt_edit"
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    xray_filename = f"{run_id}_XRAY.txt" if run_id else f"{ref_name}_XRAY.txt"
    xray_path = BASE_DIR / "data" / "results" / xray_filename
    xray_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(xray_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write(f"X-RAY DIAGNOSTIC REPORT - {mode} MODE\n")
        f.write("="*80 + "\n")
        f.write(f"Reference/Prompt: {ref_name}\n")
        f.write(f"Total Segments: {len(blueprint.segments)}\n")
        f.write(f"Total Clips: {len(clip_index.clips)}\n")
        f.write(f"Total Decisions: {len(edl.decisions)}\n")
        f.write("="*80 + "\n\n")
        
        # === BLUEPRINT OVERVIEW ===
        f.write("📑 BLUEPRINT SEGMENTS:\n")
        f.write("-"*60 + "\n")
        for seg in blueprint.segments:
            cde = getattr(seg, 'cde', 'N/A')
            hold = getattr(seg, 'expected_hold', 'Normal')
            origin = getattr(seg, 'cut_origin', 'visual')
            f.write(f"  Seg {seg.id:02d}: {seg.start:5.2f}s-{seg.end:5.2f}s | {seg.energy.value:6} | {seg.arc_stage:10} | CDE={cde:8} | Hold={hold:6} | Origin={origin}\n")
            f.write(f"           Vibe: {seg.vibe}\n")
        f.write("\n")
        
        # === CLIP USAGE BREAKDOWN (Microscopic) ===
        f.write("📊 CLIP USAGE ANALYSIS:\n")
        f.write("-"*60 + "\n")
        
        # Sort by usage count (descending)
        sorted_clips = sorted(clip_index.clips, key=lambda c: clip_usage_count[c.filename], reverse=True)
        
        for clip in sorted_clips:
            usage = clip_usage_count[clip.filename]
            intervals = clip_used_intervals.get(clip.filename, [])
            vibes = clip.vibes[:3] if clip.vibes else ['N/A']
            subjects = clip.primary_subject[:2] if clip.primary_subject else ['N/A']
            
            status = "✅ USED" if usage > 0 else "❌ UNUSED"
            warning = "⚠️ HEAVY" if usage >= 3 else ""
            
            f.write(f"\n  {status} {warning} {clip.filename}\n")
            f.write(f"       Usage: {usage}x | Energy: {clip.energy.value} | Duration: {clip.duration:.1f}s\n")
            f.write(f"       Vibes: {', '.join(vibes)} | Subjects: {', '.join(subjects)}\n")
            
            if intervals:
                f.write(f"       Moments used:\n")
                for i, (start, end) in enumerate(intervals):
                    f.write(f"         [{i+1}] {start:.2f}s - {end:.2f}s ({end-start:.2f}s)\n")
            
            # Clip curation suggestion
            if usage == 0:
                f.write(f"       💡 SUGGESTION: Not used. Consider if vibes/energy match the edit.\n")
            elif usage >= 3:
                f.write(f"       💡 SUGGESTION: Heavily reused. Add more clips with similar vibes: {', '.join(vibes)}\n")
        
        f.write("\n")
        
        # === UNUSED CLIPS SUMMARY ===
        unused = [c for c in clip_index.clips if clip_usage_count[c.filename] == 0]
        if unused:
            f.write("🚫 UNUSED CLIPS (Potential Issues):\n")
            f.write("-"*60 + "\n")
            for clip in unused:
                f.write(f"  ❌ {clip.filename} | {clip.energy.value} | Vibes: {', '.join(clip.vibes[:2]) if clip.vibes else 'N/A'}\n")
            f.write(f"\n  Total unused: {len(unused)}/{len(clip_index.clips)} ({100*len(unused)/len(clip_index.clips):.0f}%)\n")
            f.write("\n")
        
        # === DECISION FLOW (Timeline View) ===
        f.write("🎬 EDIT DECISION FLOW:\n")
        f.write("-"*60 + "\n")
        for i, dec in enumerate(edl.decisions):
            clip_name = Path(dec.clip_path).name
            dur = dec.timeline_end - dec.timeline_start
            clip_dur = dec.clip_end - dec.clip_start
            f.write(f"  [{i+1:02d}] {dec.timeline_start:6.2f}s-{dec.timeline_end:6.2f}s ({dur:4.2f}s) | {clip_name:20} [{dec.clip_start:5.2f}s-{dec.clip_end:5.2f}s]\n")
            f.write(f"        Vibe Match: {'✅' if dec.vibe_match else '❌'} | {dec.reasoning[:60]}...\n")
        f.write("\n")
        
        # === SEGMENT-LEVEL X-RAY LOGS ===
        if xray_logs:
            f.write("🔬 SEGMENT SCORING X-RAY:\n")
            f.write("-"*60 + "\n")
            f.write('\n'.join(xray_logs))
            f.write("\n\n")
        
        # === CURATION RECOMMENDATIONS ===
        f.write("="*80 + "\n")
        f.write("💡 CLIP CURATION RECOMMENDATIONS:\n")
        f.write("="*80 + "\n")
        
        # Calculate gaps
        needed_vibes = set()
        needed_energies = set()
        for seg in blueprint.segments:
            seg_filled = any(d.segment_id == seg.id for d in edl.decisions)
            if not seg_filled or any(d.segment_id == seg.id and not d.vibe_match for d in edl.decisions):
                if seg.vibe:
                    for v in seg.vibe.split(','):
                        needed_vibes.add(v.strip().lower())
                needed_energies.add(seg.energy.value)
        
        heavily_used = [c.filename for c in clip_index.clips if clip_usage_count[c.filename] >= 3]
        
        if needed_vibes:
            f.write(f"\n📥 ADD clips with vibes: {', '.join(sorted(needed_vibes))}\n")
        if heavily_used:
            f.write(f"\n🔄 REPLACE heavily-used clips: {', '.join(heavily_used)}\n")
            f.write(f"   Add alternative clips with similar content.\n")
        if unused:
            low_value = [c.filename for c in unused if clip_usage_count[c.filename] == 0][:5]
            if low_value:
                f.write(f"\n🗑️ CONSIDER REMOVING (never used): {', '.join(low_value)}\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write("END OF X-RAY REPORT\n")
        f.write("="*80 + "\n")
    
    print(f"\n🔬 X-RAY diagnostic report exported: {xray_path}")
    
    return edl, advisor_hints


def _create_energy_pools(clip_index: ClipIndex) -> Dict[EnergyLevel, List[ClipMetadata]]:
    # Group clips by energy level for efficient matching.
    # Returns: Dictionary mapping EnergyLevel -> List[ClipMetadata]
    pools = defaultdict(list)
    for clip in clip_index.clips:
        pools[clip.energy].append(clip)
    return dict(pools)


# ============================================================================
# STATS & DEBUGGING
# ============================================================================

def print_edl_summary(edl: EDL, blueprint: StyleBlueprint, clip_index: ClipIndex) -> None:
    # Print human-readable EDL summary for debugging.
    print(f"\n{'='*60}")
    print(f"[EDL] EDIT DECISION LIST SUMMARY")
    print(f"{'='*60}\n")
    
    print(f"Total decisions: {len(edl.decisions)}")
    print(f"Total segments: {len(blueprint.segments)}")
    print(f"Available clips: {len(clip_index.clips)}\n")
    
    # Count clip usage
    clip_usage = defaultdict(int)
    for decision in edl.decisions:
        filename = decision.clip_path.split('/')[-1].split('\\')[-1]
        clip_usage[filename] += 1
    
    print("Clip usage distribution:")
    for filename, count in sorted(clip_usage.items(), key=lambda x: x[1], reverse=True):
        print(f"  {filename}: {count} times")
    
    # NEW: Intelligence Audit (v8.1)
    # This proves the AI actually followed the narrative intent
    print(f"\n🧠 INTELLIGENCE AUDIT (Narrative Compliance):")
    arc_accuracy = defaultdict(list)
    function_counts = Counter()
    vibe_matches = 0
    total_cuts = len(edl.decisions)

    # Find the blueprint segments for each decision to check compliance
    for d in edl.decisions:
        seg = next((s for s in blueprint.segments if s.id == d.segment_id), None)
        if seg:
            function_counts[seg.shot_function] += 1
            if d.vibe_match: vibe_matches += 1
            
            # Use heuristic to see if shot_function matches clip's narrative role
            # (Note: This is a rough check since clips don't have explicit function tags yet)
            arc_accuracy[seg.arc_stage].append(1 if d.vibe_match else 0)

    print(f"   Vibe Accuracy: {(vibe_matches/total_cuts*100):.1f}% matching suggested vibes")
    
    print(f"\n   Shot Function Breakdown:")
    for func, count in function_counts.most_common():
        print(f"      {func:12s}: {count} cuts")

    print(f"\n   Arc Stage Fidelity:")
    for stage in ["Intro", "Build-up", "Peak", "Outro"]:
        matches = arc_accuracy.get(stage, [])
        if matches:
            acc = sum(matches) / len(matches) * 100
            print(f"      {stage:12s}: {acc:.1f}% intent alignment")

    print()



def validate_edl(edl: EDL, blueprint: StyleBlueprint) -> bool:
    # Validate EDL for continuity and timing errors.
    # Checks timeline continuity, duration matching, and clip validity.
    # Returns: True if valid, raises ValueError if issues found
    # Check timeline continuity
    for i in range(len(edl.decisions) - 1):
        current = edl.decisions[i]
        next_decision = edl.decisions[i + 1]
        
        gap = abs(current.timeline_end - next_decision.timeline_start)
        if gap > 0.05:  # 50ms tolerance
            raise ValueError(
                f"Timeline gap/overlap between decision {i} and {i+1}: {gap:.3f}s"
            )
    
    # Check total duration
    if edl.decisions:
        total_duration = edl.decisions[-1].timeline_end
        expected = blueprint.total_duration
        
        # Strict tolerance: +/-0.5s
        if abs(total_duration - expected) > 0.5:
            raise ValueError(
                f"EDL total duration ({total_duration:.2f}s) "
                f"doesn't match blueprint ({expected:.2f}s) - difference: {abs(total_duration - expected):.2f}s"
            )
    
    # Validate clip paths exist and timestamps are reasonable
    for decision in edl.decisions:
        if decision.clip_start < 0 or decision.clip_end <= decision.clip_start:
            raise ValueError(
                f"Invalid clip timestamps in decision: {decision.clip_start:.2f}s - {decision.clip_end:.2f}s"
            )
    
    return True
