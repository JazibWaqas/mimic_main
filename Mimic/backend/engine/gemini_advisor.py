"""
Gemini Advisor: Strategic clip selection guidance system.

The Advisor provides high-level suggestions that BIAS the matcher
without replacing it. This maintains determinism while adding
narrative intelligence.
"""

import json
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime

from models import (
    StyleBlueprint,
    ClipIndex,
    ClipMetadata,
    Segment,
    AdvisorHints,
    ArcStageGuidance,
    LibraryAssessment,
    CreativeAudit,
    SegmentMomentPlan
)
from engine.gemini_advisor_prompt import ADVISOR_PROMPT
from engine.brain import call_deepseek_v3, _parse_json_response
from engine.moment_selector import (
    build_moment_candidates,
    select_moment_with_advisor,
    plan_segment_moments
)
import time

# ============================================================================
# V14.0 CONTEXTUAL MOMENT SELECTION - FEATURE FLAG
# ============================================================================
# Phase 1: Minimal activation - visual origin + Long hold + Intro/Peak only
# Phase 2: Expand to all visual-origin segments after validation
ENABLE_CONTEXTUAL_MOMENTS = True

# Which segments to process with V14.0 (empty = all, or list of segment IDs)
# Phase 1: Intro (segment 1) + Peak (segment 7) with visual origin + Long hold
# v14.9 RELEASE: Fully enabled for all segments
V14_SEGMENT_WHITELIST = []


def _should_use_v14_moment_selection(segment) -> bool:
    """
    Determine if a segment should use V14.0 contextual moment selection.
    
    Criteria (all must match):
    - Segment ID in whitelist
    - cut_origin == "visual" (sacred cuts, no subdivision risk)
    - expected_hold == "Long" (where music phrasing matters most)
    """
    if not V14_SEGMENT_WHITELIST:
        return True  # Whitelist empty = process all
    
    if segment.id not in V14_SEGMENT_WHITELIST:
        return False
    
    # Must be visual origin (sacred cuts, no subdivision)
    cut_origin = getattr(segment, 'cut_origin', 'visual')
    if cut_origin != 'visual':
        return False
    
    # Must be Long hold (where contextual selection matters most)
    expected_hold = getattr(segment, 'expected_hold', 'Normal')
    if expected_hold != 'Long':
        return False
    
    return True


def _generate_moment_plans_for_hints(
    hints: AdvisorHints,
    blueprint: StyleBlueprint,
    clip_index: ClipIndex,
    beat_grid: Optional[list] = None
) -> AdvisorHints:
    """
    Generate contextual moment plans for cached hints that lack them.
    
    This is the V14.0 moment selection logic extracted for reuse.
    Called when cached hints are loaded but ENABLE_CONTEXTUAL_MOMENTS is True.
    """
    from typing import Dict, Any
    from engine.moment_selector import build_moment_candidates, select_moment_with_advisor, plan_segment_moments
    
    if beat_grid is None:
        beat_grid = []
    
    print(f"\n  [MATCH] V14.0: Generating contextual moment plans...")
    segment_moment_plans: Dict[str, Any] = {}
    
    # Determine which segments to process
    # Phase 1: Only segments matching visual + Long + whitelist criteria
    target_segments = []
    for seg in blueprint.segments:
        if _should_use_v14_moment_selection(seg):
            target_segments.append(seg)
    
    if not target_segments:
        print(f"  [FALLBACK] V14.0: No segments match criteria (visual + Long + whitelist)")
        print(f"     Whitelist: {V14_SEGMENT_WHITELIST}")
    else:
        print(f"     Processing {len(target_segments)} segment(s) with V14.0")
    
    used_clips: dict = {}  # filename -> times committed (tracked forward across segments)
    recent_picks: list = []  # last 5 picks as dicts with content/tone
    previous_selection = None
    for segment in target_segments:
        try:
            print(f"     Segment {segment.id}: Building candidates...", end=" ")
            
            candidates = build_moment_candidates(
                clip_index=clip_index,
                target_energy=segment.energy.value,
                segment=segment,
                beat_grid=beat_grid,
                previous_selection=previous_selection
            )
            
            if not candidates:
                print(f"[WARN] No candidates")
                continue
            
            print(f"[OK] {len(candidates)} candidates")
            
            from engine.editor import calculate_cut_density_expectation
            cde = calculate_cut_density_expectation(segment, beat_grid, blueprint, "REFERENCE")
            
            print(f"     Segment {segment.id}: Calling Advisor...", end=" ")
            selection = select_moment_with_advisor(
                segment=segment,
                candidates=candidates,
                beat_grid=beat_grid,
                blueprint=blueprint,
                clip_index=clip_index,
                previous_selection=previous_selection,
                cde=cde,
                used_clips=used_clips,
                recent_picks=recent_picks[-5:]
            )
            
            if not selection or not selection.alternatives:
                raise ValueError("No alternatives returned")
            
            top = selection.alternatives[0]
            print(f"[OK] Top pick: {top.clip_filename} [{top.energy_level}] ({top.transition_type})")
            
            # Build a SegmentMomentPlan using the alternatives directly
            # The editor will waterfall through alternatives - no timestamps here
            plan = SegmentMomentPlan(
                segment_id=segment.id,
                moments=[],
                total_duration=segment.duration,
                is_single_moment=True,
                chaining_reason=selection.continuity_intent,
                advisor_alternatives=selection.alternatives
            )
            plan_key = str(segment.id)
            segment_moment_plans[plan_key] = plan
            
            # Update Advisor state tracking to preserve narrative memory
            from models import MomentCandidate
            clip_meta = next((c for c in clip_index.clips if c.filename == top.clip_filename), None)
            if clip_meta:
                used_clips[top.clip_filename] = used_clips.get(top.clip_filename, 0) + 1
                recent_picks.append({
                    "clip": top.clip_filename,
                    "energy": top.energy_level,
                    "tone": clip_meta.emotional_tone if hasattr(clip_meta, "emotional_tone") else [],
                    "content": clip_meta.content_description if hasattr(clip_meta, "content_description") else ""
                })
                previous_selection = MomentCandidate(
                    clip_filename=top.clip_filename,
                    moment_energy_level=top.energy_level,
                    start=0.0,
                    end=0.0,
                    duration=segment.duration,
                    moment_role=top.transition_type,
                    stable_moment=True,
                    reason=top.reason
                )
            else:
                previous_selection = None
            
            print(f"     [OK] Plan stored with {len(selection.alternatives)} alternatives")
            
        except Exception as e:
            raise ValueError(f"Segment {segment.id} V14.0 moment plan failed: {e}") from e
    
    # Attach moment plans to hints
    if segment_moment_plans:
        hints.segment_moment_plans = segment_moment_plans
        print(f"  [OK] V14.0: {len(segment_moment_plans)} segment(s) with contextual moment plans")
    else:
        if target_segments:
            raise ValueError("V14.0 enabled but produced no moment plans")
        print(f"  [FALLBACK] V14.0: No segments matched criteria")
    
    return hints


def get_advisor_suggestions(
    blueprint: StyleBlueprint,
    clip_index: ClipIndex,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    scarcity_report: Optional[dict] = None,
    bpm: Optional[float] = None
) -> Optional[AdvisorHints]:
    """
    Get Gemini's strategic suggestions for clip selection.
    
    This generates or retrieves cached advisor hints that influence
    the matcher's scoring without controlling it.
    
    Args:
        blueprint: Analyzed reference structure with narrative intent
        clip_index: Analyzed user clips with semantic metadata
        cache_dir: Directory for caching advisor results (defaults to root data/cache/advisor)
        force_refresh: If True, bypass cache and regenerate
    
    Returns:
        AdvisorHints if successful, None if failure (graceful degradation)
    """
    if cache_dir is None:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        cache_dir = BASE_DIR / "data" / "cache" / "advisor"

    print(f"\n{'='*60}")
    print(f"[ADVISOR] GENERATING STRATEGIC GUIDANCE")
    print(f"{'='*60}")
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # v12.1 Authority Assertion: Handshake between Reference and Advisor.
    # Text-prompt blueprints use the generator contract instead of reference-analysis
    # cache versions, so they are authoritative when explicitly marked as generated.
    from engine.brain import REFERENCE_CACHE_VERSION
    blueprint_ver = blueprint.contract.get("version", "0.0") if blueprint.contract else "0.0"
    blueprint_source = blueprint.contract.get("source", "") if blueprint.contract else ""
    is_text_prompt_blueprint = blueprint_source.startswith("text_prompt") or bool(getattr(blueprint, "text_prompt", None))
    if blueprint_ver != REFERENCE_CACHE_VERSION and not is_text_prompt_blueprint:
        print(f"  NO AUTHORITY FAILURE: Blueprint version ({blueprint_ver}) != Required ({REFERENCE_CACHE_VERSION})")
        print(f"  [WARN] Skipping strategic guidance. Please re-analyze reference {blueprint.contract.get('source_hash', 'unknown') if blueprint.contract else ''}")
        return None
    
    if is_text_prompt_blueprint and blueprint_ver != REFERENCE_CACHE_VERSION:
        print(f"  [OK] Text blueprint authority confirmed: v{blueprint_ver} ({blueprint_source or 'prompt mode'})")
    else:
        print(f"  [OK] Authority Confirmed: v{blueprint_ver} Director-Soul Intelligence active.")
    
    from engine.processors import get_beat_grid as _get_beat_grid
    beat_grid: list = []
    if bpm and getattr(blueprint, "total_duration", None) and bpm > 0:
        try:
            beat_grid = _get_beat_grid(blueprint.total_duration, bpm)
            print(f"  [MUSIC] Beat grid for advisor: {len(beat_grid)} beats at {bpm:.1f} BPM")
        except Exception:
            pass
    
    ref_hash = hashlib.md5(
        (blueprint.narrative_message + str(blueprint.segments)).encode()
    ).hexdigest()
    
    library_hash = hashlib.md5(
        "".join(sorted(c.filename for c in clip_index.clips)).encode()
    ).hexdigest()

    cache_key = f"advisor_{ref_hash}_{library_hash}.json"
    cache_file = cache_dir / cache_key

    if not force_refresh and cache_file.exists():
        try:
            print(f"  [CACHE] Loading cached advisor hints...")
            data = json.loads(cache_file.read_text(encoding='utf-8'))
            
            cache_version = data.get("cache_version", "1.0")
            if cache_version != "4.2":
                print(f"  [WARN] Cache version mismatch ({cache_version} vs 4.2), regenerating...")
                cache_file.unlink()
            else:
                hints = AdvisorHints(**data)
                print(f"  [OK] Loaded from cache: {cache_file.name}")
                
                # V14.0: If cached hints lack moment plans but V14 is enabled, generate them now
                if ENABLE_CONTEXTUAL_MOMENTS and not hints.segment_moment_plans:
                    print(f"  [MATCH] V14.0: Cached hints lack moment plans, generating now...")
                    hints = _generate_moment_plans_for_hints(hints, blueprint, clip_index, beat_grid=beat_grid)
                    # Update cache with moment plans
                    cache_file.write_text(hints.model_dump_json(indent=2), encoding='utf-8')
                    print(f"  [OK] Cache updated with moment plans")
                
                return hints
        except Exception as e:
            print(f"  [WARN] Cache corrupted, regenerating: {e}")
    
    print(f"  [AI] Calling DeepSeek for strategic guidance...")
    
    blueprint_summary = _format_blueprint_summary(blueprint)
    library_summary = _format_clip_library_summary(clip_index)
    
    prompt = ADVISOR_PROMPT.format(
        blueprint_summary=blueprint_summary,
        clip_library_summary=library_summary,
        scarcity_report=json.dumps(scarcity_report or {}, indent=2)
    )
    
    for attempt in range(2):
        try:
            data = call_deepseek_v3(prompt=prompt)
            raw_response_text = json.dumps(data)
            
            # P0: Parse with detailed error handling
            try:
                data = _parse_json_response(raw_response_text)
            except Exception as parse_error:
                print(f"  [ERROR] JSON PARSE FAILED: {parse_error}")
                raise ValueError(f"JSON parsing failed: {parse_error}") from parse_error
            
            cached_at = datetime.utcnow().isoformat()
            
            # P0: Validate required fields before Pydantic parsing
            required_fields = ['text_overlay_intent', 'dominant_narrative', 'arc_stage_guidance']
            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                print(f"  [ERROR] SCHEMA VALIDATION FAILED - Missing fields: {missing_fields}")
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            # Parse arc stage guidance (intent-driven)
            arc_guidance = {}
            for stage, guidance_data in data.get('arc_stage_guidance', {}).items():
                try:
                    # Handle both old "recommended_clips" and new "exemplar_clips"
                    if 'exemplar_clips' in guidance_data:
                        guidance_data['recommended_clips'] = guidance_data['exemplar_clips']
                    arc_guidance[stage] = ArcStageGuidance(**guidance_data)
                except Exception as e:
                    print(f"  [WARN] Failed to parse guidance for {stage}: {e}")
            
            # Validate arc stage coverage
            blueprint_stages = {seg.arc_stage for seg in blueprint.segments}
            missing_stages = blueprint_stages - set(arc_guidance.keys())
            if missing_stages:
                print(f"  [WARN] Advisor provided incomplete arc coverage. Missing: {missing_stages}")
                print(f"  [FALLBACK] These stages will use energy/motion matching only")

            
            # Parse narrative subject lock (v9.5+)
            from models import NarrativeSubject, LibraryAlignment
            primary_subject = None
            if data.get('primary_narrative_subject'):
                try:
                    primary_subject = NarrativeSubject(data['primary_narrative_subject'])
                except ValueError:
                    pass
            
            allowed_subjects = []
            for s in data.get('allowed_supporting_subjects', []):
                try:
                    allowed_subjects.append(NarrativeSubject(s))
                except ValueError:
                    pass
            
            # Parse library_alignment
            library_alignment_data = data.get('library_alignment', {})
            if isinstance(library_alignment_data, dict):
                library_alignment = LibraryAlignment(**library_alignment_data)
            else:
                library_alignment = LibraryAlignment()

            # P0: Wrap Pydantic validation with error handling
            try:
                hints = AdvisorHints(
                    text_overlay_intent=data.get('text_overlay_intent', ''),
                    dominant_narrative=data.get('dominant_narrative', ''),
                    
                    primary_narrative_subject=primary_subject,
                    allowed_supporting_subjects=allowed_subjects,
                    subject_lock_strength=float(data.get('subject_lock_strength', 1.0)),
                    
                    arc_stage_guidance=arc_guidance,
                    library_alignment=library_alignment,
                    editorial_strategy=data.get('editorial_strategy', ''),
                    remake_strategy=data.get('remake_strategy', ''),
                    editorial_motifs=data.get('editorial_motifs', []),
                    cached_at=cached_at,
                    cache_version="4.2"  # v15.0: Ranked alternatives, advisor_alternatives field
                )
            except Exception as pydantic_error:
                print(f"  [ERROR] PYDANTIC VALIDATION FAILED: {pydantic_error}")
                raise ValueError(f"Pydantic validation failed: {pydantic_error}") from pydantic_error
            
            # ============================================================================
            # V14.0: CONTEXTUAL MOMENT SELECTION (Phase 1 - Minimal Activation)
            # ============================================================================
            if ENABLE_CONTEXTUAL_MOMENTS and hints:
                print(f"\n  [MATCH] V14.0: Generating contextual moment plans...")
                segment_moment_plans: Dict[str, Any] = {}
                
                # Determine which segments to process
                # Phase 1: Only segments matching visual + Long + whitelist criteria
                target_segments = []
                for seg in blueprint.segments:
                    if _should_use_v14_moment_selection(seg):
                        target_segments.append(seg)
                
                if not target_segments:
                    print(f"  [FALLBACK] V14.0: No segments match criteria (visual + Long + whitelist)")
                    print(f"     Whitelist: {V14_SEGMENT_WHITELIST}")
                else:
                    print(f"     Processing {len(target_segments)} segment(s) with V14.0")
                
                used_clips: dict = {}
                recent_picks: list = []
                previous_selection = None
                for segment in target_segments:
                    try:
                        print(f"     Segment {segment.id}: Building candidates...", end=" ")
                        
                        candidates = build_moment_candidates(
                            clip_index=clip_index,
                            target_energy=segment.energy.value,
                            segment=segment,
                            beat_grid=beat_grid,
                            previous_selection=previous_selection
                        )
                        
                        if not candidates:
                            print(f"[WARN] No candidates")
                            continue
                        
                        print(f"[OK] {len(candidates)} candidates")
                        
                        from engine.editor import calculate_cut_density_expectation
                        cde = calculate_cut_density_expectation(segment, beat_grid, blueprint, "REFERENCE")
                        
                        print(f"     Segment {segment.id}: Calling Advisor...", end=" ")
                        selection = select_moment_with_advisor(
                            segment=segment,
                            candidates=candidates,
                            beat_grid=beat_grid,
                            blueprint=blueprint,
                            clip_index=clip_index,
                            previous_selection=previous_selection,
                            cde=cde,
                            used_clips=used_clips,
                            recent_picks=recent_picks[-5:]
                        )
                        
                        if not selection or not selection.alternatives:
                            raise ValueError("No alternatives returned")
                        
                        top = selection.alternatives[0]
                        print(f"[OK] Top pick: {top.clip_filename} [{top.energy_level}] ({top.transition_type})")
                        
                        plan = SegmentMomentPlan(
                            segment_id=segment.id,
                            moments=[],
                            total_duration=segment.duration,
                            is_single_moment=True,
                            chaining_reason=selection.continuity_intent,
                            advisor_alternatives=selection.alternatives
                        )
                        plan_key = str(segment.id)
                        segment_moment_plans[plan_key] = plan
                        
                        # Update Advisor state tracking to preserve narrative memory
                        from models import MomentCandidate
                        clip_meta = next((c for c in clip_index.clips if c.filename == top.clip_filename), None)
                        if clip_meta:
                            used_clips[top.clip_filename] = used_clips.get(top.clip_filename, 0) + 1
                            recent_picks.append({
                                "clip": top.clip_filename,
                                "energy": top.energy_level,
                                "tone": clip_meta.emotional_tone if hasattr(clip_meta, "emotional_tone") else [],
                                "content": clip_meta.content_description if hasattr(clip_meta, "content_description") else ""
                            })
                            previous_selection = MomentCandidate(
                                clip_filename=top.clip_filename,
                                moment_energy_level=top.energy_level,
                                start=0.0,
                                end=0.0,
                                duration=segment.duration,
                                moment_role=top.transition_type,
                                stable_moment=True,
                                reason=top.reason
                            )
                        else:
                            previous_selection = None
                        
                        print(f"     [OK] Plan stored with {len(selection.alternatives)} alternatives")
                        
                    except Exception as e:
                        raise ValueError(f"Segment {segment.id} V14.0 moment plan failed: {e}") from e
                
                # Attach moment plans to hints
                if segment_moment_plans:
                    hints.segment_moment_plans = segment_moment_plans
                    print(f"  [OK] V14.0: {len(segment_moment_plans)} segment(s) with contextual moment plans")
                else:
                    if target_segments:
                        raise ValueError("V14.0 enabled but produced no moment plans")
                    print(f"  [FALLBACK] V14.0: No segments matched criteria")
            
            # ============================================================================
            # Cache and return
            # ============================================================================
            cache_file.write_text(hints.model_dump_json(indent=2), encoding='utf-8')
            print(f"  [OK] Advisor hints generated and cached")
            print(f"  [INFO] Text Overlay Intent: {hints.text_overlay_intent}")
            print(f"  [NARRATIVE] Dominant Narrative: {hints.dominant_narrative}")
            print(f"  [MATCH] Editorial Strategy: {hints.editorial_strategy}")
            
            return hints
            
        except Exception as e:
            print(f"  [ERROR] Advisor attempt {attempt + 1} failed: {e}")
            if attempt == 1:
                print(f"\n{'='*60}")
                print(f"  NONONO ADVISOR FAILED AFTER ALL RETRIES NONONO")
                print(f"{'='*60}")
                print(f"  [WARN] SEMANTIC MATCHING DISABLED - Vibe accuracy will be 0%")
                print(f"  [WARN] System will fall back to energy/motion matching only")
                print(f"{'='*60}\n")
                return None
            time.sleep(1.0)
    
    return None


def compute_advisor_bonus(
    clip: ClipMetadata,
    segment: Segment,
    blueprint: StyleBlueprint,
    advisor_hints: Optional[AdvisorHints]
) -> int:
    """
    Translate Advisor's editorial intent into scoring pressure.
    
    This is NOT rule enforcement - it's priority weighting based on
    whether the clip matches the editorial intent for this arc stage.
    
    Args:
        clip: Candidate clip being scored
        segment: Current segment being filled
        blueprint: Reference analysis with narrative intent
        advisor_hints: Advisor guidance (can be None for graceful degradation)
    
    Returns:
        Bonus score (typically in range -50 to +60)
    """
    if not advisor_hints:
        return 0
    
    bonus = 0
    
    # Get editorial guidance for this arc stage
    guidance = advisor_hints.arc_stage_guidance.get(segment.arc_stage)
    if not guidance:
        return 0
    
    # Check if clip matches PRIMARY EMOTIONAL CARRIER (+60 strong boost)
    primary_match = _matches_intent(clip, guidance.primary_emotional_carrier)
    if primary_match:
        bonus += 60
    
    # Check if clip is SUPPORTING MATERIAL (+15 mild boost)
    supporting_match = _matches_intent(clip, guidance.supporting_material)
    if not primary_match and supporting_match:
        bonus += 15
    
    # Check if clip DILUTES INTENT (-50 penalty, but not forbidden)
    dilutes_match = _matches_intent(clip, guidance.intent_diluting_material)
    if dilutes_match:
        bonus -= 50
    
    # CRITICAL FIX: For Build-up, if primary carrier mentions "people" but clip has no people,
    # treat it as intent-diluting even if it wasn't explicitly listed
    if segment.arc_stage == "Build-up":
        primary_needs_people = "people" in guidance.primary_emotional_carrier.lower() or \
                              "group" in guidance.primary_emotional_carrier.lower() or \
                              "shared" in guidance.primary_emotional_carrier.lower()
        
        clip_has_people = any("People" in subj for subj in clip.primary_subject)
        
        if primary_needs_people and not clip_has_people and not primary_match:
            # This is a scenic clip in a people-driven Build-up segment
            bonus -= 40  # Penalty for missing the primary carrier
    
    # Boost clips that are specifically recommended as exemplars
    if clip.filename in guidance.recommended_clips:
        bonus += 20
    
    # Content alignment bonuses (from blueprint must_have/should_have)
    exact_must, category_must = _match_content_requirements(
        clip, blueprint.must_have_content
    )
    if exact_must:
        bonus += 20
    elif category_must:
        bonus += 10
    
    exact_should, category_should = _match_content_requirements(
        clip, blueprint.should_have_content
    )
    if exact_should:
        bonus += 10
    elif category_should:
        bonus += 5
    
    # Quality bonus
    if clip.clip_quality >= 4:
        bonus += 5
    
    # Stable moments for Intro/Outro
    if segment.arc_stage in ["Intro", "Outro"]:
        if clip.best_moments:
            energy_key = segment.energy.value.capitalize()
            best_moment = clip.best_moments.get(energy_key)
            if best_moment and best_moment.stable_moment:
                bonus += 10
    
    return bonus


def _matches_intent(clip: ClipMetadata, intent_description: str) -> bool:
    """
    Simple semantic matching between clip metadata and intent description.
    
    This is intentionally fuzzy - we're checking if the clip's semantic
    tags align with the Advisor's editorial reasoning.
    """
    if not intent_description:
        return False
    
    intent_lower = intent_description.lower()
    
    # Check if intent requires people
    intent_needs_people = any(keyword in intent_lower for keyword in [
        "people", "group", "shared", "celebrating", "laughing", "human", "friends"
    ])
    
    clip_has_people = any("People" in subj for subj in clip.primary_subject)
    
    # If intent needs people but clip has none, no match
    if intent_needs_people and not clip_has_people:
        return False
    
    # If intent is about scenic/landscapes and clip is scenic, match
    if any(keyword in intent_lower for keyword in ["scenic", "landscape", "atmospheric", "establishing"]):
        if any("Place" in subj for subj in clip.primary_subject):
            return True
    
    # Check primary_subject for specific matches
    for subject in clip.primary_subject:
        if "People" in subject:
            # People-related intent keywords
            if any(keyword in intent_lower for keyword in [
                "people", "group", "shared", "celebrating", "laughing", "human",
                "connection", "interaction", "friends", "social"
            ]):
                return True
        
        if "Celebration" in subject and "celebrat" in intent_lower:
            return True
        
        if "Travel" in subject and any(keyword in intent_lower for keyword in [
            "journey", "transit", "travel", "moving"
        ]):
            return True
        
        if "Leisure" in subject and any(keyword in intent_lower for keyword in [
            "leisure", "casual", "relaxed"
        ]):
            return True
    
    # Check emotional_tone
    for tone in clip.emotional_tone:
        if tone.lower() in intent_lower:
            return True
    
    # Check narrative_utility
    for utility in clip.narrative_utility:
        if utility.lower() in intent_lower:
            return True
    
    return False


def _match_content_requirements(
    clip: ClipMetadata,
    requirements: list[str]
) -> Tuple[bool, bool]:
    """
    Check if clip matches content requirements.
    
    Uses a two-tier matching system:
    - Exact: Full subject name appears in requirement text
    - Category: Subject category (first part before dash) appears in requirement
    
    Args:
        clip: Clip with primary_subject field
        requirements: List of content requirement strings from reference
    
    Returns:
        Tuple of (exact_match, category_match)
    """
    exact_match = False
    category_match = False
    
    clip_categories = {s.split('-')[0].lower() for s in clip.primary_subject}
    
    for req in requirements:
        req_lower = req.lower()
        
        for subject in clip.primary_subject:
            subject_clean = subject.lower().replace('-', ' ')
            if subject_clean in req_lower or any(part in req_lower for part in subject_clean.split()):
                exact_match = True
                break
        
        for cat in clip_categories:
            if cat in req_lower:
                category_match = True
                break
    
    return exact_match, category_match


def _format_blueprint_summary(blueprint: StyleBlueprint) -> str:
    """
    Format blueprint into a concise summary for the Gemini prompt.
    """
    lines = []
    
    lines.append(f"Duration: {blueprint.total_duration:.1f}s")
    lines.append(f"Editing Style: {blueprint.editing_style}")
    lines.append(f"Emotional Intent: {blueprint.emotional_intent}")
    
    if blueprint.text_overlay:
        lines.append(f"Text Overlay: \"{blueprint.text_overlay}\"")
        if blueprint.text_style:
            lines.append(f"Text Style: {blueprint.text_style}")
    
    if blueprint.color_grading:
        lines.append(f"Color Grading: {blueprint.color_grading}")
    if blueprint.visual_effects:
        lines.append(f"Visual Effects: {', '.join(blueprint.visual_effects)}")
    if blueprint.aspect_ratio:
        lines.append(f"Aspect Ratio: {blueprint.aspect_ratio}")

    lines.append(f"\nNarrative Message: {blueprint.narrative_message}")
    lines.append(f"Intent Clarity: {blueprint.intent_clarity}")
    
    if blueprint.must_have_content:
        lines.append(f"\nMust-Have Content:")
        for item in blueprint.must_have_content:
            lines.append(f"  - {item}")
    
    if blueprint.should_have_content:
        lines.append(f"\nShould-Have Content:")
        for item in blueprint.should_have_content:
            lines.append(f"  - {item}")
    
    if blueprint.avoid_content:
        lines.append(f"\nAvoid Content:")
        for item in blueprint.avoid_content:
            lines.append(f"  - {item}")
    
    lines.append(f"\nPacing Feel: {blueprint.pacing_feel}")
    lines.append(f"Visual Balance: {blueprint.visual_balance}")
    lines.append(f"Arc Description: {blueprint.arc_description}")
    
    arc_stages = {}
    for seg in blueprint.segments:
        stage = seg.arc_stage
        if stage not in arc_stages:
            arc_stages[stage] = []
        arc_stages[stage].append(seg)
    
    lines.append(f"\nArc Stage Breakdown:")
    for stage, segments in arc_stages.items():
        energy_counts = {}
        functions = set()
        for seg in segments:
            energy_counts[seg.energy.value] = energy_counts.get(seg.energy.value, 0) + 1
            if seg.shot_function:
                functions.add(seg.shot_function)
        
        energy_str = ", ".join(f"{count}x {energy}" for energy, count in energy_counts.items())
        func_str = f" [Functions: {', '.join(functions)}]" if functions else ""
        lines.append(f"  {stage}: {len(segments)} segments ({energy_str}){func_str}")
    
    return "\n".join(lines)


def _format_clip_library_summary(clip_index: ClipIndex) -> str:
    """
    Format clip library into a concise summary for the Gemini prompt.
    """
    lines = []
    lines.append(f"Total Clips: {len(clip_index.clips)}\n")
    
    for clip in clip_index.clips:
        clip_info = [
            f"Filename: {clip.filename}",
            f"Duration: {clip.duration:.1f}s",
            f"Energy: {clip.energy.value} (intensity: {clip.intensity})",
            f"Motion: {clip.motion.value}",
            f"Primary Subject: {', '.join(clip.primary_subject)}",
            f"Narrative Utility: {', '.join(clip.narrative_utility)}",
            f"Emotional Tone: {', '.join(clip.emotional_tone)}",
            f"Quality: {clip.clip_quality}/5",
            f"Best For: {', '.join(clip.best_for)}",
        ]
        
        if clip.avoid_for:
            clip_info.append(f"Avoid For: {', '.join(clip.avoid_for)}")
        
        if clip.content_description:
            clip_info.append(f"Content: {clip.content_description}")
        
        lines.append("  " + " | ".join(clip_info))
    
    return "\n".join(lines)

