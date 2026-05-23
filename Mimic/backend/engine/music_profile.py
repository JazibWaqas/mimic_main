"""
Music profile utilities.

MIMIC already analyzes BPM, onsets, and energy. This module packages that data
into an editor-friendly contract so planning stages can reason about structure,
not just raw numbers.
"""

from typing import Any, Dict, List


def _average(values: List[float]) -> float:
    return round(sum(values) / max(len(values), 1), 3)


def _energy_label(value: float) -> str:
    if value < 0.35:
        return "quiet"
    if value < 0.7:
        return "moderate"
    return "strong"


def _density_for_energy(value: float) -> str:
    if value < 0.35:
        return "hold longer shots"
    if value < 0.7:
        return "use moderate cuts"
    return "allow shorter beat-driven cuts"


def _ranges_from_energy(energy_curve: List[float], threshold: float, above: bool) -> List[Dict[str, float]]:
    ranges: List[Dict[str, float]] = []
    start = None

    for index, value in enumerate(energy_curve):
        active = value >= threshold if above else value <= threshold
        if active and start is None:
            start = index
        elif not active and start is not None:
            if index - start >= 2:
                ranges.append({"start": float(start), "end": float(index), "avg_energy": _average(energy_curve[start:index])})
            start = None

    if start is not None and len(energy_curve) - start >= 2:
        ranges.append({"start": float(start), "end": float(len(energy_curve)), "avg_energy": _average(energy_curve[start:])})

    return ranges[:4]


def build_music_profile(
    duration: float,
    bpm: float,
    onset_times: List[float] | None,
    energy_curve: List[float] | None,
) -> Dict[str, Any]:
    """Build a compact music profile for LLM planning and validation."""
    safe_duration = max(float(duration or 0), 0.0)
    safe_bpm = float(bpm or 120.0)
    onsets = [round(float(t), 3) for t in (onset_times or []) if 0 <= float(t) <= safe_duration]
    energy = [float(v) for v in (energy_curve or [])]

    peak_second = energy.index(max(energy)) if energy else 0
    peak_energy = round(max(energy), 3) if energy else 0.0

    quarters = []
    if energy:
        q = max(1, len(energy) // 4)
        for index in range(4):
            start = index * q
            end = len(energy) if index == 3 else min(len(energy), (index + 1) * q)
            avg = _average(energy[start:end])
            quarters.append({
                "start": round(start * safe_duration / max(len(energy), 1), 2),
                "end": round(end * safe_duration / max(len(energy), 1), 2),
                "avg_energy": avg,
                "feel": _energy_label(avg),
                "cut_guidance": _density_for_energy(avg),
            })

    beat_interval = 60.0 / safe_bpm if safe_bpm > 0 else 0.5
    phrase_seconds = beat_interval * 4
    phrase_boundaries = []
    cursor = 0.0
    while cursor <= safe_duration + 0.001:
        phrase_boundaries.append(round(cursor, 3))
        cursor += phrase_seconds

    return {
        "duration": round(safe_duration, 3),
        "bpm": round(safe_bpm, 2),
        "beat_interval": round(beat_interval, 3),
        "four_beat_phrase_seconds": round(phrase_seconds, 3),
        "onset_count": len(onsets),
        "key_onsets": onsets[:80],
        "peak_second": round(float(peak_second), 2),
        "peak_energy": peak_energy,
        "energy_quarters": quarters,
        "quiet_ranges": _ranges_from_energy(energy, 0.35, above=False),
        "strong_ranges": _ranges_from_energy(energy, 0.7, above=True),
        "phrase_boundaries": phrase_boundaries[:40],
        "planning_guidance": (
            "Use quiet ranges for longer holds, strong ranges for shorter beat-driven cuts, "
            "and place the strongest visual moment near the music peak when it fits the user intent."
        ),
    }


def format_music_profile_for_prompt(profile: Dict[str, Any] | None) -> str:
    """Format MusicProfile as compact prompt context."""
    if not profile:
        return "No structured music profile available."

    quarters = "\n".join(
        f"- {q['start']:.1f}-{q['end']:.1f}s: {q['feel']} energy ({q['avg_energy']:.2f}); {q['cut_guidance']}"
        for q in profile.get("energy_quarters", [])
    ) or "- No energy quarters available."

    quiet = ", ".join(f"{r['start']:.1f}-{r['end']:.1f}s" for r in profile.get("quiet_ranges", [])) or "none detected"
    strong = ", ".join(f"{r['start']:.1f}-{r['end']:.1f}s" for r in profile.get("strong_ranges", [])) or "none detected"

    return f"""
STRUCTURED MUSIC PROFILE:
- Duration: {profile.get('duration', 0)}s
- BPM: {profile.get('bpm', 120)}
- Beat interval: {profile.get('beat_interval', 0.5)}s
- 4-beat phrase: {profile.get('four_beat_phrase_seconds', 2.0)}s
- Strong onsets available: {profile.get('onset_count', 0)}
- Loudest peak: ~{profile.get('peak_second', 0)}s
- Quiet ranges: {quiet}
- Strong ranges: {strong}
- Phrase boundaries: {profile.get('phrase_boundaries', [])[:16]}
Energy by quarter:
{quarters}
Planning guidance: {profile.get('planning_guidance', '')}
"""
