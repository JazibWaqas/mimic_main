"""
Data models for MIMIC project.
These are the ONLY valid data structures. Do not create ad-hoc dictionaries.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from enum import Enum

# ============================================================================
# ENUMS (Controlled Vocabularies)
# ============================================================================

class EnergyLevel(str, Enum):
    """
    Energy classification based on visual rhythm (NOT content).
    
    Low: Slow motion, steady shots, minimal cuts (meditation, landscapes)
    Medium: Moderate pacing, some variation (vlogs, interviews)
    High: Rapid cuts, fast motion, intense action (sports, dance trends)
    """
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


# ============================================================================
# STYLE CONFIG MODELS (v14.9 Post-Editor Layer)
# ============================================================================

class TextStyleConfig(BaseModel):
    font: str = Field("Inter", description="Font family: Inter, Roboto, Outfit")
    weight: int = Field(600, description="Font weight: 400, 600, 700")
    color: str = Field("#FFFFFF", description="Hex text color")
    shadow: bool = Field(True, description="Whether to show text shadow")
    position: str = Field("bottom", description="Position: top, center, bottom")
    animation: str = Field("fade", description="Entry animation: fade, none")

class ColorConfig(BaseModel):
    preset: str = Field("neutral", description="Color preset: neutral, warm, cool, high_contrast, vintage")

class TextureConfig(BaseModel):
    grain: bool = Field(False, description="Whether to show film grain")

class StyleConfig(BaseModel):
    text: TextStyleConfig = Field(default_factory=TextStyleConfig)
    color: ColorConfig = Field(default_factory=ColorConfig)
    texture: TextureConfig = Field(default_factory=TextureConfig)



class MotionType(str, Enum):
    """
    Camera/subject movement classification.
    
    Static: Fixed camera, minimal subject movement
    Dynamic: Panning, zooming, fast subject motion
    """
    STATIC = "Static"
    DYNAMIC = "Dynamic"


class NarrativeSubject(str, Enum):
    """
    Specific narrative subjects that can be used for subject-locking.
    """
    PEOPLE_GROUP = "People-Group"
    PEOPLE_SOLO = "People-Solo"
    PLACE_NATURE = "Place-Nature"
    PLACE_URBAN = "Place-Urban"
    OBJECT_DETAIL = "Object-Detail"
    ABSTRACT = "Abstract"


# ============================================================================
# REFERENCE VIDEO ANALYSIS
# ============================================================================

class Segment(BaseModel):
    """
    A single time-based segment from the reference video.
    
    Example: {
        "id": 1,
        "start": 0.0,
        "end": 2.3,
        "duration": 2.3,
        "energy": "High",
        "motion": "Dynamic",
        "vibe": "Action",
        "reasoning": "Rapid visual movement detected in reference shots."
    }
    """
    id: int = Field(..., description="Sequential segment number (1, 2, 3...)")
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., gt=0, description="End time in seconds")
    duration: float = Field(..., gt=0, description="Segment length in seconds")
    energy: EnergyLevel
    motion: MotionType
    vibe: str = Field("General", description="The aesthetic/content vibe (e.g. Nature, Urban, Action)")
    reasoning: str = Field("", description="AI's thinking about why this segment has this profile")
    arc_stage: str = Field("Main", description="The role of this segment in the video's story arc (e.g. Intro, Build-up, Peak, Outro)")
    
    # Editorial Intelligence (v8.0+)
    shot_scale: str = Field("", description="Shot framing: Extreme CU | CU | Medium | Wide | Extreme Wide")
    shot_function: str = Field("", description="Editorial purpose: Establish | Action | Reaction | Detail | Transition | Release | Button")
    relation_to_previous: str = Field("None", description="How this relates to previous shot: Setup | Payoff | Contrast | Continuation | None")
    expected_hold: str = Field("Normal", description="How long viewer should rest: Short | Normal | Long")
    camera_movement: str = Field("", description="Camera motion: Locked | Handheld | Smooth pan | Erratic | Mixed")
    emotional_guidance: str = Field("", description="What the viewer should feel (e.g. anticipation, joy)")
    
    # Director Soul (v12.1)
    media_type: str = Field("Video", description="Video | Still")
    shot_scale_role: str = Field("", description="World-Building | Action-Link | Intimacy-Focus")
    temporal_weight: str = Field("Push", description="Push (fast/tension) vs Breath (emotional/resting)")
    emotional_anchor: bool = Field(False, description="Whether this segment is a key narrative turning point")
    audio_driver: str = Field("", description="Music-Rhythm | Sound-Event | Emotional-Silence")
    audio_priority: str = Field("", description="Music > SFX | SFX > Music | Silence > All")
    cut_motivation: str = Field("", description="Rhythmic-Snap | Graphic-Match | Action-Completion | Narrative-Shift")
    transition_intent: dict = Field(default_factory=dict, description="Detailed transition mechanics: type, mechanism, strength")
    continuity_hook: dict = Field(default_factory=dict, description="Hooks for visual flow: opens, resolves, type")
    
    # v12.1 Internal Tracking
    cut_origin: str = Field("visual", description="visual | beat")
    
    # v14.7 Prompt Mode: Cut Density Expectation
    cde: str = Field("Moderate", description="Cut Density Expectation: Sparse | Moderate | Dense")
    
    @field_validator('shot_scale_role', 'temporal_weight', 'cut_motivation')
    @classmethod
    def validate_director_soul(cls, v, info):
        """
        v12.1 Assertion: Ensure semantic depth is present.
        
        v14.7 UPDATE: These fields are optional for Prompt Mode generated blueprints.
        The validator now allows empty values, with defaults applied in Editor if needed.
        This enables Prompt Mode to generate minimal blueprints while REFERENCE Mode
        blueprints (from brain.py analysis) continue to enforce these fields.
        """
        # Allow empty values for Prompt Mode compatibility
        # The Editor will use sensible defaults if these are empty
        return v if v else ""
    
    @field_validator('end')
    @classmethod
    def end_after_start(cls, v, info):
        if 'start' in info.data and v <= info.data['start']:
            raise ValueError('end must be greater than start')
        return v
    
    @field_validator('duration')
    @classmethod
    def duration_matches(cls, v, info):
        if 'start' in info.data and 'end' in info.data:
            expected = info.data['end'] - info.data['start']
            if abs(v - expected) > 0.01:  # Allow 10ms float precision
                raise ValueError(f'duration must equal end - start')
        return v


class TextEvent(BaseModel):
    """
    Timed text overlay event (v12.2).
    """
    content: str = Field(..., description="Visible text content")
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., gt=0, description="End time in seconds")
    duration: float = Field(..., gt=0, description="Duration in seconds")
    sync_driver: str = Field("Visual-hit", description="Beat | Lyric | Narrative | Visual-hit")
    role: str = Field("Decorative", description="Narrative-Anchor | Emphasis | Decorative | Branding")
    confidence: str = Field("Medium", description="High | Medium | Low")


class StyleBlueprint(BaseModel):
    """
    Complete analysis of reference video structure.
    This is the "editing DNA" we'll apply to user clips.
    """
    model_config = ConfigDict(populate_by_name=True)
    
    total_duration: float = Field(..., gt=0, description="Total video length in seconds")
    segments: List[Segment] = Field(..., min_length=1, description="Ordered list of segments")
    phrases: List[dict] = Field(default_factory=list, description="Logical grouping of segments for continuity (v12.4)")
    
    # Creator Mode (v11.0+)
    text_prompt: Optional[str] = Field(None, description="The natural language prompt used to generate this blueprint")
    plan_summary: str = Field("", description="A 2-3 sentence human-readable explanation of the editing plan")
    assumed_material: List[str] = Field(default_factory=list, description="Footage types assumed by the generator to make the vision work")
    
    # Professional Editing Metadata
    editing_style: str = Field("General", description="The editing style (e.g. Cinematic, Vlog, Montage, TikTok/Reel)")
    emotional_intent: str = Field("Dynamic", description="The intended mood/emotion (e.g. Nostalgic, Energetic, Peaceful)")
    arc_description: str = Field("", description="Description of the video's structural story arc")
    
    # Enhanced Narrative Analysis (v7.0+)
    text_overlay: str = Field("", description="On-screen text extracted from reference video")
    narrative_message: str = Field("", description="What the edit is trying to communicate in one sentence")
    intent_clarity: str = Field("Implicit", description="How explicit the intent is: Clear, Implicit, or Ambiguous")
    
    # Dynamic Text Engine (v12.2)
    text_events: List[TextEvent] = Field(default_factory=list, description="Timed editorial text events")
    
    # Content Requirements (Intent-Level)
    must_have_content: List[str] = Field(default_factory=list, description="3-5 types of moments this edit fundamentally relies on")
    should_have_content: List[str] = Field(default_factory=list, description="2-3 types of moments that would strengthen the edit")
    avoid_content: List[str] = Field(default_factory=list, description="Content types that would clash with narrative intent")
    
    # Experience Goals (Felt, Not Mechanical)
    pacing_feel: str = Field("", description="How the edit feels rhythmically (e.g., breathable, relentless)")
    visual_balance: str = Field("", description="What the edit emphasizes (e.g., people-centric, place-centric)")
    
    # Visual Style & Aesthetics (v8.0+)
    color_grading: dict = Field(default_factory=dict, description="Color treatment: tone, contrast, specific_look")
    aspect_ratio: str = Field("", description="Video aspect ratio: 16:9 | 9:16 | 1:1 | 4:5 | 21:9")
    visual_effects: List[str] = Field(default_factory=list, description="Recurring effects: Film grain, Light leaks, etc.")
    shot_variety: dict = Field(default_factory=dict, description="Shot scale variety: dominant_scale, variety_level")
    
    # Global Style Branding (v12.1)
    stylistic_invariants: List[str] = Field(default_factory=list, description="Fixed rules for this specific edit (e.g. 'Hard cuts only')")
    peak_density: str = Field("Moderate", description="How crowded the peaks are: Sparse | Moderate | Dense")
    
    # Editing Style (v8.0+)
    cut_style: str = Field("", description="How cuts are executed: Hard cuts | Cross dissolves | Match cuts | Jump cuts | Mixed")
    transition_effects: List[str] = Field(default_factory=list, description="Special transitions: Whip pans, Zooms, Morphs, None")
    
    # Metadata Invariants (v12.1)
    reference_audio: str = Field("original", description="original | muted. Tracks if the source was muted during analysis.")
    audio_confidence: str = Field("Observed", description="Observed | Inferred. Tracks if audio was directly analyzed or inferred from visual rhythm.")
    
    # Audio & Music (v8.0+)
    music_sync: str = Field("", description="Cut-music alignment: Tightly synced | Loosely synced | Independent")
    audio_style: dict = Field(default_factory=dict, description="Audio characteristics: genre, vocal_presence, energy")
    music_structure: dict = Field(default_factory=dict, description="Music structure: phrases, accent_moments, ending_type")
    
    # Text Styling & Identity (v12.1 Refined)
    text_style: dict = Field(default_factory=dict, description="Typography design: font_style, animation, placement, color_effects")
    text_behavior: dict = Field(default_factory=dict, description="Logic of text: appearance_logic, entry_moment, exit_rule, priority")
    text_cadence: str = Field("", description="Rhythm of text: Per-cut | Per-beat | Per-phrase | Static")
    
    # v14.9 Style Control (Post-Editor Layer)
    style_config: Optional['StyleConfig'] = Field(None, description="Recommended visual styling configuration")
    
    overall_reasoning: str = Field("", description="AI's holistic thinking about this video's structure")
    ideal_material_suggestions: List[str] = Field(default_factory=list, description="Suggestions for the user on what clips would work best")
    
    # Identity Passport (v12.1)
    contract: dict = Field(default_factory=dict, alias="_contract", serialization_alias="_contract", validation_alias="_contract", description="Self-describing identity: version, type, source_hash")
    
    @field_validator('segments')
    @classmethod
    def validate_segments(cls, v, info):
        if not v:
            raise ValueError('Must have at least one segment')
        
        # Check sequential IDs
        for i, seg in enumerate(v, start=1):
            if seg.id != i:
                raise ValueError(f'Segment IDs must be sequential starting from 1')
        
        # Check continuity (no gaps/overlaps)
        for i in range(len(v) - 1):
            if abs(v[i].end - v[i+1].start) > 0.01:
                raise ValueError(f'Gap/overlap between segments {i+1} and {i+2}')
        
        # Check total duration matches last segment end
        if 'total_duration' in info.data:
            expected_duration = info.data['total_duration']
            last_segment_end = v[-1].end
            gap = expected_duration - last_segment_end
            
            # If Gemini truncated the video (common bug), auto-extend the last segment
            if gap > 0.1:  # More than 100ms gap
                print(f"[VALIDATION] Gemini truncated analysis: video is {expected_duration:.2f}s but segments end at {last_segment_end:.2f}s")
                print(f"[VALIDATION] Auto-extending last segment by {gap:.2f}s to match video duration")
                
                # Extend the last segment to match video duration
                v[-1].end = expected_duration
                v[-1].duration = v[-1].end - v[-1].start
                
            # If segments extend beyond video (shouldn't happen, but check)
            elif gap < -0.1:  # Segments go 100ms+ past video end
                raise ValueError(f'Segments extend beyond video duration (video: {expected_duration:.2f}s, segments end: {last_segment_end:.2f}s)')
        
        return v


# ============================================================================
# GEMINI ADVISOR (v7.0+)
# ============================================================================

class ArcStageGuidance(BaseModel):
    """
    Gemini's editorial intent reasoning for a specific arc stage.
    
    This expresses WHAT TYPE of content carries narrative intent,
    not prescriptive rules about what must be used.
    """
    primary_emotional_carrier: str = Field("", description="What type of content drives the narrative at this stage")
    supporting_material: str = Field("", description="What can enhance or transition between primary moments")
    intent_diluting_material: str = Field("", description="What would weaken the emotional impact")
    reasoning: str = Field("", description="Why this intent matters for this arc stage")
    recommended_clips: List[str] = Field(default_factory=list, description="8-12 clip filenames that exemplify the primary carrier")
    required_energy: str = Field("", description="OVERRIDE: Required energy level for this arc stage (Low/Medium/High) - overrides reference's mechanical labels when text overlay demands it")


class LibraryAssessment(BaseModel):
    """
    Gemini's overall assessment of the user's clip library.
    """
    strengths: List[str] = Field(default_factory=list, description="What types of content are well-represented")
    gaps: List[str] = Field(default_factory=list, description="What types of content are missing or weak")
    confidence: str = Field("Medium", description="High, Medium, or Low confidence in library coverage")


class CreativeAudit(BaseModel):
    """
    Deeper analysis of the synergy between Reference Theme and User Library.
    """
    reference_theme: str = Field("", description="The primary visual/emotional theme of the reference (e.g. 'Mountains / Nature')")
    library_theme: str = Field("", description="The dominant theme detected in user clips (e.g. 'City / Urban')")
    thematic_dissonance: str = Field("", description="Description of mismatch between reference and library themes")
    critical_nuance: str = Field("", description="Subtle mismatch (e.g. 'Reference is 4:3 filmic, Library is 9:16 digital')")

class LibraryAlignment(BaseModel):
    """
    Structured assessment of how well the library matches the reference style.
    """
    strengths: List[str] = Field(default_factory=list)
    editorial_tradeoffs: List[str] = Field(default_factory=list)
    constraint_gaps: List[str] = Field(default_factory=list)

class LibraryHealth(BaseModel):
    """
    Aggregated metrics of the user's clip library.
    """
    asset_count: int = Field(0)
    avg_quality: float = Field(0.0)
    energy_distribution: dict = Field(default_factory=dict)
    primary_subject_distribution: dict = Field(default_factory=dict)
    confidence_score: float = Field(0.0, description="0-100 score of library readiness for the edit")

class VaultReportSection(BaseModel):
    hero: str = Field(..., description="Short, punchy summary sentence")
    body: str = Field(..., description="Detailed explanation following the one-sentence causality rule")

class VaultDecision(BaseModel):
    segment_id: int
    what_i_tried: str = Field(..., description="The initial intent or goal for this segment")
    decision: str = Field(..., description="The final choice and why it was the best move")
    what_if: str = Field(..., description="Counterfactual: what would have changed with different material")
    # v15.0 Vault Layering (Additive)
    is_key: bool = Field(False, description="True if this entry is a key decision (shown by default)")
    importance: str = Field("all", description="'key' or 'all' classification for UI toggles")
    tags: List[str] = Field(default_factory=list, description="Optional symbolic tags for filtering/grouping")

class VaultReport(BaseModel):
    """
    Final human-toned intelligence report for the Vault UI.
    Generated by the Reflector as a translation of VaultReasoning.
    
    v15.1: Relaxed validation for LLM robustness. Non-critical fields default to empty
    to prevent partial LLM responses from breaking the entire Vault page.
    """
    # CRITICAL FIELDS (required for basic Vault functionality)
    header: str = Field(..., description="Context establishment and overall summary")
    advisor: VaultReportSection = Field(..., description="Library health and high-level constraints")
    decision_stream: List[VaultDecision] = Field(..., description="Per-segment reasoning and trade-offs")
    
    # OPTIONAL FIELDS (safe defaults if LLM fails to return them)
    # v15.0 Executive Layer (Additive)
    executive_summary: List[str] = Field(default_factory=list, description="Short bullets for default-collapsed UI")
    # v15.0 Key-vs-All Support (Additive)
    key_decision_stream: List[VaultDecision] = Field(default_factory=list, description="Key decisions only (safe default view)")
    friction_log: List[str] = Field(default_factory=list, description="Temporal awareness: how confidence evolved")
    post_mortem: Dict[str, Any] = Field(default_factory=dict, description="Global strengths, weaknesses, and responsibility")
    next_steps: List[str] = Field(default_factory=list, description="Actionable prescriptions for the user")
    # v15.0 Clip Curation Suggestions (Additive)
    clip_suggestions: List[str] = Field(default_factory=list, description="Clip-level descriptive suggestions for improving future runs")
    technical: List[str] = Field(default_factory=list, description="Behind-the-scenes technical discipline log")

class DirectorCritique(BaseModel):
    """
    Post-render AI reflection on the final edit quality.
    """
    overall_score: float = Field(..., ge=0, le=10, description="1-10 rating of the final edit")
    monologue: str = Field(..., description="A 3-4 sentence 'Director's Voice' explanation of the edit")
    star_performers: List[str] = Field(default_factory=list, description="Clips that carried the narrative perfectly")
    dead_weight: List[str] = Field(default_factory=list, description="Clips that were used but didn't fit the vibe/quality")
    missing_ingredients: List[str] = Field(default_factory=list, description="Specific shot types/vibes needed to reach 10/10")
    remake_actions: List[dict] = Field(default_factory=list, description="Structured deltas for the next iteration (type, segment, suggestion)")
    technical_fidelity: str = Field(..., description="Assessment of beat-sync and energy matching")


# ============================================================================
# ADVISOR-DRIVEN CONTEXTUAL MOMENT SELECTION (v14.0)
# ============================================================================

class MomentCandidate(BaseModel):
    """
    A candidate moment from a clip for consideration by the Advisor.
    Best moments are now candidates, not absolute truth.
    The Advisor selects which moment fits a specific reference segment.
    """
    clip_filename: str
    moment_energy_level: str  # "High", "Medium", or "Low"
    start: float
    end: float
    duration: float
    moment_role: str
    stable_moment: bool
    reason: str
    # Scoring context (filled by editor, used by Advisor)
    semantic_score: float = Field(0.0, description="How well content matches segment vibe")
    musical_alignment: float = Field(0.0, description="Alignment with beat/phrase (0-1)")
    narrative_continuity: float = Field(0.0, description="Flow from previous decisions (0-1)")


class AdvisorAlternative(BaseModel):
    """
    One ranked alternative returned by the per-segment Advisor.
    Editor maps clip_filename + energy_level to pre-computed best_moments timestamps.
    """
    clip_filename: str
    energy_level: str  # High | Medium | Low
    transition_type: str = Field("continue", description="continue | escalate | contrast | release")
    reason: str = Field("", description="One-line editorial justification")
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class ContextualMomentSelection(BaseModel):
    """
    The Advisor's ranked alternatives for a specific segment.
    Editor walks alternatives in order, committing the first valid one.
    """
    segment_id: int
    alternatives: List[AdvisorAlternative] = Field(default_factory=list, description="Ranked picks, best first")
    continuity_intent: str = Field("", description="One-sentence editorial intent for this segment")
    selection: Optional[MomentCandidate] = Field(default=None, description="LEGACY: kept for backward compat, not used")
    reasoning: str = Field("", description="LEGACY")
    confidence: str = Field("Medium", description="LEGACY")
    alternatives_considered: List[Dict[str, Any]] = Field(default_factory=list, description="LEGACY")
    continuity_notes: str = Field("", description="LEGACY")


class SegmentMomentPlan(BaseModel):
    """
    A complete plan for a segment, potentially using multiple moments
    if the duration requires it (chained from same or different clips).
    """
    segment_id: int
    moments: List[MomentCandidate]  # Ordered sequence to fill segment duration
    total_duration: float
    is_single_moment: bool = Field(True, description="True if one moment fills the segment")
    chaining_reason: str | None = Field(None, description="Why multiple moments were needed")
    advisor_alternatives: List[AdvisorAlternative] = Field(
        default_factory=list,
        description="v15.0: Ranked Advisor alternatives for this segment (survives cache)"
    )


class AdvisorHints(BaseModel):
    """
    Complete Gemini Advisor output containing editorial intent reasoning.
    
    ENDGAME VERSION (v3.0): Includes text overlay interpretation as the highest
    authority signal, with clear reasoning hierarchy.
    
    v14.0 UPDATE: Adds segment-level moment selection guidance for Advisor-as-Editor
    contextual moment reasoning.
    
    This is generated once per reference+library combination and cached.
    The hints express editorial intent that the matcher translates into scoring pressure.
    """
    text_overlay_intent: str = Field("", description="Interpreted narrative intent from text overlay (highest authority)")
    dominant_narrative: str = Field("", description="Overall story being told (e.g., 'Shared adventure with friends')")
    arc_stage_guidance: dict[str, ArcStageGuidance] = Field(
        default_factory=dict,
        description="Editorial intent guidance keyed by arc stage: Intro, Build-up, Peak, Outro"
    )
    library_alignment: LibraryAlignment = Field(
        default_factory=LibraryAlignment,
        description="Library assessment: strengths, editorial_tradeoffs, constraint_gaps"
    )
    editorial_strategy: str = Field("", description="One-sentence overall editing strategy")
    remake_strategy: str = Field("", description="Advice for the next iteration to reach Director's Cut quality")
    
    # Narrative Subject Authority (v9.5+)
    primary_narrative_subject: NarrativeSubject | None = Field(None, description="The primary subject that MUST dominate (e.g. People-Group for 'friends')")
    allowed_supporting_subjects: List[NarrativeSubject] = Field(default_factory=list, description="Subjects allowed as fillers/transitions")
    subject_lock_strength: float = Field(1.0, description="Confidence in subject lock (0.0=advisory, 1.0=forced anchor)")
    
    editorial_motifs: List[dict] = Field(default_factory=list, description="High-level continuity patterns (Scale-Escalation, Motion-Carry, etc.)")
    
    # v14.0: Advisor-Driven Contextual Moment Selection
    # Keyed by segment_id, contains the Advisor's moment-level selection for each segment
    segment_moment_plans: Dict[str, SegmentMomentPlan] = Field(
        default_factory=dict,
        description="Per-segment moment plans from Advisor (v14.0 contextual selection)"
    )
    
    # Legacy fields (for backward compatibility with v2.0 cache)
    library_assessment: LibraryAssessment | None = Field(None, description="DEPRECATED: Use library_alignment")
    creative_audit: CreativeAudit | None = Field(None, description="DEPRECATED: Merged into library_alignment")
    overall_strategy: str = Field("", description="DEPRECATED: Use editorial_strategy")
    required_improvements: List[str] = Field(default_factory=list, description="DEPRECATED: No longer used")
    
    cache_version: str = Field("4.2", description="Advisor cache version (4.2 = ranked alternatives, no single pick)")
    cached_at: str = Field("", description="ISO timestamp when cached")



# ============================================================================
# USER CLIP ANALYSIS
# ============================================================================

class BestMoment(BaseModel):
    """
    A single best moment within a clip for a specific energy profile.
    
    Example: {
        "start": 8.2,
        "end": 10.5,
        "moment_role": "Climax",
        "stable_moment": true,
        "reason": "Peak action moment with fast motion"
    }
    """
    start: float = Field(..., ge=0, description="Start time in seconds")
    end: float = Field(..., gt=0, description="End time in seconds")
    moment_role: str = Field("", description="Establishing, Build, Climax, Transition, or Reflection")
    stable_moment: bool = Field(True, description="Whether moment is visually stable for full duration")
    reason: str | None = Field(None, description="Why this moment was selected")
    
    @field_validator('end')
    @classmethod
    def end_after_start(cls, v, info):
        if 'start' in info.data and v <= info.data['start']:
            raise ValueError('end must be greater than start')
        return v


class ClipMetadata(BaseModel):
    """
    Comprehensive analysis result for a single user clip.
    ...
    """
    model_config = ConfigDict(populate_by_name=True)
    
    filename: str
    filepath: str
    duration: float = Field(..., gt=0)
    energy: EnergyLevel
    motion: MotionType
    
    # Enhanced classification (v7.0+)
    intensity: int = Field(2, ge=1, le=3, description="Intensity within energy level (1=mild, 2=clear, 3=strong)")
    
    # Semantic content analysis (v7.0+)
    primary_subject: List[str] = Field(default_factory=list, description="1-2 primary subject categories")
    narrative_utility: List[str] = Field(default_factory=list, description="1-3 narrative roles this clip can serve")
    emotional_tone: List[str] = Field(default_factory=list, description="1-2 emotional tones")
    
    # Editing usability (v7.0+)
    clip_quality: int = Field(3, ge=1, le=5, description="Visual appeal and usefulness (1-5 scale)")
    best_for: List[str] = Field(default_factory=list, description="2-3 editing contexts where clip excels")
    avoid_for: List[str] = Field(default_factory=list, description="1-2 contexts to avoid")
    
    # Legacy fields (maintained for backward compatibility)
    vibes: List[str] = Field(default_factory=list, description="Aesthetic/Content tags for semantic matching")
    content_description: str | None = Field(None, description="Detailed AI description of what is happening in the clip")
    
    # Pre-computed best moments for each energy level (filled during comprehensive analysis)
    best_moments: dict[str, BestMoment] | None = Field(
        None, 
        description="Best moments keyed by energy level (High/Medium/Low)"
    )

    # Identity Passport (v12.1)
    contract: dict = Field(default_factory=dict, alias="_contract", serialization_alias="_contract", validation_alias="_contract", description="Self-describing identity: version, type, source_hash")
    
    # Legacy fields for backward compatibility (deprecated - use best_moments instead)
    best_moment_start: float | None = Field(None, ge=0, description="DEPRECATED: Use best_moments instead")
    best_moment_end: float | None = Field(None, gt=0, description="DEPRECATED: Use best_moments instead")
    
    def get_best_moment_for_energy(self, energy: EnergyLevel) -> tuple[float, float] | None:
        """
        Get the best moment timestamps for a specific energy level.
        
        Returns:
            Tuple of (start, end) or None if not available
        """
        if self.best_moments and energy.value in self.best_moments:
            moment = self.best_moments[energy.value]
            return (moment.start, moment.end)
        
        # Fallback to legacy fields
        if self.best_moment_start is not None and self.best_moment_end is not None:
            return (self.best_moment_start, self.best_moment_end)
        
        return None
    
    @field_validator('best_moment_end')
    @classmethod
    def validate_best_moment(cls, v, info):
        if v is not None and 'best_moment_start' in info.data:
            start = info.data.get('best_moment_start')
            if start is not None and v <= start:
                raise ValueError('best_moment_end must be greater than best_moment_start')
            if 'duration' in info.data and v > info.data['duration']:
                raise ValueError('best_moment_end cannot exceed clip duration')
        return v


class ClipIndex(BaseModel):
    """Collection of all analyzed user clips."""
    clips: List[ClipMetadata] = Field(..., min_length=1)


# ============================================================================
# EDIT DECISION LIST (EDL)
# ============================================================================

class EditDecision(BaseModel):
    """
    A single edit instruction: "Use clip X from time A to B".

    Example: {
        "segment_id": 1,
        "clip_path": "/temp/xyz/clips/dance.mp4",
        "clip_start": 0.0,
        "clip_end": 2.3,
        "timeline_start": 0.0,
        "timeline_end": 2.3
    }
    """
    segment_id: int = Field(..., ge=1)
    clip_path: str
    clip_start: float = Field(..., ge=0, description="Start time in source clip")
    clip_end: float = Field(..., gt=0, description="End time in source clip")
    timeline_start: float = Field(..., ge=0, description="Start time in final video")
    timeline_end: float = Field(..., gt=0, description="End time in final video")
    hold_end_seconds: Optional[float] = Field(None, ge=0, description="Demo fill: hold last frame this long so slot duration matches timeline")

    # Matching metadata for Thinking UI
    reasoning: str = Field("", description="Why this clip was chosen for this segment")
    vibe_match: bool = Field(False, description="Did the vibes match?")


class EDL(BaseModel):
    """
    Complete Edit Decision List for video assembly.
    This is the "recipe" for FFmpeg to follow.
    """
    decisions: List[EditDecision]
    
    @field_validator('decisions')
    @classmethod
    def validate_timeline(cls, v):
        if not v:
            raise ValueError('EDL cannot be empty')
        
        # Check timeline continuity
        for i in range(len(v) - 1):
            if abs(v[i].timeline_end - v[i+1].timeline_start) > 0.01:
                raise ValueError(f'Timeline gap/overlap between decisions {i} and {i+1}')
        
        return v


# ============================================================================
# PIPELINE RESULT
# ============================================================================

class PipelineResult(BaseModel):
    """
    Final output from orchestrator.run_mimic_pipeline().
    """
    model_config = ConfigDict(populate_by_name=True)
    
    success: bool
    output_path: str | None = None
    blueprint: StyleBlueprint | None = None
    clip_index: ClipIndex | None = None
    edl: EDL | None = None
    advisor: AdvisorHints | None = None  # NEW: Strategic guidance used
    critique: DirectorCritique | None = None # NEW: Post-render reflection
    library_health: LibraryHealth | None = None # NEW: Aggregated library metrics
    style_config: Optional['StyleConfig'] = Field(None, description="Current visual styling configuration")
    iteration: int = Field(1, description="The version/iteration of this result")
    error: str | None = None
    processing_time_seconds: float | None = None
    
    # Identity Passport (v12.1)
    contract: dict = Field(default_factory=dict, alias="_contract", serialization_alias="_contract", validation_alias="_contract", description="Result identity contract")
    vault_report: Optional[VaultReport] = Field(None, description="Human-toned intelligence report for the Vault")

