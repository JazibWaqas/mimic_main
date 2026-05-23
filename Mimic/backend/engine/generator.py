"""
Blueprint Generator: Text-to-Edit-DNA system (v14.7 Prompt Mode).

Allows users to describe an edit in natural language and generates a full StyleBlueprint.
This bypasses the need for a reference video while maintaining the same deterministic execution.

v14.7 PROMPT MODE ENHANCEMENTS:
- Nostalgia-first design: Fewer cuts, longer holds, emotional pacing
- Explicit CDE (Cut Density Expectation) guidance per segment
- Explicit cut_origin for Editor compatibility
- Optional BPM awareness for music-synchronized phrasing
- Fallback blueprint for graceful degradation
"""

import json
import hashlib
import time
from typing import Optional
from pathlib import Path
from models import StyleBlueprint, EnergyLevel, MotionType, Segment
from engine.brain import call_deepseek_reasoner, _parse_json_response, REFERENCE_CACHE_VERSION
from engine.text_safety import sanitize_blueprint_text_fields
from engine.music_profile import format_music_profile_for_prompt

# ============================================================================
# PROMPT MODE GENERATOR PROMPT (v14.8 Intent-First Design)
# ============================================================================
# This prompt is designed for short-form social edits.
# It produces StyleBlueprints that follow the user's approved intent while
# preserving intentional rhythm and avoiding jittery hyper-fragmentation.
# ============================================================================

GENERATOR_CACHE_VERSION = "14.8-intent-first"

GENERATOR_PROMPT = """
You are a world-class Creative Director and Edit Producer specializing in short-form social video edits.

Your task is to generate a 'Style Blueprint' (Editing DNA) based on a user's text description.
This blueprint will be used by an automated engine to assemble raw clips into a cohesive narrative.

USER DESCRIPTION:
{user_prompt}

TARGET DURATION: {target_duration} seconds
{music_context}

---

## INTENT-FIRST EDITING PHILOSOPHY (CRITICAL)

The user's approved intent is the highest creative authority.
Do not force every edit into the same emotional or nostalgic shape.

QUALITY RULES:
- Avoid jittery, random, or hyper-fragmented edits.
- Use fewer, stronger segments rather than many tiny blueprint segments.
- Let meaningful moments breathe when the user asks for raw, calm, emotional, documentary, luxury, or nonchalant energy.
- Use denser cuts only when the user explicitly asks for high energy, speed, action, hype, comedy, or beat-driven impact.
- Peak near the strongest music or narrative moment, not an arbitrary middle point.
- Land the ending cleanly; never end abruptly unless the user asks for an abrupt punchline or hard stop.

Nostalgia is one possible intent, not the default. Intentional rhythm is always required.

---

## AUTHORSHIP BOUNDARY

You define EDITORIAL INTENT AND STRUCTURE, not execution guarantees.
- Segment boundaries represent intended emotional pacing.
- The engine may adjust cuts to match the beat grid and clip availability.
- Specify PREFERENCES for shot types, not mandates.
- Focus on the "soul" of the segment, not micro-details.

---

## MUSIC-AWARE PHRASING
{music_guidance}

---

## ARC PLAN REQUIREMENTS

Design a clear 4-stage editorial arc:

| Stage    | Duration  | Purpose                              | Energy   | CDE      |
|----------|-----------|--------------------------------------|----------|----------|
| Intro    | 15-25%    | Set the scene, establish tone        | Low      | Sparse   |
| Build-up | 25-35%    | Escalate interest                    | Medium   | Moderate |
| Peak     | 25-35%    | Emotional climax, payoff             | High/Med | Moderate |
| Outro    | 15-25%    | Resolution or clean final beat       | Low      | Sparse   |

---

## SEGMENT SPECIFICATION

For EACH segment, you MUST specify:

1. **id**: Sequential integer (1, 2, 3, ...)
2. **start / end / duration**: Continuous, no gaps. Sum = target_duration exactly.
3. **energy**: Low | Medium | High
4. **motion**: Static | Dynamic
5. **vibe**: 1-3 emotional keywords (e.g., "warmth, nostalgia, joy")
6. **reasoning**: 1-2 sentences explaining WHY this segment exists
7. **arc_stage**: Intro | Build-up | Peak | Outro
8. **shot_scale**: Wide | Medium | Close (advisory only)
9. **shot_function**: Establish | Action | Reaction | Detail | Transition | Release
10. **expected_hold**: Short | Normal | Long
11. **cut_origin**: "visual" (narrative-driven) | "beat" (music-driven)
12. **cde**: "Sparse" | "Moderate" | "Dense" (Cut Density Expectation)
13. **emotional_guidance**: What should the viewer FEEL? (e.g., "peaceful reflection")

14. **style_config**: A recommended visual style for the entire edit.
   - **text**: object with font (Inter/Outfit), weight (400/600/700), color (hex), shadow (true/false), position (top/center/bottom), animation (fade/none)
   - **color**: object with preset (neutral/warm/cool/high_contrast/vintage)
   - **texture**: object with grain (true/false)

---

## CDE (CUT DENSITY EXPECTATION) GUIDELINES

| CDE      | Meaning                                           | Use Case                    |
|----------|---------------------------------------------------|-----------------------------|
| Sparse   | 1 clip per segment preferred. Let it breathe.    | Intro, Outro, Emotional     |
| Moderate | 1-2 cuts allowed if needed. Natural pacing.      | Build-up, Standard scenes   |
| Dense    | Multiple quick cuts permitted. Energy-driven.    | Action peaks, celebrations  |

FOR CALM / RAW / NOSTALGIC / DOCUMENTARY EDITS:
- Default to "Sparse" for Intro and Outro.
- Use "Moderate" for Build-up.
- Use "Moderate" (not Dense) even for Peak unless user requests intensity.

FOR HYPE / ACTION / FAST / BEAT-DRIVEN EDITS:
- Allow "Dense" at the Peak and short beat-driven moments.
- Keep Intro and Outro readable; do not make the whole edit feel like noise.

---

## CRITICAL RULES

1. Total duration must be EXACTLY {target_duration} seconds.
2. Segments must be CONTINUOUS (Segment 2 start = Segment 1 end).
3. Prefer FEWER blueprint segments with intentional holds over many tiny segments.
4. For a 20-30 second edit, aim for 4-6 blueprint segments (the execution engine may still make multiple cuts inside a segment when appropriate).
5. Use professional editorial reasoning for every decision.
6. If user description conflicts with standard pacing, prioritize the USER'S APPROVED INTENT.
7. **HARD LIMIT**: If target_duration <= 30 seconds, NEVER produce more than 6 segments.
8. **DURATION FIX**: If segment durations don't sum exactly to target_duration, adjust the FINAL segment duration to ensure the total equals target_duration exactly.
9. **STYLE LOGIC**: Set the `style_config` based on the user's intent:
   - Nostalgic/Warm/Memories -> "warm" or "vintage" preset, Inter font.
   - Clean/Modern/Professional -> "neutral" preset, Outfit font.
   - High Energy/Flashy -> "high_contrast" preset, Outfit font, weight 700.

---

## OUTPUT FORMAT (JSON ONLY)

{{
  "total_duration": {target_duration},
  "editing_style": "...",
  "emotional_intent": "...",
  "plan_summary": "...",
  "style_config": {{
    "text": {{
      "font": "Inter",
      "weight": 600,
      "color": "#FFFFFF",
      "shadow": true,
      "position": "bottom",
      "animation": "fade"
    }},
    "color": {{
      "preset": "warm"
    }},
    "texture": {{
      "grain": false
    }}
  }},
  "arc_description": "How emotion and energy evolve over time",
  "text_overlay": "1-3 short, impactful lines (or empty string if none)",
  "text_style": {{
    "font_style": "Serif/Sans-serif/Handwritten/etc.",
    "animation": "Fade/Typewriter/Static/etc.",
    "placement": "Center/Top-third/Bottom-third",
    "color_effects": "Warm/Cool/White/etc."
  }},
  "color_grading": {{
    "tone": "Warm/Cool/Neutral",
    "contrast": "Low/Medium/High",
    "specific_look": "Vintage Film/Modern Clean/etc."
  }},
  "visual_effects": ["film grain", "light leaks"],
  "narrative_message": "The story being told",
  "intent_clarity": "Clear",
  "assumed_material": ["wide landscapes", "people laughing", "etc."],
  "must_have_content": ["specific required types"],
  "should_have_content": ["preferred types"],
  "avoid_content": ["types to avoid"],
  "pacing_feel": "Breathable/Reflective/Steady",
  "visual_balance": "People-centric/Place-centric/Balanced",
  "peak_density": "Sparse/Moderate/Dense",
  "segments": [
    {{
      "id": 1,
      "start": 0.0,
      "end": 5.0,
      "duration": 5.0,
      "energy": "Low",
      "motion": "Static",
      "vibe": "warmth, nostalgia",
      "reasoning": "Open with a calm establishing shot to set the emotional tone.",
      "arc_stage": "Intro",
      "shot_scale": "Wide",
      "shot_function": "Establish",
      "expected_hold": "Long",
      "cut_origin": "visual",
      "cde": "Sparse",
      "emotional_guidance": "peaceful anticipation"
    }},
    ...
  ]
}}
"""


def create_fallback_blueprint(target_duration: float, user_prompt: str = "") -> StyleBlueprint:
    """
    Create a safe, minimal fallback blueprint if Gemini synthesis fails.
    
    This ensures the pipeline NEVER crashes during demo.
    Produces a balanced 4-segment arc optimized for nostalgia.
    
    Args:
        target_duration: Total duration in seconds
        user_prompt: Original user prompt (for logging)
    
    Returns:
        StyleBlueprint: A safe, minimal blueprint
    """
    print(f"  [FALLBACK] Creating emergency blueprint for {target_duration}s edit")
    
    # Calculate segment durations (balanced 4-stage arc)
    intro_dur = round(target_duration * 0.20, 2)
    buildup_dur = round(target_duration * 0.30, 2)
    peak_dur = round(target_duration * 0.30, 2)
    outro_dur = round(target_duration - intro_dur - buildup_dur - peak_dur, 2)
    
    # Build segment boundaries
    intro_end = intro_dur
    buildup_end = intro_end + buildup_dur
    peak_end = buildup_end + peak_dur
    outro_end = target_duration
    
    # Add contract for Advisor compatibility
    from engine.brain import REFERENCE_CACHE_VERSION
    import time
    
    fallback_data = {
        "total_duration": target_duration,
        "editing_style": "Nostalgic Fallback",
        "emotional_intent": "Warm memories",
        "plan_summary": "A balanced 4-stage arc with gentle pacing. Fallback mode due to synthesis failure.",
        "arc_description": "Intro sets scene, Build-up escalates, Peak delivers emotion, Outro resolves.",
        "text_overlay": "",
        "text_style": {
            "font_style": "Sans-serif",
            "animation": "Fade",
            "placement": "Center",
            "color_effects": "White"
        },
        "color_grading": {
            "tone": "Warm",
            "contrast": "Medium",
            "specific_look": "Natural"
        },
        "visual_effects": [],
        "narrative_message": "A moment to remember",
        "intent_clarity": "Clear",
        "assumed_material": ["people", "places", "moments"],
        "must_have_content": [],
        "should_have_content": [],
        "avoid_content": [],
        "pacing_feel": "Breathable",
        "visual_balance": "Balanced",
        "peak_density": "Moderate",
        "text_prompt": user_prompt,
        "contract": {
            "type": "blueprint",
            "version": REFERENCE_CACHE_VERSION,
            "source": "fallback",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        },
        "segments": [
            {
                "id": 1,
                "start": 0.0,
                "end": intro_end,
                "duration": intro_dur,
                "energy": "Low",
                "motion": "Static",
                "vibe": "calm, establishing",
                "reasoning": "Open with a calm establishing shot.",
                "arc_stage": "Intro",
                "shot_scale": "Wide",
                "shot_function": "Establish",
                "expected_hold": "Long",
                "cut_origin": "visual",
                "cde": "Sparse",
                "emotional_guidance": "peaceful anticipation"
            },
            {
                "id": 2,
                "start": intro_end,
                "end": buildup_end,
                "duration": buildup_dur,
                "energy": "Medium",
                "motion": "Dynamic",
                "vibe": "anticipation, warmth",
                "reasoning": "Build energy and anticipation.",
                "arc_stage": "Build-up",
                "shot_scale": "Medium",
                "shot_function": "Action",
                "expected_hold": "Normal",
                "cut_origin": "visual",
                "cde": "Moderate",
                "emotional_guidance": "growing excitement"
            },
            {
                "id": 3,
                "start": buildup_end,
                "end": peak_end,
                "duration": peak_dur,
                "energy": "Medium",
                "motion": "Dynamic",
                "vibe": "joy, memory",
                "reasoning": "Emotional peak with meaningful moments.",
                "arc_stage": "Peak",
                "shot_scale": "Close",
                "shot_function": "Reaction",
                "expected_hold": "Normal",
                "cut_origin": "visual",
                "cde": "Moderate",
                "emotional_guidance": "emotional payoff"
            },
            {
                "id": 4,
                "start": peak_end,
                "end": outro_end,
                "duration": outro_dur,
                "energy": "Low",
                "motion": "Static",
                "vibe": "reflection, peace",
                "reasoning": "Soft landing to close the narrative.",
                "arc_stage": "Outro",
                "shot_scale": "Wide",
                "shot_function": "Release",
                "expected_hold": "Long",
                "cut_origin": "visual",
                "cde": "Sparse",
                "emotional_guidance": "peaceful resolution"
            }
        ]
    }
    
    print(f"  [FALLBACK] Generated 4-segment fallback blueprint")
    return StyleBlueprint(**fallback_data)


def generate_blueprint_from_text(
    user_prompt: str,
    target_duration: float = 15.0,
    api_key: Optional[str] = None,
    bpm: Optional[float] = None,
    beat_count: Optional[int] = None,
    energy_curve: Optional[list] = None,  # Normalized per-second RMS energy [0.0–1.0]
    library_snapshot: Optional[dict] = None,  # Compact library summary for blueprint calibration
    music_profile: Optional[dict] = None
) -> StyleBlueprint:
    """
    Call Gemini to generate a full StyleBlueprint from a text prompt.
    Uses robust retry and key rotation logic.
    
    v14.7 ENHANCEMENTS:
    - Optional BPM awareness for music-synchronized phrasing
    - Fallback blueprint for graceful degradation
    - Nostalgia-first prompt design
    
    Args:
        user_prompt: Natural language description of desired edit
        target_duration: Target duration in seconds (HARD CONSTRAINT)
        api_key: Optional Gemini API key override
        bpm: Optional BPM for music-aware phrasing
        beat_count: Optional beat count for phrase calculation
    
    Returns:
        StyleBlueprint: Generated blueprint ready for Editor consumption
    """
    import time
    
    print(f"\n[GENERATOR] Synthesizing Blueprint from prompt: '{user_prompt[:50]}...'")
    if bpm:
        print(f"  [MUSIC] Music-aware mode: {bpm:.1f} BPM")
    
    # Define cache directory
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    cache_dir = BASE_DIR / "data" / "cache" / "blueprints"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique hash for this prompt + duration + bpm + music energy + library combo
    energy_fingerprint = "none"
    if energy_curve and len(energy_curve) > 0:
        peak_sec = energy_curve.index(max(energy_curve))
        avg_e = round(sum(energy_curve) / len(energy_curve), 3)
        energy_fingerprint = f"{peak_sec}_{avg_e}"
    # Include library fingerprint: same prompt + different clips = different blueprint
    lib_fingerprint = "none"
    if library_snapshot:
        lib_fingerprint = "-".join(sorted(library_snapshot.get("dominant_vibes", [])[:4]))
    cache_key = f"{GENERATOR_CACHE_VERSION}_{user_prompt}_{target_duration}_{bpm or 'none'}_{energy_fingerprint}_{lib_fingerprint}"
    prompt_hash = hashlib.md5(cache_key.encode()).hexdigest()[:12]
    cache_file = cache_dir / f"blueprint_{prompt_hash}.json"
    
    # 1. Check Cache (Deterministic execution)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"  [CACHE] Hit! Reusing synthesized blueprint: {cache_file.name}")
            return StyleBlueprint(**data)
        except Exception as e:
            print(f"  [WARN] Failed to load cached blueprint: {e}")
    
    # 2. Build music context for the prompt
    music_context = ""
    music_guidance = ""
    
    if bpm and bpm > 0:
        beat_interval = 60.0 / bpm
        beats_in_duration = int(target_duration / beat_interval)
        phrase_length = 4  # Typical phrase = 4 beats
        phrases_in_duration = beats_in_duration // phrase_length
        
        music_context = f"""
MUSIC INFORMATION:
- BPM: {bpm:.1f}
- Beat interval: {beat_interval:.3f} seconds
- Estimated beats in edit: {beats_in_duration}
- Estimated musical phrases (4-beat): {phrases_in_duration}
"""
        music_guidance = f"""
When designing segments, consider musical phrasing:
- A 4-beat phrase at {bpm:.1f} BPM = {phrase_length * beat_interval:.2f} seconds
- Align major segment transitions to phrase boundaries when possible
- Peak should align with a strong downbeat or phrase start
- Outro should start on a resolving phrase
- DO NOT force all cuts to beats - vibes matter more than math
"""
        # Enrich with energy curve data if available
        if energy_curve and len(energy_curve) >= 3:
            total_secs = len(energy_curve)
            third = total_secs // 3
            intro_avg = round(sum(energy_curve[:third]) / max(third, 1), 2)
            mid_avg = round(sum(energy_curve[third:2*third]) / max(third, 1), 2)
            outro_avg = round(sum(energy_curve[2*third:]) / max(total_secs - 2*third, 1), 2)
            peak_sec = energy_curve.index(max(energy_curve))
            music_guidance += f"""

MUSIC ENERGY ANALYSIS (from actual audio):
- Opening energy (0-{third}s): {intro_avg:.2f}/1.0 - {'quiet/delicate' if intro_avg < 0.4 else 'moderate' if intro_avg < 0.7 else 'strong'}
- Middle energy ({third}-{2*third}s): {mid_avg:.2f}/1.0 - {'quiet/delicate' if mid_avg < 0.4 else 'moderate' if mid_avg < 0.7 else 'strong'}
- Closing energy ({2*third}-{total_secs}s): {outro_avg:.2f}/1.0 - {'quiet/delicate' if outro_avg < 0.4 else 'moderate' if outro_avg < 0.7 else 'strong'}
- Loudest musical moment: {peak_sec}s into the track

USE THIS to shape segment intensities and cut density:
- Where music energy is low (<0.4): use longer holds, peaceful clips, sparse cuts
- Where music energy is moderate (0.4-0.7): standard pacing, 1-2 cuts per segment  
- Where music energy is high (>0.7): shorter cuts, more energy, can be denser
- The peak at ~{peak_sec}s should coincide with your Peak arc stage
"""
    else:
        music_context = "(No music information available - design based on narrative pacing)"
        music_guidance = """
Design segments based on narrative flow and emotional pacing.
Since no BPM is provided, focus on visual rhythm and story arc.
"""

    if music_profile:
        music_guidance += "\n" + format_music_profile_for_prompt(music_profile)
    
    # 3. Build library context (injected only when available)
    library_context = ""
    if library_snapshot:
        import json as _json
        library_context = f"""

CLIP LIBRARY SNAPSHOT (CRITICAL - design your blueprint around this):
{_json.dumps(library_snapshot, indent=2)}

IMPORTANT RULES:
- The 'dominant_vibes' above are the ACTUAL vibes present in the user's clips.
- The 'dominant_subjects' are what ACTUALLY appears in these clips.
- The 'energy_distribution' and 'motion_distribution' show how much fast/slow material exists.
- The 'strongest_clips' are compact examples of the most usable material.
- Your segment vibes and emotional_guidance MUST draw from these real vibes.
- Do NOT ask for intimacy/solo moments if only 'group/leisure' clips exist.
- Prefer blueprint assumptions that the strongest clips can realistically satisfy.
- The edit will FAIL if you design segments for content that doesn't exist.
- These clips are all handpicked and genuinely usable - trust the library.
"""

    # 4. Build final prompt
    final_prompt = GENERATOR_PROMPT
    final_prompt = final_prompt.replace("{user_prompt}", user_prompt)
    final_prompt = final_prompt.replace("{target_duration}", str(target_duration))
    final_prompt = final_prompt.replace("{music_context}", music_context)
    final_prompt = final_prompt.replace("{music_guidance}", music_guidance + library_context)
    
    
    for attempt in range(3):
        try:
            print(f"  [GENERATOR] Calling DeepSeek Reasoner for creative blueprint synthesis (attempt {attempt + 1})...")
            data = call_deepseek_reasoner(
                prompt=final_prompt,
                system_prompt="You are a world-class Creative Director and Edit Producer specializing in short-form social video edits."
            )
            
            # Ensure total_duration is a float
            data["total_duration"] = float(data.get("total_duration", target_duration))
            
            # Add the original text prompt to the blueprint
            data["text_prompt"] = user_prompt
            data = sanitize_blueprint_text_fields(data)
            
            # Ensure segments have required fields for Editor compatibility
            for seg in data.get("segments", []):
                # Default cut_origin to "visual" if not specified
                if "cut_origin" not in seg:
                    seg["cut_origin"] = "visual"
                # Default CDE to "Moderate" if not specified
                if "cde" not in seg:
                    seg["cde"] = "Moderate"
            
            # Add contract field for Advisor compatibility
            data["contract"] = {
                "type": "blueprint",
                "version": GENERATOR_CACHE_VERSION,
                "source": "text_prompt_gemini",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Save to Cache immediately
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"  [CACHE] Saved new blueprint synthesis: {cache_file.name}")
            except Exception as e:
                print(f"  [WARN] Failed to save blueprint cache: {e}")
            
            print(f"  [OK] Blueprint successfully synthesized with Gemini 3 Pro (Attempt {attempt + 1})")
            return StyleBlueprint(**data)
            
        except Exception as e:
            print(f"  [WARN] Blueprint Generation attempt {attempt + 1} failed: {e}")
            
            if attempt == 2:
                print(f"  NO Blueprint Generation failed after 3 retries. Using fallback.")
                return create_fallback_blueprint(target_duration, user_prompt)
            
            time.sleep(1.0)
    
    # Final fallback (should never reach here, but safety first)
    print(f"  NO Unexpected failure path. Using fallback blueprint.")
    return create_fallback_blueprint(target_duration, user_prompt)

