"""
Contextual Moment Selection Engine: Advisor-driven clip-to-segment matching.

v14.0 ADVISOR-AS-EDITOR VERSION:
- Builds moment candidates from all available clips
- Calls Advisor to make contextual selections per segment
- Matcher executes Advisor's decisions deterministically
"""

import json
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from models import (
    MomentCandidate, 
    ContextualMomentSelection,
    AdvisorAlternative,
    SegmentMomentPlan,
    ClipMetadata,
    ClipIndex,
    StyleBlueprint,
    Segment
)
from engine.brain import call_deepseek_v3, _parse_json_response
from engine.gemini_moment_prompt import CONTEXTUAL_MOMENT_PROMPT


def build_moment_candidates(
    clip_index: ClipIndex,
    target_energy: str,
    segment: Segment,
    beat_grid: List[float],
    previous_selection: Optional[MomentCandidate] = None
) -> List[MomentCandidate]:
    """
    Build a list of all candidate moments from all clips.
    
    Unlike the old system that picked one "best" moment per clip,
    this exposes ALL moments (High/Medium/Low) from ALL clips
    so the Advisor can make contextual decisions.
    
    Args:
        clip_index: All analyzed clips
        target_energy: Preferred energy level (but all levels included)
        segment: The reference segment we're filling
        beat_grid: Beat timestamps for musical alignment scoring
        previous_selection: The previous segment's selection (for continuity)
    
    Returns:
        List of MomentCandidate objects with pre-calculated context scores
    """
    candidates = []
    
    for clip in clip_index.clips:
        if not clip.best_moments:
            continue
        
        # Include ALL energy levels, not just target
        # The Advisor decides which level fits this segment
        for energy_level, moment in clip.best_moments.items():
            # Pre-calculate semantic alignment
            semantic_score = _calculate_semantic_alignment(clip, segment, moment)
            
            # Pre-calculate musical alignment
            musical_alignment = _calculate_musical_alignment(
                moment.start, moment.end, beat_grid
            )
            
            # Pre-calculate narrative continuity
            narrative_continuity = 0.0
            if previous_selection:
                narrative_continuity = _calculate_continuity(
                    previous_selection, clip, moment
                )
            
            candidate = MomentCandidate(
                clip_filename=clip.filename,
                moment_energy_level=energy_level,
                start=moment.start,
                end=moment.end,
                duration=moment.end - moment.start,
                moment_role=moment.moment_role,
                stable_moment=moment.stable_moment,
                reason=moment.reason or "",
                semantic_score=semantic_score,
                musical_alignment=musical_alignment,
                narrative_continuity=narrative_continuity
            )
            candidates.append(candidate)
    
    return candidates


def _calculate_semantic_alignment(
    clip: ClipMetadata, 
    segment: Segment,
    moment
) -> float:
    """
    Calculate how well a clip's content aligns with segment needs.
    Returns 0-1 score based on:
    - Vibe matching
    - Shot function alignment
    - Arc stage appropriateness
    """
    score = 0.0
    checks = 0
    
    # Vibe matching
    segment_vibe = (segment.vibe or "").lower()
    clip_vibes = [v.lower() for v in (clip.vibes or [])]
    if segment_vibe and any(segment_vibe in cv or cv in segment_vibe for cv in clip_vibes):
        score += 0.4
    checks += 1
    
    # Shot function alignment
    seg_func = getattr(segment, 'shot_function', None)
    if seg_func and clip.narrative_utility:
        func_map = {
            "Establish": ["establishing"],
            "Action": ["peak", "build"],
            "Reaction": ["reflection", "build"],
            "Detail": ["transition"],
            "Release": ["reflection"]
        }
        target_utils = func_map.get(seg_func, [])
        clip_utils = [u.lower() for u in clip.narrative_utility]
        if any(tu in clip_utils for tu in target_utils):
            score += 0.3
    checks += 1
    
    # Arc stage appropriateness via moment role
    arc_to_role = {
        "Intro": ["Establishing"],
        "Build-up": ["Build", "Transition"],
        "Peak": ["Climax", "Peak"],
        "Outro": ["Reflection", "Establishing"]
    }
    preferred_roles = arc_to_role.get(segment.arc_stage, [])
    if moment.moment_role in preferred_roles:
        score += 0.3
    checks += 1
    
    return score / checks if checks > 0 else 0.0


def _calculate_musical_alignment(
    moment_start: float,
    moment_end: float,
    beat_grid: List[float]
) -> float:
    """
    Calculate how well a moment aligns with musical structure.
    Returns 0-1 based on:
    - Start on or near beat
    - End on or near beat or phrase boundary
    - Duration aligns with beat intervals
    """
    if not beat_grid:
        return 0.5  # Neutral if no beat data
    
    # Check if start is near a beat (within 0.1s tolerance)
    start_near_beat = any(abs(moment_start - b) < 0.1 for b in beat_grid)
    
    # Check if end is near a beat
    end_near_beat = any(abs(moment_end - b) < 0.1 for b in beat_grid)
    
    # Calculate alignment score
    score = 0.0
    if start_near_beat:
        score += 0.4
    if end_near_beat:
        score += 0.4
    
    # Bonus for duration that aligns with beat intervals
    duration = moment_end - moment_start
    beat_intervals = [beat_grid[i+1] - beat_grid[i] for i in range(len(beat_grid)-1)]
    if beat_intervals:
        avg_interval = sum(beat_intervals) / len(beat_intervals)
        # Check if duration is close to integer multiples of beat interval
        if avg_interval > 0:
            beat_multiple = round(duration / avg_interval)
            if abs(duration - (beat_multiple * avg_interval)) < 0.1:
                score += 0.2
    
    return min(1.0, score)


def _calculate_continuity(
    previous: MomentCandidate,
    current_clip: ClipMetadata,
    current_moment
) -> float:
    """
    Calculate narrative continuity between previous selection and current candidate.
    Returns 0-1 based on:
    - Same clip (avoid immediate reuse)
    - Moment role flow (Build -> Climax, not Climax -> Establishing)
    - Semantic similarity
    """
    score = 0.5  # Neutral baseline
    
    # Same clip penalty (avoid immediate reuse)
    if previous.clip_filename == current_clip.filename:
        score -= 0.3
    
    # Moment role flow
    role_flows = {
        "Establishing": ["Build", "Transition"],
        "Build": ["Climax", "Peak", "Transition"],
        "Transition": ["Build", "Climax", "Reflection"],
        "Climax": ["Reflection", "Transition"],
        "Peak": ["Reflection", "Transition"],
        "Reflection": ["Establishing", "Build"]
    }
    valid_next = role_flows.get(previous.moment_role, [])
    if current_moment.moment_role in valid_next:
        score += 0.3
    
    return max(0.0, min(1.0, score))


def _normalize_candidates(
    candidates: List[MomentCandidate],
    target_energy: str,
    max_per_clip: int = 2
) -> List[MomentCandidate]:
    """
    Keep at most max_per_clip entries per unique clip in the candidate list.

    Selection rule per clip:
    - Keep the entry whose energy_level best matches target_energy (best fit)
    - Keep the entry with the most different energy_level (diversity option)
    - Never keep two entries with the same energy_level from the same clip

    This prevents one clip from monopolizing the advisor's visible shortlist.
    """
    energy_order = {"High": 2, "Medium": 1, "Low": 0}
    target_val = energy_order.get(target_energy, 1)

    by_clip: dict = {}
    for c in candidates:
        by_clip.setdefault(c.clip_filename, []).append(c)

    normalized = []
    for clip_name, entries in by_clip.items():
        if len(entries) <= 1:
            normalized.extend(entries)
            continue

        # Best fit: closest energy to target
        best = min(entries, key=lambda c: abs(energy_order.get(c.moment_energy_level, 1) - target_val))
        # Diversity: furthest energy from best fit
        diversity = max(
            [e for e in entries if e.moment_energy_level != best.moment_energy_level],
            key=lambda c: abs(energy_order.get(c.moment_energy_level, 1) - energy_order.get(best.moment_energy_level, 1)),
            default=None
        )
        normalized.append(best)
        if diversity:
            normalized.append(diversity)

    return normalized


def _build_narrative_history(recent_picks: List[dict]) -> str:
    """Format the last N picks into a readable history string for the prompt."""
    if not recent_picks:
        return "No picks yet (this is the first segment)."
    lines = []
    for i, pick in enumerate(recent_picks, 1):
        clip = pick.get("clip", "?")
        energy = pick.get("energy", "?")
        tone = ", ".join(pick.get("tone", [])) or "unknown tone"
        desc = (pick.get("content", "") or "")[:60]
        lines.append(f"{i}. {clip} [{energy}] - {desc} ({tone})")
    return "\n".join(lines)


def _build_used_clips_summary(used_clips: dict) -> str:
    """Format the used_clips dict into a readable summary for the prompt."""
    if not used_clips:
        return "None yet."
    used = [f"{name} ({count}x)" for name, count in used_clips.items() if count > 0]
    return ", ".join(used) if used else "None yet."


def select_moment_with_advisor(
    segment: Segment,
    candidates: List[MomentCandidate],
    beat_grid: List[float],
    blueprint: StyleBlueprint,
    clip_index: ClipIndex,
    previous_selection: Optional[MomentCandidate] = None,
    cde: str = "Moderate",
    used_clips: Optional[dict] = None,
    recent_picks: Optional[List[dict]] = None
) -> Optional[ContextualMomentSelection]:
    """
    Call DeepSeek Advisor to return 5 ranked clip+energy alternatives for this segment.

    Candidates are normalized (max 2 per clip) before the model sees them.
    The Advisor receives clip usage history and last 5 picks for continuity reasoning.
    Returns ContextualMomentSelection.alternatives - editor walks and commits first valid.
    """
    if not candidates:
        return None

    segment_beats = [b for b in beat_grid if segment.start <= b < segment.end]
    beat_density = len(segment_beats) / segment.duration if segment.duration > 0 else 0

    # Normalize candidates: max 2 per unique clip
    normalized = _normalize_candidates(candidates, segment.energy.value)
    clip_meta_by_name = {clip.filename: clip for clip in clip_index.clips}
    normalized.sort(
        key=lambda c: (c.semantic_score * 0.7) + (c.musical_alignment * 0.3),
        reverse=True
    )
    normalized = normalized[:20]  # Hard cap for prompt token budget

    candidates_json = []
    for c in normalized:
        clip_meta = clip_meta_by_name.get(c.clip_filename)
        candidates_json.append({
            "clip_filename": c.clip_filename,
            "energy_level": c.moment_energy_level,
            "content": (c.reason or "")[:80],
            "content_description": (clip_meta.content_description[:120] if clip_meta and clip_meta.content_description else ""),
            "emotional_tone": clip_meta.emotional_tone if clip_meta else [],
            "primary_subject": clip_meta.primary_subject if clip_meta else [],
            "semantic_score": round(c.semantic_score, 2),
            "musical_alignment": round(c.musical_alignment, 2),
            "moment_role": c.moment_role,
        })

    narrative_history = _build_narrative_history(recent_picks or [])
    used_summary = _build_used_clips_summary(used_clips or {})

    prompt = CONTEXTUAL_MOMENT_PROMPT.format(
        segment_id=segment.id,
        segment_start=segment.start,
        segment_end=segment.end,
        segment_duration=segment.duration,
        segment_energy=segment.energy.value,
        segment_vibe=segment.vibe or "general",
        arc_stage=segment.arc_stage,
        expected_hold=getattr(segment, 'expected_hold', 'Normal'),
        cut_origin=getattr(segment, 'cut_origin', 'visual'),
        shot_function=getattr(segment, 'shot_function', 'Action'),
        segment_beat_count=len(segment_beats),
        beat_density=round(beat_density, 2),
        cde=cde,
        narrative_history=narrative_history,
        used_clips_summary=used_summary,
        moment_candidates=json.dumps(candidates_json, indent=2)
    )

    for attempt in range(3):
        try:
            data = call_deepseek_v3(
                prompt=prompt,
                system_prompt="You are a senior human film editor."
            )

            raw_alts = data.get("alternatives", [])
            valid_transitions = {"continue", "escalate", "contrast", "release"}
            valid_energies = {"High", "Medium", "Low"}

            alternatives = []
            seen_clips = set()
            for alt in raw_alts:
                clip = alt.get("clip_filename", "").strip()
                energy = alt.get("energy_level", "Medium").strip()
                transition = alt.get("transition_type", "continue").strip().lower()

                if not clip or clip in seen_clips:
                    continue
                if energy not in valid_energies:
                    energy = "Medium"
                if transition not in valid_transitions:
                    transition = "continue"

                seen_clips.add(clip)
                alternatives.append(AdvisorAlternative(
                    clip_filename=clip,
                    energy_level=energy,
                    transition_type=transition,
                    reason=alt.get("reason", ""),
                    confidence=float(alt.get("confidence", 0.7))
                ))

            return ContextualMomentSelection(
                segment_id=segment.id,
                alternatives=alternatives,
                continuity_intent=data.get("continuity_intent", "")
            )

        except Exception as e:
            print(f"  [ERROR] Advisor Moment Selection attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                raise RuntimeError(f"Moment selection failed after 3 retries: {e}")
            time.sleep(1.0)


def _find_phrase_boundaries(beat_grid: List[float]) -> List[float]:
    """
    Simple phrase boundary detection: look for gaps > 1.5x average beat interval.
    """
    if len(beat_grid) < 4:
        return []
    
    intervals = [beat_grid[i+1] - beat_grid[i] for i in range(len(beat_grid)-1)]
    avg_interval = sum(intervals) / len(intervals)
    
    boundaries = []
    for i, interval in enumerate(intervals):
        if interval > avg_interval * 1.5:
            boundaries.append(beat_grid[i+1])
    
    return boundaries


def plan_segment_moments(
    segment: Segment,
    selection: ContextualMomentSelection,
    clip_index: ClipIndex,
    beat_grid: List[float]
) -> SegmentMomentPlan:
    """
    Create a complete plan for filling a segment.
    
    If the selected moment can't fill the entire segment duration,
    this function chains additional moments (from same or different clips)
    to complete the duration without gaps.
    
    Args:
        segment: The reference segment
        selection: The Advisor's selected moment
        clip_index: All available clips
        beat_grid: Musical timing data
    
    Returns:
        SegmentMomentPlan with ordered moment sequence
    """
    moments = [selection.selection]
    total_duration = selection.selection.duration
    used_windows = [(selection.selection.start, selection.selection.end)]  # Track ALL used windows
    same_clip_count = 1  # How many times we've used the primary clip
    
    # If selected moment fills segment completely, we're done
    if total_duration >= segment.duration - 0.05:
        return SegmentMomentPlan(
            segment_id=segment.id,
            moments=moments,
            total_duration=total_duration,
            is_single_moment=True,
            chaining_reason=None
        )
    
    # Need to chain additional moments
    remaining = segment.duration - total_duration
    
    # Find compatible follow-up moments
    selected_clip = next(
        (c for c in clip_index.clips if c.filename == selection.selection.clip_filename),
        None
    )
    
    chaining_reason = f"Selected moment ({total_duration:.2f}s) insufficient for segment ({segment.duration:.2f}s)"
    
    while remaining > 0.05:
        # After using the same clip twice, force a switch to keep variety
        force_different_clip = (same_clip_count >= 2)
        
        next_moment = _find_chain_moment(
            selected_clip,
            clip_index,
            moments[-1],
            remaining,
            selection.selection.moment_energy_level,
            used_windows=used_windows,
            force_different_clip=force_different_clip
        )
        
        if not next_moment:
            break
        
        moments.append(next_moment)
        used_windows.append((next_moment.start, next_moment.end))
        total_duration += next_moment.duration
        remaining = segment.duration - total_duration
        
        if next_moment.clip_filename == selection.selection.clip_filename:
            same_clip_count += 1
    
    return SegmentMomentPlan(
        segment_id=segment.id,
        moments=moments,
        total_duration=total_duration,
        is_single_moment=(len(moments) == 1),
        chaining_reason=chaining_reason if len(moments) > 1 else None
    )


def _find_chain_moment(
    primary_clip: Optional[ClipMetadata],
    clip_index: ClipIndex,
    previous_moment: MomentCandidate,
    remaining_duration: float,
    target_energy: str,
    used_windows: Optional[List[Tuple[float, float]]] = None,
    force_different_clip: bool = False
) -> Optional[MomentCandidate]:
    """
    Find a moment that can follow the previous one to fill remaining time.

    Priority:
    1. Different moment from same clip (if not force_different_clip and windows not exhausted)
    2. Moment from a different clip (for variety)
    """
    if used_windows is None:
        used_windows = []

    def already_used(start: float, end: float) -> bool:
        """Check if this window overlaps any already-used region."""
        for us, ue in used_windows:
            if start < ue and end > us:  # overlap
                return True
        return False

    candidates = []

    # Try same clip first (unless caller says to force a different one)
    if not force_different_clip and primary_clip and primary_clip.best_moments:
        for energy_level, moment in primary_clip.best_moments.items():
            if already_used(moment.start, moment.end):
                continue
            duration = moment.end - moment.start
            if duration >= remaining_duration - 0.05 or moment.stable_moment:
                candidates.append(MomentCandidate(
                    clip_filename=primary_clip.filename,
                    moment_energy_level=energy_level,
                    start=moment.start,
                    end=moment.end,
                    duration=duration,
                    moment_role=moment.moment_role,
                    stable_moment=moment.stable_moment,
                    reason=moment.reason or ""
                ))

    # Search other clips when same-clip options are exhausted or forcing variety
    if not candidates:
        for clip in clip_index.clips:
            if clip.filename == previous_moment.clip_filename:
                continue
            if not clip.best_moments:
                continue
            for energy_level, moment in clip.best_moments.items():
                if already_used(moment.start, moment.end):
                    continue
                duration = moment.end - moment.start
                if duration >= remaining_duration - 0.1:
                    candidates.append(MomentCandidate(
                        clip_filename=clip.filename,
                        moment_energy_level=energy_level,
                        start=moment.start,
                        end=moment.end,
                        duration=duration,
                        moment_role=moment.moment_role,
                        stable_moment=moment.stable_moment,
                        reason=moment.reason or ""
                    ))

    if not candidates:
        return None

    # Sort by: stable first, then duration closest to remaining
    candidates.sort(key=lambda c: (
        not c.stable_moment,
        abs(c.duration - remaining_duration)
    ))

    return candidates[0]


