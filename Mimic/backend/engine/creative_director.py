"""
Creative Director: PROMPT MODE holistic cut planning.

Replaces the per-segment Advisor loop with a single call that sees:
  - User's creative intent
  - Full music map (BPM, onset timestamps, energy curve, key moments)
  - Every clip with its best moment windows

Outputs a complete ordered cut list for the entire edit.
The Editor becomes a deterministic executor: snap, validate, render.
"""

import json
import hashlib
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

from models import ClipIndex, StyleBlueprint, SegmentMomentPlan, MomentCandidate
from engine.brain import call_deepseek_v3, _parse_json_response


# ---------------------------------------------------------------------------
# Data class: a single cut decision from the Creative Director
# ---------------------------------------------------------------------------
class DirectorCut:
    """One cut in the Creative Director's ordered playlist."""
    def __init__(self, clip_filename: str, clip_start: float, clip_end: float,
                 music_position: float, purpose: str, arc_stage: str = ""):
        self.clip_filename = clip_filename
        self.clip_start = clip_start
        self.clip_end = clip_end
        self.music_position = music_position  # Where this cut starts in the music timeline
        self.purpose = purpose
        self.arc_stage = arc_stage  # Intro / Build-up / Peak / Outro

    @property
    def duration(self) -> float:
        return self.clip_end - self.clip_start

    def __repr__(self):
        return (f"DirectorCut({self.clip_filename} [{self.clip_start:.2f}-{self.clip_end:.2f}] "
                f"@ music {self.music_position:.2f}s, {self.arc_stage})")


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def _build_director_prompt(
    text_prompt: str,
    total_duration: float,
    bpm: float,
    onset_timestamps: List[float],
    energy_curve: List[float],
    clip_index: ClipIndex,
    blueprint: StyleBlueprint
) -> str:
    """Build the Creative Director prompt with all available context."""

    # --- Music map ---
    # Summarise energy curve as quarters
    n = len(energy_curve)
    if n >= 4:
        q = n // 4
        energy_quarters = [
            round(sum(energy_curve[i*q:(i+1)*q]) / q, 2)
            for i in range(4)
        ]
    else:
        energy_quarters = [0.5, 0.5, 0.5, 0.5]

    peak_sec = energy_curve.index(max(energy_curve)) if energy_curve else 0
    onsets_str = ", ".join(f"{o:.2f}" for o in onset_timestamps[:60])  # cap to avoid huge prompt

    # --- Blueprint arc summary ---
    arc_lines = []
    for seg in blueprint.segments:
        arc_lines.append(
            f"  [{seg.arc_stage}] {seg.start:.2f}s-{seg.end:.2f}s "
            f"({seg.duration:.2f}s) | energy={seg.energy.value} | "
            f"vibe={seg.vibe} | hold={getattr(seg,'expected_hold','Normal')} | "
            f"pacing={getattr(seg,'cde','Moderate')}"
        )
    arc_summary = "\n".join(arc_lines)

    # --- Clip library with ALL moment windows ---
    clip_lines = []
    for clip in clip_index.clips:
        moments_str = ""
        if clip.best_moments:
            for level, m in clip.best_moments.items():
                moments_str += (
                    f"\n      [{level}] {m.start:.2f}s-{m.end:.2f}s "
                    f"({m.end - m.start:.2f}s) role={m.moment_role} "
                    f"stable={m.stable_moment} | {(m.reason or '')[:80]}"
                )
        clip_lines.append(
            f"  {clip.filename} | {clip.duration:.1f}s | "
            f"vibes={','.join(clip.vibes or [])} | "
            f"subjects={','.join(clip.primary_subject or [])} | "
            f"energy={clip.energy.value}{moments_str}"
        )
    library_str = "\n".join(clip_lines)

    # --- Constraints ---
    constraints_str = ""
    if blueprint.must_have_content:
        constraints_str += "\nCRITICAL 'MUST HAVE' CONSTRAINTS (You MUST include these):"
        for item in blueprint.must_have_content:
            constraints_str += f"\n  - {item}"
    if blueprint.avoid_content:
        constraints_str += "\nCRITICAL 'AVOID' CONSTRAINTS (Do NOT include these):"
        for item in blueprint.avoid_content:
            constraints_str += f"\n  - {item}"

    prompt = f"""You are a senior human film editor making a video edit from scratch.
You have full creative authority. Your job is to produce a COMPLETE ORDERED CUT LIST
for this {total_duration:.1f}s edit. Every second of the music must be covered.

═══════════════════════════════════════════════════════════
USER'S CREATIVE INTENT & CONSTRAINTS
═══════════════════════════════════════════════════════════
{text_prompt}
{constraints_str}

═══════════════════════════════════════════════════════════
MUSIC MAP
═══════════════════════════════════════════════════════════
Total duration: {total_duration:.2f}s
BPM: {bpm:.1f}
Musical onsets (cut to these timestamps): [{onsets_str}]
Energy by quarter:
  0-{total_duration/4:.1f}s : {energy_quarters[0]}/1.0  ({'quiet' if energy_quarters[0]<0.4 else 'moderate' if energy_quarters[0]<0.7 else 'strong'})
  {total_duration/4:.1f}-{total_duration/2:.1f}s : {energy_quarters[1]}/1.0  ({'quiet' if energy_quarters[1]<0.4 else 'moderate' if energy_quarters[1]<0.7 else 'strong'})
  {total_duration/2:.1f}-{3*total_duration/4:.1f}s : {energy_quarters[2]}/1.0  ({'quiet' if energy_quarters[2]<0.4 else 'moderate' if energy_quarters[2]<0.7 else 'strong'})
  {3*total_duration/4:.1f}-{total_duration:.1f}s : {energy_quarters[3]}/1.0  ({'quiet' if energy_quarters[3]<0.4 else 'moderate' if energy_quarters[3]<0.7 else 'strong'})
Loudest peak: ~{peak_sec}s

═══════════════════════════════════════════════════════════
EDITORIAL ARC (blueprint guidance - not a hard contract)
═══════════════════════════════════════════════════════════
{arc_summary}

═══════════════════════════════════════════════════════════
YOUR CLIP LIBRARY (ALL handpicked, ALL usable)
Each clip shows its 3 best moment windows (High / Medium / Low energy)
Use the window timestamps exactly as clip_start / clip_end in your output.
═══════════════════════════════════════════════════════════
{library_str}

═══════════════════════════════════════════════════════════
HOW A REAL EDITOR THINKS (follow this reasoning)
═══════════════════════════════════════════════════════════
1. FEEL THE MUSIC FIRST: Where does it breathe (quiet, hold)? Where does it surge (fast cuts)?
   Where does it resolve (slow, final)? The peak is around {peak_sec}s.

2. PICK YOUR HERO MOMENTS: Which clip windows genuinely HIT emotionally?
   These are your anchors. Place them at the strongest musical moments.

3. FILL WITH VARIETY: Use as many DIFFERENT clips as possible.
   Do NOT use the same clip more than twice. Prefer once-each.

4. PACING RULES:
   - Quiet/intro sections: 3-6s holds (let moments breathe)
   - Building sections: 2-3s cuts
   - Peak/energy sections: 0.6-1.5s cuts snapped to onsets above
   - Outro/resolve: 3-5s holds

5. SNAP CUTS TO MUSIC: For fast sections, start each cut at an onset timestamp
   from the list above (within 0.3s is fine).

6. NO GAPS: Your cuts must cover 0.0s to {total_duration:.2f}s continuously.
   Each cut's timeline end = music_position + (clip_end - clip_start).
   Next cut's music_position = previous cut's timeline end.

═══════════════════════════════════════════════════════════
OUTPUT FORMAT — strict JSON, no markdown, no extra text
═══════════════════════════════════════════════════════════
{{
  "arc_summary": "2-3 sentence description of the edit you are making and why",
  "cuts": [
    {{
      "clip_filename": "clip83.mp4",
      "clip_start": 0.0,
      "clip_end": 2.5,
      "music_position": 13.0,
      "arc_stage": "Peak",
      "purpose": "Celebration burst — clapping energy matches the beat drop"
    }}
  ]
}}

VALIDATION RULES (check before outputting):
- cuts must be sorted by music_position ascending
- clip_start and clip_end must be within the clip's duration (check above)
- clip_start < clip_end for every cut
- music_position of cut N+1 = music_position of cut N + (clip_end - clip_start)
- Last cut must end at exactly {total_duration:.2f}s (adjust last clip_end if needed)
- No clip used at the exact same window twice
- Prefer using the moment windows shown above; don't invent timestamps outside them
"""
    return prompt


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
def _get_cache_file(text_prompt: str, total_duration: float, bpm: float,
                    clip_index: ClipIndex) -> Path:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    cache_dir = BASE_DIR / "data" / "cache" / "creative_director"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Cache key: prompt + duration + bpm + sorted clip filenames
    lib_sig = "-".join(sorted(c.filename for c in clip_index.clips))
    raw = f"{text_prompt}|{total_duration:.1f}|{bpm:.1f}|{lib_sig}"
    h = hashlib.md5(raw.encode()).hexdigest()[:14]
    return cache_dir / f"director_{h}.json"


# ---------------------------------------------------------------------------
# Convert Director's flat cut list → SegmentMomentPlans (what the editor expects)
# ---------------------------------------------------------------------------
def _cuts_to_segment_moment_plans(
    cuts: List[DirectorCut],
    blueprint: StyleBlueprint
) -> Dict[str, SegmentMomentPlan]:
    """
    Map the Creative Director's flat ordered cut list onto blueprint segments
    so the existing editor can execute them via the Advisor moment plan path.
    """
    plans: Dict[str, SegmentMomentPlan] = {}

    for segment in blueprint.segments:
        seg_cuts = [
            c for c in cuts
            if segment.start <= c.music_position < segment.end
        ]
        if not seg_cuts:
            # Fallback: assign any cut whose music_position is closest to segment midpoint
            mid = (segment.start + segment.end) / 2
            closest = min(cuts, key=lambda c: abs(c.music_position - mid), default=None)
            if closest:
                seg_cuts = [closest]

        if not seg_cuts:
            continue

        moments = [
            MomentCandidate(
                clip_filename=cut.clip_filename,
                moment_energy_level="High",
                start=cut.clip_start,
                end=cut.clip_end,
                duration=cut.duration,
                moment_role=cut.arc_stage or segment.arc_stage,
                stable_moment=(cut.duration >= 2.0),
                reason=cut.purpose
            )
            for cut in seg_cuts
        ]

        plans[str(segment.id)] = SegmentMomentPlan(
            segment_id=segment.id,
            moments=moments,
            total_duration=sum(m.duration for m in moments),
            is_single_moment=(len(moments) == 1),
            chaining_reason=(
                f"Creative Director planned {len(moments)} cuts for this segment"
                if len(moments) > 1 else None
            )
        )

    return plans


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_creative_director(
    text_prompt: str,
    clip_index: ClipIndex,
    blueprint: StyleBlueprint,
    total_duration: float,
    bpm: float,
    onset_timestamps: List[float],
    energy_curve: List[float],
    api_key: Optional[str] = None,
    force_refresh: bool = False,
) -> Optional[Dict[str, SegmentMomentPlan]]:
    """
    Call the Creative Director for PROMPT mode.

    Returns a dict of {segment_id: SegmentMomentPlan} ready for the Editor,
    or None if the call fails (editor falls back to regular scoring).
    """
    cache_file = _get_cache_file(text_prompt, total_duration, bpm, clip_index)

    # Try cache first
    if not force_refresh and cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            cuts = [DirectorCut(**c) for c in data["cuts"]]
            print(f"  [DIRECTOR] Loaded {len(cuts)} cuts from cache: {cache_file.name}")
            return _cuts_to_segment_moment_plans(cuts, blueprint)
        except Exception as e:
            print(f"  [DIRECTOR] Cache load failed ({e}), regenerating...")

    print(f"\n{'='*60}")
    print(f"[CREATIVE DIRECTOR] Planning full edit ({total_duration:.1f}s, {len(clip_index.clips)} clips)")
    print(f"{'='*60}")

    prompt = _build_director_prompt(
        text_prompt=text_prompt,
        total_duration=total_duration,
        bpm=bpm,
        onset_timestamps=onset_timestamps,
        energy_curve=energy_curve,
        clip_index=clip_index,
        blueprint=blueprint
    )

    for attempt in range(3):
        try:
            print(f"  🎬 Creative Director: Calling DeepSeek (attempt {attempt+1})...")
            raw = call_deepseek_v3(prompt=prompt, system_prompt=(
                "You are a senior human film editor with 20 years of experience. "
                "You have strong creative taste. You output valid JSON only."
            ))

            # Parse response
            if isinstance(raw, dict) and "cuts" in raw:
                data = raw
            else:
                data = _parse_json_response(json.dumps(raw))

            cuts_raw = data.get("cuts", [])
            if not cuts_raw:
                raise ValueError("Creative Director returned empty cut list")

            # Build DirectorCut objects with validation
            clip_durations = {c.filename: c.duration for c in clip_index.clips}
            cuts: List[DirectorCut] = []
            seen_windows: Dict[str, set] = {}

            for raw_cut in cuts_raw:
                fn = raw_cut.get("clip_filename", "")
                cs = float(raw_cut.get("clip_start", 0))
                ce = float(raw_cut.get("clip_end", 0))
                mp = float(raw_cut.get("music_position", 0))
                purpose = raw_cut.get("purpose", "")
                arc = raw_cut.get("arc_stage", "")

                # Basic validation
                max_dur = clip_durations.get(fn, 9999)
                cs = max(0.0, min(cs, max_dur - 0.1))
                ce = min(ce, max_dur)
                if ce <= cs + 0.05:
                    print(f"  [DIRECTOR] Skipping invalid cut: {fn} [{cs:.2f}-{ce:.2f}]")
                    continue

                # Deduplicate windows
                if fn not in seen_windows:
                    seen_windows[fn] = set()
                window_key = f"{cs:.1f}-{ce:.1f}"
                if window_key in seen_windows[fn]:
                    print(f"  [DIRECTOR] Skipping duplicate window: {fn} {window_key}")
                    continue
                seen_windows[fn].add(window_key)

                cuts.append(DirectorCut(
                    clip_filename=fn,
                    clip_start=cs,
                    clip_end=ce,
                    music_position=mp,
                    purpose=purpose,
                    arc_stage=arc
                ))

            # Sort by music position
            cuts.sort(key=lambda c: c.music_position)

            if not cuts:
                raise ValueError("No valid cuts after validation")

            # Fix continuity: recalculate music_positions to be sequential (no gaps/overlaps)
            fixed_cuts: List[DirectorCut] = []
            pos = 0.0
            for cut in cuts:
                cut.music_position = pos
                pos += cut.duration
                fixed_cuts.append(cut)

            # If total < target_duration, extend last cut
            total_planned = sum(c.duration for c in fixed_cuts)
            if total_planned < total_duration - 0.1 and fixed_cuts:
                gap = total_duration - total_planned
                last = fixed_cuts[-1]
                max_dur = clip_durations.get(last.clip_filename, 9999)
                last.clip_end = min(last.clip_end + gap, max_dur)
                print(f"  [DIRECTOR] Extended last cut by {gap:.2f}s to fill timeline")

            arc_summary = data.get("arc_summary", "")
            print(f"  ✅ Creative Director planned {len(fixed_cuts)} cuts")
            print(f"  📝 Arc: {arc_summary[:120]}")
            for cut in fixed_cuts:
                print(f"     @ {cut.music_position:.2f}s → {cut.clip_filename} "
                      f"[{cut.clip_start:.2f}-{cut.clip_end:.2f}] ({cut.duration:.2f}s) | {cut.purpose[:60]}")

            # Cache the result
            cache_data = {
                "arc_summary": arc_summary,
                "cuts": [
                    {
                        "clip_filename": c.clip_filename,
                        "clip_start": c.clip_start,
                        "clip_end": c.clip_end,
                        "music_position": c.music_position,
                        "purpose": c.purpose,
                        "arc_stage": c.arc_stage
                    }
                    for c in fixed_cuts
                ]
            }
            cache_file.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
            print(f"  [DIRECTOR] Cached to {cache_file.name}")

            return _cuts_to_segment_moment_plans(fixed_cuts, blueprint)

        except Exception as e:
            print(f"  🔴 Creative Director attempt {attempt+1} failed: {e}")
            if attempt == 2:
                print("  ⚠️ Creative Director failed — falling back to Advisor+Scoring")
                return None
            time.sleep(1.5)

    return None
