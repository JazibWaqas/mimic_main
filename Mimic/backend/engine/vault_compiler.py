import json
from pathlib import Path
from typing import Dict, Any, List
from models import StyleBlueprint, EDL, AdvisorHints, DirectorCritique

# APPROVED VOCABULARY (The only phrases the Translator is allowed to use)
# We provide 3 variants per level to avoid robotic repetition while remaining deterministic.
VAULT_PHRASE_MAP = {
    "decisions": {
        "confident": [
            "Used",
            "Locked in",
            "Selected"
        ],
        "strategic_pivot": [
            "Optimized with",
            "Pivoted to",
            "Strategically deployed"
        ],
        "structural_necessity": [
            "Used out of necessity",
            "Forced into the slot",
            "Deployed as a structural anchor"
        ],
        "forced_compromise": [
            "Settled for",
            "Accepted",
            "Compromised with"
        ]
    },
    "causality": {
        "narrative_priority": "to ensure the {subject} story remained the primary focus",
        "energy_mismatch": "to prioritize the {intent} vibe over raw energy levels",
        "missing_ideal_motif": "because the library lacked the requested {motif} motif",
        "library_gap": "because no better alternative was available in the library",
        "pacing_priority": "to preserve the rhythmic soul of the edit"
    },
    "impacts": {
        "pacing_preserved": "preserving the edit's momentum",
        "momentum_saved": "preventing a pacing collapse",
        "narrative_sacrifice": "despite the semantic mismatch",
        "strategic_choice": "maintaining narrative coherence"
    }
}

def compile_vault_reasoning(
    blueprint: StyleBlueprint,
    edl: EDL,
    advisor: AdvisorHints,
    critique: DirectorCritique,
    output_path: Path
) -> Dict[str, Any]:
    """
    Gathers all metadata into a single structured reasoning object.
    
    STRICT RULES:
    - NO PROSE. NO SENTENCES.
    - Labels and symbolic tags only.
    - Explicit causality mapping.
    """
    
    # 1. Library Health (Symbolic Only)
    status_tags = []
    clean_missing_motifs = []
    
    # Handle case where advisor is None (e.g., when Advisor fails or is disabled)
    if advisor and advisor.library_alignment:
        if advisor.library_alignment.editorial_tradeoffs:
            for tradeoff in advisor.library_alignment.editorial_tradeoffs:
                if "Medium" in tradeoff: status_tags.append("scarcity_medium_energy")
                if "Low" in tradeoff: status_tags.append("scarcity_low_energy")
                if "aggressive" in tradeoff: status_tags.append("forced_aggressive_pacing")
        
        if not status_tags:
            status_tags = ["aligned"]

        for gap in advisor.library_alignment.constraint_gaps:
            gap_lower = gap.lower()
            if "fire" in gap_lower: clean_missing_motifs.append("fire")
            elif "eyes" in gap_lower or "face" in gap_lower: clean_missing_motifs.append("human_detail")
            elif "macro" in gap_lower: clean_missing_motifs.append("macro")
            elif "establishing" in gap_lower: clean_missing_motifs.append("wide_shot")
            else: clean_missing_motifs.append(gap.split()[0].lower())
    else:
        # Advisor is None - use safe defaults
        status_tags = ["advisor_unavailable"]

    library_health = {
        "status_tags": status_tags,
        "rejected_clip_count": len(critique.dead_weight),
        "missing_motifs": clean_missing_motifs,
        "bottlenecks": [
            "scarcity_medium_energy" if "scarcity_medium_energy" in status_tags else None,
            "missing_payoff_shots" if clean_missing_motifs else None
        ]
    }
    library_health["bottlenecks"] = [b for b in library_health["bottlenecks"] if b]

    # 2. Segment Decisions
    segments = []
    for decision in edl.decisions:
        bp_seg = next((s for s in blueprint.segments if s.id == decision.segment_id), None)
        stage = bp_seg.arc_stage if bp_seg else "Main"
        stage_guidance = advisor.arc_stage_guidance.get(stage) if advisor else None

        # Determine Decision Type
        decision_type = "confident"
        causality_key = "library_gap"
        
        if "compromise" in decision.reasoning.lower() or "best available" in decision.reasoning.lower():
            decision_type = "forced_compromise"
            causality_key = "library_gap"
        elif bp_seg and bp_seg.emotional_anchor:
            decision_type = "structural_necessity"
            causality_key = "pacing_priority"

        # Determine Confidence Level (Perception Layer)
        # Derived from score deltas if available, or decision type
        confidence = "high" if decision_type == "confident" else "medium"
        if decision_type == "forced_compromise" and clean_missing_motifs:
            confidence = "low"

        # Decision Weight (Importance Signal)
        if bp_seg and bp_seg.emotional_anchor:
            decision_weight = "primary"
        elif decision_type != "confident":
            decision_weight = "supporting"
        else:
            decision_weight = "filler"

        # v15.0: Key decision candidate flag (additive signal)
        is_key_candidate = False
        if decision_type != "confident":
            is_key_candidate = True
        if decision_weight in ["primary", "supporting"] and confidence in ["low", "medium"]:
            is_key_candidate = True
        if bp_seg and bp_seg.emotional_anchor:
            is_key_candidate = True

        segments.append({
            "segment_id": decision.segment_id,
            "intent_tag": bp_seg.vibe.lower().replace(" ", "_") if bp_seg else "general",
            "decision_type": decision_type,
            "decision_weight": decision_weight,
            "confidence_level": confidence,
            "causality_key": causality_key,
            "clip_used": decision.clip_path.split('/')[-1].split('\\')[-1],
            "missing_ideal_motif": stage_guidance.primary_emotional_carrier.lower() if decision_type != "confident" and stage_guidance else None,
            "counterfactual_tag": f"replace_with_{stage_guidance.primary_emotional_carrier.lower()}" if decision_type != "confident" and stage_guidance else None,
            "is_key_candidate": is_key_candidate
        })

    # v15.0 Clip usage signals (additive; derived from EDL only)
    clip_usage_counts: Dict[str, int] = {}
    for d in edl.decisions:
        name = d.clip_path.split('/')[-1].split('\\')[-1]
        clip_usage_counts[name] = clip_usage_counts.get(name, 0) + 1

    overused = sorted(
        [{"clip": k, "count": v} for k, v in clip_usage_counts.items() if v >= 3],
        key=lambda x: x["count"],
        reverse=True
    )

    # 3. Post-Mortem (Responsibility Consistency)
    post_mortem = {
        "technical_score": critique.overall_score,
        "sync_fidelity": "high" if "rhythmic" in critique.technical_fidelity.lower() or "sync" in critique.technical_fidelity.lower() else "nominal",
        "responsibility": {
            "vibe": "library" if clean_missing_motifs or status_tags != ["aligned"] else "system",
            "emotion": "library" if clean_missing_motifs or critique.missing_ingredients else "system"
        },
        "unmet_requirements": [m.lower().replace(" ", "_") for m in critique.missing_ingredients]
    }

    # Build technical discipline list based on what was actually applied
    technical_discipline = []
    
    # TEMPORARY FIX: Styling is currently failing in production (FFmpeg font issues)
    # Set to false to prevent LUT hallucinations until styling is fixed
    styling_applied = False  # TODO: Get this from orchestrator/stylist return value
    
    if styling_applied:
        # Styling was applied - mention the specific LUT/grade
        technical_discipline.append(f"lut_{blueprint.color_grading.get('specific_look', 'neutral').lower().replace(' ', '_')}")
    else:
        # No styling applied - only mention tone adjustments (not LUTs)
        tone = blueprint.color_grading.get('tone', 'neutral').lower()
        if tone and tone != 'neutral':
            technical_discipline.append(f"tone_{tone}")
    
    # Always include pacing and sync info (these are editorial, not styling)
    technical_discipline.append(f"pacing_{blueprint.pacing_feel.lower()}")
    technical_discipline.append(f"sync_{blueprint.music_sync.lower().replace(' ', '_')}")
    
    reasoning = {
        "edit_meta": {
            "duration_sec": blueprint.total_duration,
            "reference_type": blueprint.editing_style.lower().replace(" ", "_"),
            "segment_count": len(blueprint.segments),
            "styling_applied": styling_applied
        },
        "library_health": library_health,
        "segments": segments,
        "clip_usage": {
            "counts": clip_usage_counts,
            "overused": overused
        },
        "post_mortem": post_mortem,
        "phrase_map": VAULT_PHRASE_MAP, # Explicitly injected for the translator
        "prescriptions": [m.lower().replace(" ", "_") for m in critique.missing_ingredients],
        "technical_discipline": technical_discipline
    }

    output_path.write_text(json.dumps(reasoning, indent=2), encoding='utf-8')
    return reasoning
