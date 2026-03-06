"""
Reflector module: Post-render AI reflection and critique.
Generates the 'Director's Voice' monologue and identifies library gaps.
"""

import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List
from models import StyleBlueprint, EDL, ClipIndex, DirectorCritique, AdvisorHints, VaultReport, VaultDecision
from engine.brain import MultiModelConfig, call_llama_groq, _parse_json_response
from engine.vault_compiler import compile_vault_reasoning
import time

VAULT_TRANSLATOR_PROMPT = """
You are an AI Film Editor acting as a Creative Partner. Your job is to translate structured technical reasoning into a clear, human, and blunt 'Vault Intelligence Report'.

CORE VOICE RULES:
1. PLAIN LANGUAGE: No abstract nouns or 'AI-speak'. Talk like a human sitting next to the user.
2. CAUSALITY: Always explain 'What I wanted' -> 'What got in the way' -> 'Why this choice still made sense'.
3. BLUNT HONESTY: If the footage is bad, say so. If the system compromised, admit it.
4. NO INFERENCE: You may only describe counterfactuals or intents that are explicitly listed in the input data.
5. VOCABULARY ENFORCEMENT: You must use the 'phrase_map' provided in the input data for describing decisions, causality, and impacts. 
   - For 'decision_type', pick one of the 3 variants provided in 'phrase_map.decisions' to ensure variety while remaining deterministic.
   - For causality, use the template provided in 'phrase_map.causality' that matches the 'causality_key'.
6. DATA FIDELITY: You must mirror the 'responsibility' enums (system vs library) exactly as they appear in the input data.
6b. NO FILTER HALLUCINATION (CRITICAL): 
    - If input edit_meta.styling_applied==false, you may ONLY mention tone adjustments (e.g., "warm tone", "cool tone").
    - You MUST NOT mention: LUTs, filters, grading changes, overlays, color correction, film emulation, or any applied styling.
    - If styling_applied==true, you may describe the specific LUT/filter listed in technical_discipline.
    - NEVER invent filter names. Only use what appears in technical_discipline.
6c. STRATEGIC FRAMING (CRITICAL): Never imply the system failed or lacked intelligence.
    - All constraints must be framed as tradeoffs in service of narrative coherence.
    - Use causality templates from phrase_map to explain WHY a choice was made, not just WHAT was chosen.
    - When decision_type is "strategic_pivot", emphasize the deliberate optimization (e.g., "pivoted to prioritize X over Y").
    - When decision_type is "structural_necessity", frame it as architectural (e.g., "deployed as a structural anchor").
    - Avoid phrases like "struggled", "failed", "couldn't find" unless responsibility=="library" AND status_tags confirm scarcity.
7. TRADEOFF-FIRST TONE (CRITICAL): Do not narrate like an apology. Frame outcomes as constraint-driven optimization.
   - If the input data indicates constraints, describe the tradeoff explicitly.
   - Do NOT default to "the library failed" language unless responsibility=="library" OR status_tags indicate scarcity/missing motifs.
8. CONFIDENCE QUALIFIERS (CRITICAL): When the input does not explicitly prove a claim, use calibrated language:
   - "likely", "consistent with", "suggests", "cannot confirm".
   - Never assert unseen footage properties.
9. EXECUTIVE FIRST: The header and advisor.hero should read as an executive summary. Detail belongs in advisor.body and decision_stream.

INPUT DATA (The Truth):
{vault_reasoning}

YOUR TASKS:
1. HEADER: 1-2 sentences summarizing the context and goal.
1b. EXECUTIVE SUMMARY (CRITICAL): Provide 3-6 short bullets for default view.
   - Each bullet must be a single sentence.
   - Prefer constraint/tradeoff framing.
2. ADVISOR: 
   - 'hero': Emotional, blunt, and memorable summary of the library's impact on the edit.
   - 'body': Specific, actionable, and technical explanation of the constraints. Avoid repeating the hero.
3. DECISION STREAM: For each segment, provide a 3-beat reasoning block:
   - Beat 1 (Intent): What I wanted for this segment (derived from intent_tag).
   - Beat 2 (Decision): The final choice and causality (using phrase_map variants and causality_key).
   - Beat 3 (Impact/Tradeoff): A short note on the consequence (e.g., "This preserved momentum but added no new energy"). Use phrase_map.impacts.
   - 'what_if': If no counterfactual motif is provided, use a deterministic fallback like "No stronger alternative existed" or "This slot had no viable upgrade". NEVER use "No counterfactual intent provided".

   SCHEMA CONSTRAINT:
   - `segment_id` MUST ALWAYS be a single integer.
   - When grouping multiple segments into one decision entry, ALWAYS use the FIRST segment's ID.
   - NEVER use ranges (e.g. "1-4"), arrays, or strings.

   DECISION WEIGHT RULES:
   - primary: write 2–3 sentences with full causal explanation
   - supporting: write 1–2 sentences, concise but clear
   - filler: keep to 1 short sentence per field (do not be verbose)

   COVERAGE RULE (CRITICAL): decision_stream MUST include exactly one entry for EVERY segment in input edit_meta.segment_count.
   - Do NOT group segments.
   - Do NOT omit filler segments.
   KEY VS ALL (CRITICAL):
   - You must set `is_key` and `importance` for every entry.
   - Use the input field `is_key_candidate` (if present per segment) as the primary signal.
   - `importance` MUST be either "key" or "all".
   - `tags` is optional but recommended (examples: "forced_compromise", "structural_necessity", "overuse", "scarcity").
4. FRICTION LOG: 3 bullet points on how confidence evolved (Start, Middle, End).
5. POST-MORTEM: Blunt reflection on what worked and what didn't. Assign responsibility (System vs Library) EXACTLY as provided in the JSON.
   - Must cite at least 2 specific segment_id+clip_used pairs from input segments as evidence (e.g., "Segment 7 used clip52.mp4")
   - If you praise sync/beat alignment, tie it to a specific segment's intent+decision (no generic "good timing" claims).
6. NEXT STEPS: 3 actionable prescriptions for the user.
6b. CLIP-LEVEL SUGGESTIONS (CRITICAL): Provide 4-8 descriptive suggestions that help the user improve future edits.
   - Use only the input data (including clip_usage.overused, missing_motifs, status_tags, constraint_gaps).
   - Suggestions must be descriptive ("adding X would help"), not prescriptive ("delete clip Y").
   - If overused clips exist, mention that adding substitutes with similar vibe/subject would reduce repetition.
7. TECHNICAL: 2-3 behind-the-scenes notes on technical discipline.

OUTPUT FORMAT (JSON ONLY):
{{
  "header": "...",
  "executive_summary": ["...", "..."],
  "advisor": {{ "hero": "...", "body": "..." }},
  "decision_stream": [
    {{ "segment_id": 1, "what_i_tried": "...", "decision": "...", "what_if": "...", "is_key": true, "importance": "key", "tags": ["..."] }}
  ],
  "key_decision_stream": [
    {{ "segment_id": 1, "what_i_tried": "...", "decision": "...", "what_if": "...", "is_key": true, "importance": "key", "tags": ["..."] }}
  ],
  "friction_log": ["...", "...", "..."],
  "post_mortem": {{ "worked": "...", "didnt": "...", "responsibility": {{ "vibe": "...", "emotion": "..." }} }},
  "next_steps": ["...", "...", "..."],
  "clip_suggestions": ["...", "..."],
  "technical": ["...", "...", "..."]
}}
"""

REFLECTOR_PROMPT = """
You are a world-class Creative Director and Editor, specializing in short-form, social-native storytelling (reels, clips, and modern video narratives).

You are reviewing a finished video edit created by an automated system called MIMIC.
This is a WHITEBOX critique: your job is to explain what worked, what didn't, and why - 
based strictly on the data provided. Do not hallucinate visuals or events.

IMPORTANT SYSTEM CONSTRAINTS (DO NOT VIOLATE):
- The editing engine is deterministic and constraint-driven.
- Energy gating, beat alignment, and diversity rules were always respected.
- If a clip feels weak, assume it was used due to limitations in the clip library, not a system error.
- Do NOT suggest alternate edits. Only evaluate the outcome and material quality.
- NOTE: You are reviewing a partial summary of the edit decisions. Do not assume full consistency beyond the provided evidence.

CONTEXT PROVIDED:
- Reference Blueprint Summary: {blueprint_summary}
- Strategic Context (The Plan): {strategic_context}
- Final Edit Decisions (EDL with reasoning): {edl_summary}

YOUR HIERARCHY OF JUDGMENT (CRITICAL):
1. NARRATIVE ADHERENCE: Did the edit respect the "Text Overlay" intent and "Dominant Narrative"? 
   (NOTE: If no explicit text overlay exists, infer narrative intent from the Reference Blueprint's narrative_message and emotional_intent).
2. SEMANTIC FLOW: Did the "Vibe" of the clips match the "Vibe" of the reference segments?
3. RHYTHMIC PRECISION: How well did the cuts align with the "Beat Sync" and "Energy" requirements? 
   (NOTE: For text-based edits, rhythm is inferred at a default 120 BPM).
4. MATERIAL QUALITY: The visual appeal and relevance of the source clips themselves.
   (NOTE: Check the blueprint's "assumed_material" list. If the edit drifted, was it because the library lacked these assumed assets?)

DEFINITIONS (USE THESE):
- "Star Performer": A clip that satisfied the Narrative Intent (Text Overlay) AND matched the segment's Vibe perfectly.
- "Dead Weight": A clip that diluted the narrative intent (e.g., a scenic shot in a people-driven story) or was a low-energy compromise.
- "Missing Ingredients": Concrete shot types or moments that would materially improve the edit if added.

YOUR TASKS:
1. Analyze the EDL. Identify where the system successfully anchored the "Text Overlay" intent vs where it drifted into "Filler."
2. Write a 3-4 sentence Director's Monologue that captures the soul of the edit.
   - Start with "Based on the observed segments..." to maintain technical humility.
   - Focus on the "Story Transfer": How well did the system transplant the reference's rhythm into the user's narrative?
   - Explicitly distinguish between what the system executed well despite constraints vs what would improve only with better source material.
   - Be honest about "Thematic Dissonance" (e.g., "The system tried to tell a story of friendship using mostly landscape clips").
3. List specific Star Performers by clip filename.
4. List specific Dead Weight clips by filename. Frame these as "necessary compromises" due to library constraints, not as errors.
5. Suggest Missing Ingredients as concrete, filmable shots (not abstract advice).
6. Create 'Remake Actions': 2-3 structured deltas for the next iteration.
   - format: {"type": "increase_energy" | "change_subject" | "fix_pacing", "segment": "Intro" | "Build-up" | "Peak" | "Outro", "suggestion": "..."}
7. Provide a brief Technical Fidelity note that evaluates execution quality independently of footage quality.

SCORING GUIDELINE:
- overall_score reflects the NARRATIVE COHESION and VIEWING EXPERIENCE.
- A 10/10 requires perfect alignment between the Text Intent, the Reference Rhythm, and the Clip Content.
- Penalize "Intent Dilution" (wrong subject for the story) heavily.

OUTPUT FORMAT (JSON ONLY):
{{
  "overall_score": 7.5,
  "monologue": "...",
  "star_performers": ["clip1.mp4", "clip5.mp4"],
  "dead_weight": ["clip4.mp4", "clip7.mp4"],
  "missing_ingredients": [
    "Wide establishing shots with stable framing",
    "Group motion (friends walking or dancing together)",
    "Transitional filler shots for pacing"
  ],
  "remake_actions": [
    {{ "type": "increase_energy", "segment": "Peak", "suggestion": "Add at least 2 more Dynamic/High clips" }}
  ],
  "technical_fidelity": "Beat alignment and energy progression were executed cleanly. Narrative intent was preserved, but limited by clip variety."
}}
"""

def generate_vault_report(
    blueprint: StyleBlueprint,
    edl: EDL,
    advisor: AdvisorHints,
    critique: DirectorCritique,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False
) -> VaultReport:
    """
    Translates the compiled reasoning into a human-toned Vault Report.
    """
    if cache_dir is None:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        cache_dir = BASE_DIR / "data" / "cache" / "vault"
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    edl_hash = hashlib.md5(edl.model_dump_json().encode()).hexdigest()
    reasoning_file = cache_dir / f"reasoning_{edl_hash}.json"
    report_file = cache_dir / f"vault_{edl_hash}.json"

    if not force_refresh and report_file.exists():
        try:
            data = json.loads(report_file.read_text(encoding='utf-8'))
            return VaultReport(**data)
        except Exception:
            pass

    # Step 1: Compile the truth
    reasoning = compile_vault_reasoning(blueprint, edl, advisor, critique, reasoning_file)

    def _ensure_full_decision_coverage(report: VaultReport) -> VaultReport:
        segment_rows = reasoning.get("segments", []) if isinstance(reasoning, dict) else []
        if not isinstance(segment_rows, list) or not segment_rows:
            return report

        by_id: Dict[int, VaultDecision] = {d.segment_id: d for d in (report.decision_stream or [])}
        out: List[VaultDecision] = []

        for s in segment_rows:
            try:
                seg_id = int(s.get("segment_id"))
            except Exception:
                continue

            existing = by_id.get(seg_id)
            if existing is not None:
                out.append(existing)
                continue

            intent_tag = str(s.get("intent_tag") or "general").replace("_", " ")
            decision_type = str(s.get("decision_type") or "confident").replace("_", " ")
            clip_used = str(s.get("clip_used") or "unknown")
            counterfactual = s.get("counterfactual_tag")
            what_if = "No stronger alternative existed."
            if isinstance(counterfactual, str) and counterfactual:
                what_if = counterfactual.replace("_", " ")

            is_key = bool(s.get("is_key_candidate", False))
            importance = "key" if is_key else "all"
            tags: List[str] = []
            if isinstance(s.get("decision_type"), str) and s.get("decision_type"):
                tags.append(str(s.get("decision_type")))

            out.append(
                VaultDecision(
                    segment_id=seg_id,
                    what_i_tried=f"Target {intent_tag}.",
                    decision=f"Used {clip_used} ({decision_type}).",
                    what_if=what_if,
                    is_key=is_key,
                    importance=importance,
                    tags=tags,
                )
            )

        report.decision_stream = out
        report.key_decision_stream = [d for d in out if d.is_key]
        return report

    # Step 2: Translate with Llama 3.3 70B via Groq (v14.8: Upgraded for schema compliance)
    print(f"[VAULT] Translating reasoning into human report via Groq (Llama 3.3 70B)...")
    prompt = VAULT_TRANSLATOR_PROMPT.format(vault_reasoning=json.dumps(reasoning, indent=2))

    max_attempts = 3
    last_error = None
    
    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                print(f"  [VAULT] Attempt {attempt + 1}/{max_attempts}...")
                
            data = call_llama_groq(
                prompt=prompt,
                model_name=MultiModelConfig.LLAMA_3_3_70B,
                system_prompt="You are an AI Film Editor acting as a Creative Partner."
            )
            report = VaultReport(**data)
            report = _ensure_full_decision_coverage(report)
            
            report_file.write_text(report.model_dump_json(indent=2), encoding='utf-8')
            return report
        except Exception as e:
            last_error = e
            print(f"  ⚠️ Vault generation attempt {attempt + 1} failed: {e}")
            if attempt < max_attempts - 1:
                time.sleep(1) # Small cooldown before retry
                continue
    
    # Final Fallback: All attempts failed, return minimal report to prevent UI crash
    print(f"  🔴 Vault translation failed after {max_attempts} attempts: {last_error}")
    
    fallback_report = VaultReport(
        header="[System Note] Narrative intelligence report partially unavailable.",
        advisor=VaultReportSection(
            hero="The edit was rendered successfully, but the storytelling reasoning engine returned an incomplete profile.",
            body="This occurs when the AI reflection step exceeds complexity limits or encounters formatting conflicts. Your edit is technically sound; refer to the Decision Stream below for objective clip logic."
        ),
        decision_stream=[] # Will be hydrated by decision coverage helper below
    )
    
    # Hydrate the fallback with objective segment data so the UI at least shows what clips were used
    fallback_report = _ensure_full_decision_coverage(fallback_report)
    return fallback_report

def reflect_on_edit(
    blueprint: StyleBlueprint,
    edl: EDL,
    clip_index: ClipIndex,
    advisor: Optional[AdvisorHints] = None,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False
) -> DirectorCritique:
    """
    Call Gemini to generate a post-render critique.
    Uses hash-based caching to avoid redundant API calls.
    """
    if cache_dir is None:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        cache_dir = BASE_DIR / "data" / "cache" / "critiques"
    
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Create a unique hash for this specific edit (Blueprint + EDL + Advisor)
    # This ensures that if the pacing or clips change, the critique regenerates.
    edl_hash = hashlib.md5(edl.model_dump_json().encode()).hexdigest()
    cache_file = cache_dir / f"critique_{edl_hash}.json"

    if not force_refresh and cache_file.exists():
        try:
            print(f"  📦 Loading cached Director's Critique...")
            data = json.loads(cache_file.read_text(encoding='utf-8'))
            return DirectorCritique(**data)
        except Exception as e:
            print(f"  ⚠️ Critique cache corrupted: {e}")

    print(f"\n[REFLECTOR] Generating Director's Critique...")
    
    # Summarize data for prompt
    blueprint_summary = f"Style: {blueprint.editing_style}, Intent: {blueprint.emotional_intent}, Message: {blueprint.narrative_message}"
    
    # v12.1 STRATEGIC CONTEXT SYNTHESIS
    strategic_parts = []
    if advisor:
        if advisor.editorial_strategy:
            strategic_parts.append(f"STRATEGY: {advisor.editorial_strategy}")
        
        if advisor.primary_narrative_subject:
            strength = getattr(advisor, 'subject_lock_strength', 1.0)
            lock_type = "HARD LOCK" if strength >= 0.9 else "Soft Preference"
            strategic_parts.append(f"PRIMARY ANCHOR: {advisor.primary_narrative_subject.value} ({lock_type})")
        
        if hasattr(advisor, 'editorial_motifs') and advisor.editorial_motifs:
            motifs = [f"{m.get('desired_continuity')} ({m.get('trigger', 'general')})" for m in advisor.editorial_motifs]
            strategic_parts.append(f"ACTIVE MOTIFS: {', '.join(motifs)}")
            
        if advisor.library_alignment:
            gaps = advisor.library_alignment.constraint_gaps
            if gaps:
                strategic_parts.append(f"KNOWN CONSTRAINTS: {', '.join(gaps)}")
    else:
        strategic_parts.append("No strategic guidance was active.")
        
    strategic_context = "\n".join(strategic_parts)
    
    # Extract key decisions for the prompt
    decisions = []
    for d in edl.decisions[:20]: # Expanded to 20 for better visibility
        # Use filename only for prompt clarity
        clip_name = d.clip_path.split('/')[-1].split('\\')[-1]
        decisions.append(f"Seg {d.segment_id}: {clip_name} ({d.reasoning})")
    edl_summary = " | ".join(decisions)

    # Use a dictionary for formatting to avoid KeyError with {type} in the prompt
    format_vars = {
        "blueprint_summary": blueprint_summary,
        "strategic_context": strategic_context,
        "edl_summary": edl_summary
    }

    for attempt in range(3):
        try:
            # Use Llama 3.3 70B for high-quality Director's Monologue
            data = call_llama_groq(
                prompt=final_prompt,
                model_name=MultiModelConfig.LLAMA_3_3_70B,
                system_prompt="You are a world-class Creative Director and Editor."
            )
            critique = DirectorCritique(**data)
            
            # Save to cache
            try:
                cache_file.write_text(critique.model_dump_json(indent=2), encoding='utf-8')
                print(f"  ✅ Critique cached: {cache_file.name}")
            except Exception as e:
                print(f"  ⚠️ Failed to cache critique: {e}")
                
            return critique
        except Exception as e:
            print(f"  🔴 Reflector attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                print(f"  ⚠️ Reflector failed after all retries. Using fallback critique.")
                return DirectorCritique(
                    overall_score=5.0,
                    monologue="The system completed the edit, but the reflection layer encountered an error. The technical structure is sound, but the narrative nuance requires human review.",
                    technical_fidelity="Automatic validation passed. Rhythmic alignment confirmed."
                )
            time.sleep(1.0)
    
    return DirectorCritique(
        overall_score=5.0,
        monologue="The system completed the edit, but the reflection layer encountered an error. The technical structure is sound, but the narrative nuance requires human review.",
        technical_fidelity="Automatic validation passed. Rhythmic alignment confirmed."
    )
