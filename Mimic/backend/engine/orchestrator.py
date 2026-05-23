"""
Orchestrator: Main pipeline controller.

This is the SINGLE entry point for the entire backend. The UI calls
run_mimic_pipeline() and gets back a PipelineResult.

All state management, error handling, and module coordination happens here.
"""

import time
import sys

# Fix Windows console encoding for print statements
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass
import hashlib
import shutil
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Dict
from models import PipelineResult, StyleBlueprint, EDL, ClipIndex, DirectorCritique, AdvisorHints, LibraryHealth, StyleConfig, VaultReport
from engine.brain import (
    analyze_reference_video,
    analyze_all_clips,
    create_fallback_blueprint,
    REFERENCE_CACHE_VERSION
)
from engine.generator import generate_blueprint_from_text
from engine.reflector import generate_vault_report
from engine.editor import match_clips_to_blueprint, validate_edl, print_edl_summary, audit_edl_quality
from engine.processors import (
    standardize_clip,
    extract_audio,
    extract_audio_wav,
    extract_segment,
    concatenate_videos,
    merge_audio_video,
    create_silent_video,
    validate_output,
    detect_scene_changes,
    analyze_music,
    detect_bpm,
    get_beat_grid,
    get_video_duration
)
from engine.music_profile import build_music_profile
from utils import ensure_directory, cleanup_session, get_file_hash
from collections import defaultdict, Counter


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _merge_scene_and_beat_timestamps(
    scene_timestamps: List[float],
    beat_grid: List[float],
    max_gap: float = 8.0
) -> List[Tuple[float, str]]:
    """
    Merge visual scene cuts with beat-aligned timestamps.
    Returns list of (timestamp, origin) tuples where origin is 'visual' or 'beat'.
    
    Raising max_gap to 8.0s (Cinematic Safety) to prevent 'Mechanical Metronome' 
    subdivision of long emotional holds.
    """
    # 1. Start with 'Beat-Snapped' visual cuts
    combined_dict = {} # timestamp -> origin
    for scene_cut in scene_timestamps:
        # Find nearest beat to the visual cut
        nearest_beat = min(beat_grid, key=lambda x: abs(x - scene_cut))
        # Only snap if the beat is close enough (within 0.25s), otherwise keep the visual cut
        # V12.1 GUARD: Never snap to 0.0 (it creates zero-duration segments)
        if abs(nearest_beat - scene_cut) < 0.25 and nearest_beat > 0.1:
            combined_dict[nearest_beat] = "visual"
        elif scene_cut > 0.1:
            combined_dict[scene_cut] = "visual"
    
    # 2. Safety Subdivision (Only for EXTREME gaps)
    # Ensure 0.0 is there but not duplicated
    all_ts = sorted(list(set(combined_dict.keys()) | {0.0}))
    
    for i in range(len(all_ts) - 1):
        start = all_ts[i]
        end = all_ts[i + 1]
        gap = end - start
        
        # If the gap is massive (stagnant), insert ONE beat-aligned cut in the middle
        if gap > max_gap:
            midpoint = start + (gap / 2)
            nearest_mid_beat = min(beat_grid, key=lambda x: abs(x - midpoint))
            if start < nearest_mid_beat < end:
                combined_dict[nearest_mid_beat] = "beat"
                
    # Sort and return as tuples
    return sorted([(ts, origin) for ts, origin in combined_dict.items()])


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def run_mimic_pipeline(
    reference_path: Optional[str],
    clip_paths: List[str],
    session_id: str,
    output_dir: str,
    api_key: str | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    iteration: int = 1,
    text_prompt: Optional[str] = None,
    target_duration: float = 15.0,
    music_path: Optional[str] = None,
    style_config: Optional[StyleConfig] = None # v14.9 Style Control (Post-Editor Layer)
) -> PipelineResult:
    """
    Execute the complete MIMIC pipeline.
    
    STAGES:
    0. Generate Blueprint from text (if no reference)
    1. Validate inputs
    2. Analyze reference video (Gemini) - SKIPPED if Stage 0 used
    3. Analyze user clips (Gemini)
    4. Match clips to blueprint segments (Editor)
    5. Render video (FFmpeg)
    6. Reflect & Critique
    """
    start_time = time.time()
    
    # Setup file logging and results naming
    ref_name = Path(reference_path).stem if reference_path else "text_prompt"
    # Use 'master' if no session_id is provided, otherwise first 12 chars
    tag = session_id if len(session_id) < 12 else session_id[:12]
    
    # Versioned naming: ref_tag_v1
    base_output_name = f"{ref_name}_{tag}_v{iteration}"
    
    log_path = Path(output_dir) / f"{base_output_name}.log"
    json_report_path = Path(output_dir) / f"{base_output_name}.json"
    music_profile = build_music_profile(
        duration=target_duration,
        bpm=120.0,
        onset_times=[],
        energy_curve=[],
    )
    
    log_file = None
    original_stdout = sys.stdout
    
    class Tee:
        def __init__(self, *files):
            self.files = [f for f in files if f is not None]
        def write(self, s):
            for f in self.files:
                f.write(s)
                try: 
                    f.flush()
                except Exception: 
                    pass
        def flush(self):
            for f in self.files:
                try: 
                    f.flush()
                except Exception: 
                    pass
    
    try:
        if log_path:
            log_file = open(log_path, 'w', encoding='utf-8')
        sys.stdout = Tee(original_stdout, log_file)
        print("=" * 80)
        print(f"PIPELINE RUN: {Path(reference_path).name.upper() if reference_path else 'TEXT_PROMPT'}")
        print("=" * 80)
        print(f"Session ID: {session_id}")
        print(f"Reference: {Path(reference_path).name if reference_path else 'None (Creator Mode)'}")
        print(f"Clips: {len(clip_paths)}")
        print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    except Exception as e:
        print(f"[WARN] Could not create log file: {e}")
        log_file = None
    
    def update_progress(step: int, total: int, message: str):
        """Helper to call progress callback if provided."""
        if progress_callback:
            progress_callback(step, total, message)
        print(f"\n[{step}/{total}] {message}")
    
    TOTAL_STEPS = 5
    
    try:
        # ==================================================================
        # STEP 1: VALIDATE INPUTS
        # ==================================================================
        update_progress(1, TOTAL_STEPS, "Validating inputs...")
        
        _validate_inputs(reference_path, clip_paths)
        
        # Setup session directories
        # Use absolute path to ensure consistency regardless of CWD
        BASE_DIR = Path(__file__).resolve().parent.parent.parent
        DATA_DIR = BASE_DIR / "data"
        
        # Permanent uploads are in data/uploads/{session_id}/
        # Temporary processing files go to temp/{session_id}/
        temp_session_dir = BASE_DIR / "temp" / session_id
        standardized_dir = temp_session_dir / "standardized"
        segments_dir = temp_session_dir / "segments"
        
        # PERSISTENT CACHE FOR STANDARDIZED CLIPS
        persistent_standardized_cache = DATA_DIR / "cache" / "standardized"
        persistent_standardized_cache.mkdir(parents=True, exist_ok=True)
        
        ensure_directory(temp_session_dir)
        ensure_directory(standardized_dir)
        ensure_directory(segments_dir)
        ensure_directory(output_dir)
        ensure_directory(persistent_standardized_cache)
        
        # Note: Uploaded files stay in data/uploads/ (permanent)
        # Only temp/ files (standardized, segments) can be cleaned up
        
        # ==================================================================
        # STEP 2: ANALYZE REFERENCE / GENERATE BLUEPRINT
        # ==================================================================
        if text_prompt:
            update_progress(2, TOTAL_STEPS, "Synthesizing Blueprint from text prompt...")
            
            # ── Music analysis (determines target_duration) ──────────────
            audio_source = music_path if music_path else reference_path
            
            if audio_source:
                print(f"  [MUSIC] Analyzing audio source: {Path(audio_source).name}")
                audio_analysis_path = temp_session_dir / "music_analysis.wav"
                if extract_audio_wav(audio_source, str(audio_analysis_path)):
                    try:
                        music_duration = get_video_duration(str(audio_analysis_path))
                        if music_duration > 3.0:
                            print(f"  [MUSIC] Detected duration: {music_duration:.2f}s. Overriding target_duration.")
                            target_duration = music_duration
                    except Exception as e:
                        print(f"  [WARN] Could not detect music duration: {e}")

                    music_intel = analyze_music(str(audio_analysis_path))
                    ref_bpm = music_intel["bpm"]
                    onset_times = music_intel["onset_times"]
                    energy_curve = music_intel["energy_curve"]
                    print(f"  [MUSIC] Detected BPM: {ref_bpm:.2f}")
                else:
                    ref_bpm = 120.0; onset_times = []; energy_curve = []
                    print(f"  [WARN] Music analysis failed, using default 120 BPM")
            else:
                ref_bpm = 120.0; onset_times = []; energy_curve = []
                print(f"  [WARN] No audio source provided for text-based edit, using default 120 BPM")

            music_profile = build_music_profile(
                duration=target_duration,
                bpm=ref_bpm,
                onset_times=onset_times,
                energy_curve=energy_curve,
            )
            print(
                f"  [MUSIC] Profile ready: peak ~{music_profile['peak_second']}s, "
                f"{music_profile['onset_count']} onsets"
            )
            
            # ── PROMPT MODE: Analyze clips BEFORE blueprint generation ────
            # The blueprint must know what material it has to work with.
            # A blueprint written blind will ask for vibes/subjects that don't exist.
            print(f"\n  [LIBRARY SCAN] Pre-analyzing {len(clip_paths)} clips before blueprint synthesis...")
            try:
                _pre_clip_index = analyze_all_clips(clip_paths, api_key)
                _clips = _pre_clip_index.clips
                
                # Build a compact library snapshot for the blueprint generator
                _vibe_counts = Counter()
                _subject_counts = Counter()
                _energy_counts = Counter()
                _motion_counts = Counter()
                for c in _clips:
                    for v in (c.vibes or []):
                        _vibe_counts[v.lower()] += 1
                    for s in (c.primary_subject or []):
                        _subject_counts[s.lower()] += 1
                    _energy_counts[c.energy.value] += 1
                    _motion_counts[c.motion.value] += 1
                
                _top_vibes = [v for v, _ in _vibe_counts.most_common(8)]
                _top_subjects = [s for s, _ in _subject_counts.most_common(5)]
                _total_secs = sum(c.duration for c in _clips)
                _strongest_clips = []
                for c in sorted(_clips, key=lambda clip: (clip.clip_quality, clip.duration), reverse=True)[:8]:
                    _strongest_clips.append({
                        "filename": c.filename,
                        "duration": round(c.duration, 1),
                        "energy": c.energy.value,
                        "motion": c.motion.value,
                        "subjects": c.primary_subject[:3],
                        "vibes": c.vibes[:4],
                        "best_for": c.best_for[:3],
                        "avoid_for": c.avoid_for[:2],
                        "description": (c.content_description or "")[:140]
                    })
                
                library_snapshot = {
                    "clip_count": len(_clips),
                    "total_footage_seconds": round(_total_secs),
                    "dominant_vibes": _top_vibes,
                    "dominant_subjects": _top_subjects,
                    "energy_distribution": dict(_energy_counts),
                    "motion_distribution": dict(_motion_counts),
                    "strongest_clips": _strongest_clips,
                    "note": (
                        "These clips are handpicked by the user and are ALL usable. "
                        "Design the blueprint vibes and arc to match what actually exists in the library. "
                        "Do NOT design segments that require vibes or subjects not present above."
                    )
                }
                print(f"  [LIBRARY SCAN] Done. Dominant vibes: {_top_vibes[:4]} | Subjects: {_top_subjects[:3]}")
                
                # Reuse this pre-analyzed index in Step 3 to avoid duplicate API calls
                _pre_analyzed_clip_index = _pre_clip_index
                
            except Exception as e:
                print(f"  [WARN] Pre-scan failed ({e}), blueprint will generate without library context.")
                library_snapshot = None
                _pre_analyzed_clip_index = None
            
            # ── Generate blueprint (now informed by actual library) ───────
            blueprint = generate_blueprint_from_text(
                text_prompt, target_duration, api_key,
                bpm=ref_bpm,
                energy_curve=energy_curve,
                library_snapshot=library_snapshot,
                music_profile=music_profile
            )
            print(f"[OK] Gemini successfully synthesized blueprint from text: {len(blueprint.segments)} segments.")
        else:
            update_progress(2, TOTAL_STEPS, "Detecting visual cuts and analyzing reference structure...")
            
            # Setup audio analysis path
            audio_analysis_path = temp_session_dir / "ref_analysis_audio.wav"
            ref_bpm = 120.0
            onset_times = []
            energy_curve = []
            
            try:
                # [STEP 2] Visual Scene Change Detection (The "Eyes")
                print(f"  [DIAGNOSTIC] Detecting visual scene changes (threshold=0.12)...")
                scene_changes = detect_scene_changes(reference_path, threshold=0.12)
                
                # 2b. Extract audio and detect BPM + full music intelligence
                if extract_audio_wav(reference_path, str(audio_analysis_path)):
                    music_intel = analyze_music(str(audio_analysis_path))
                    ref_bpm = music_intel["bpm"]
                    onset_times = music_intel["onset_times"]
                    energy_curve = music_intel["energy_curve"]
                else:
                    onset_times = []
                    energy_curve = []
                
                # 2c. HYBRID DETECTION: Merge visual cuts + beat-aligned subdivision
                ref_duration = get_video_duration(reference_path)
                music_profile = build_music_profile(
                    duration=ref_duration,
                    bpm=ref_bpm,
                    onset_times=onset_times,
                    energy_curve=energy_curve,
                )
                beat_grid = get_beat_grid(ref_duration, ref_bpm)
                combined_hints = _merge_scene_and_beat_timestamps(
                    scene_changes, 
                    beat_grid, 
                    max_gap=8.0 # Cinematic Breath: Allow up to 8s holds without forcing cuts
                )
                
                # Extract just the raw floats for Gemini's prompt
                raw_timestamps = [t[0] for t in combined_hints]
                
                print(f"  [HYBRID] Visual cuts: {len(scene_changes)}, Beat-enhanced: {len(combined_hints)}")
                
                # 2d. Analyze with Gemini using hybrid timestamps
                blueprint = analyze_reference_video(
                    reference_path, 
                    api_key=api_key,
                    scene_timestamps=raw_timestamps
                )


                # v12.1: Transfer cut origins to Segments for Pacing Authority
                # combined_hints has N timestamps. Segments 2..N+1 start at these points.
                # Segment 1 always starts at 0.0 (visual origin).
                for i, segment in enumerate(blueprint.segments):
                    if i == 0:
                        segment.cut_origin = "visual"
                    elif i-1 < len(combined_hints):
                        segment.cut_origin = combined_hints[i-1][1]
                
                # v12.1 ROBUSTNESS: Validate all segments have cut_origin
                # If scene detection failed or combined_hints was malformed, ensure safe defaults
                for segment in blueprint.segments:
                    if not hasattr(segment, 'cut_origin') or segment.cut_origin not in ["visual", "beat"]:
                        segment.cut_origin = "visual"  # Safe default: protect from subdivision


                print(f"[OK] Gemini successfully analyzed reference: {len(blueprint.segments)} segments found.")
            except Exception as e:
                print(f"[ERROR] Gemini reference analysis failed: {e}")
                print("    FALLING BACK to linear 2-second segments. Results will be generic.")
                blueprint = create_fallback_blueprint(reference_path)
        
        # ==================================================================
        # STEP 3: ANALYZE USER CLIPS
        # ==================================================================
        update_progress(3, TOTAL_STEPS, "Analyzing user clips with Gemini AI...")
        
        # 1. Analyze ORIGINAL clips first (allows better caching)
        # PROMPT MODE: Reuse the pre-scan from Step 2 - clips were already analyzed.
        # REFERENCE MODE: Analyze fresh here as usual.
        try:
            if text_prompt and '_pre_analyzed_clip_index' in locals() and _pre_analyzed_clip_index is not None:
                print(f"  [SKIP] Clips already analyzed in library scan. Reusing results.")
                clip_index = _pre_analyzed_clip_index
            else:
                clip_index = analyze_all_clips(clip_paths, api_key)
            print(f"[OK] Gemini successfully analyzed {len(clip_index.clips)} clips (using originals for cache).")
            
            # Compute Library Health
            clips = clip_index.clips
            avg_quality = sum(c.clip_quality for c in clips) / len(clips) if clips else 0
            energy_dist = Counter(c.energy.value for c in clips)
            subject_dist = Counter()
            for c in clips:
                for s in c.primary_subject:
                    subject_dist[s] += 1
            
            # Simple confidence score (0-100)
            # Factors: count, quality, diversity
            base_score = min(len(clips) * 5, 40) # Up to 40 pts for count
            quality_score = avg_quality * 10 # Up to 50 pts for quality
            diversity_score = min(len(subject_dist) * 5, 10) # Up to 10 pts for diversity
            
            library_health = LibraryHealth(
                asset_count=len(clips),
                avg_quality=avg_quality,
                energy_distribution=dict(energy_dist),
                primary_subject_distribution=dict(subject_dist),
                confidence_score=base_score + quality_score + diversity_score
            )
            print(f"  [OK] Library Health: {library_health.confidence_score:.1f}% readiness")
            
        except Exception as e:
            print(f"[ERROR] Gemini clip analysis failed: {e}")
            print("    FALLING BACK to default energy levels. Edit quality will be reduced.")
            from models import ClipMetadata, EnergyLevel, MotionType
            
            clips = []
            for path in clip_paths:
                clips.append(ClipMetadata(
                    filename=Path(path).name,
                    filepath=path,
                    duration=get_video_duration(path),
                    energy=EnergyLevel.MEDIUM,
                    motion=MotionType.DYNAMIC
                ))
            clip_index = ClipIndex(clips=clips)
            
        # 2. Standardize clips for rendering (with persistent caching)
        standardized_paths = []
        for i, clip_path in enumerate(clip_paths, start=1):
            input_p = Path(clip_path)
            output_path = standardized_dir / f"clip_{i:03d}.mp4"
            
            # Generate a unique cache key for this specific file state
            # Fast Fingerprinting (v12.4): uses name/size/mtime cache
            cache_hash = get_file_hash(input_p)
            cached_filename = f"std_{cache_hash}.mp4"
            cached_path = persistent_standardized_cache / cached_filename
            
            if cached_path.exists():
                print(f"  [CACHE] Hit! Using persistent standardized clip: {input_p.name}")
                shutil.copy2(str(cached_path), str(output_path))
            else:
                print(f"  [NEW] Standardizing clip {i}/{len(clip_paths)}: {input_p.name} (first-time processing)...")
                # find energy for this clip (v12.5 Context-Aware)
                from models import EnergyLevel
                clip_energy = EnergyLevel.MEDIUM
                for cm in clip_index.clips:
                    if cm.filename == input_p.name:
                        # Pass the ENUM object, not the string value
                        clip_energy = cm.energy 
                        break
                standardize_clip(str(input_p), str(output_path), energy=clip_energy)
                # Save to persistent cache
                shutil.copy2(str(output_path), str(cached_path))
                print(f"  [CACHE] Saved standardized clip to persistent storage.")
                
            standardized_paths.append(str(output_path))
            
            # Update the filepath in the clip index to the standardized one
            original_filename = input_p.name
            for clip_meta in clip_index.clips:
                if clip_meta.filename == original_filename:
                    clip_meta.filepath = str(output_path)
                    break
        
        print(f"[OK] All clips standardized (cached or new) and ready for render.")
        
        # Hardening (v12.5): Persist the hash registry now so we don't lose the fingerprints
        from utils import save_hash_registry
        save_hash_registry()
        
        # ==================================================================
        # STEP 4: MATCH & EDIT
        # ==================================================================
        update_progress(4, TOTAL_STEPS, "Creating edit sequence...")
        
        # CLIP LIBRARY SANITY CHECK (v14.0 diagnostic)
        segment_count = len(blueprint.segments)
        clip_count = len(clip_index.clips)
        if segment_count > 15 and clip_count < 10:
            print(f"\n   [WARN]  CLIP LIBRARY WARNING:")
            print(f"      Reference has {segment_count} segments but only {clip_count} clips available.")
            print(f"      This will cause heavy clip repetition and reduced edit quality.")
            print(f"      Recommendation: Add {segment_count - clip_count}+ more clips for better diversity.")
            print()
        
        # v14.7: Determine editing mode based on input source
        edit_mode = "PROMPT" if text_prompt else "REFERENCE"
        
        edl, advisor_hints = match_clips_to_blueprint(
            blueprint, 
            clip_index, 
            find_best_moments=True, 
            api_key=api_key,
            reference_path=reference_path,
            bpm=ref_bpm,
            onset_times=onset_times,      # Musical hit points for cut snapping
            energy_curve=energy_curve,    # Per-second RMS energy for Creative Director
            music_profile=music_profile,
            mode=edit_mode,
            run_id=base_output_name
        )
        
        # Validate EDL - loud on failure but don't crash (allow debug render)
        try:
            validate_edl(edl, blueprint)
            print("  [OK] EDL validated: timeline integrity confirmed")
        except ValueError as e:
            print(f"\n{'!'*60}")
            print(f"  [WARN] EDL VALIDATION FAILED - timeline integrity problem")
            print(f"  Error: {e}")
            print(f"  Decisions: {len(edl.decisions)} | Blueprint segments: {len(blueprint.segments)}")
            if edl.decisions:
                print(f"  Timeline: {edl.decisions[0].timeline_start:.3f}s -> {edl.decisions[-1].timeline_end:.3f}s (target: {blueprint.total_duration:.3f}s)")
            print(f"  Continuing render for debug - check the output video carefully")
            print(f"{'!'*60}\n")

        quality_warnings = audit_edl_quality(edl, blueprint, music_profile=music_profile)
        if quality_warnings:
            print("  [QUALITY] Edit audit warnings:")
            for warning in quality_warnings:
                print(f"    - {warning}")
        else:
            print("  [QUALITY] Edit audit passed: no obvious timing/repetition issues")
        
        print_edl_summary(edl, blueprint, clip_index)
        
        # ==================================================================
        # STEP 5: RENDER VIDEO
        # ==================================================================
        update_progress(5, TOTAL_STEPS, "Rendering final video...")
        
        # Extract segments according to EDL (Clock-Lock: timeline duration is authority)
        segment_paths = []
        for i, decision in enumerate(edl.decisions, start=1):
            segment_path = segments_dir / f"segment_{i:03d}.mp4"
            slot_duration = decision.timeline_end - decision.timeline_start
            hold_secs = getattr(decision, 'hold_end_seconds', None)
            if hold_secs and hold_secs > 0.01:
                content_duration = decision.clip_end - decision.clip_start
                extract_segment(
                    decision.clip_path,
                    str(segment_path),
                    decision.clip_start,
                    content_duration,
                    hold_last_frame_seconds=hold_secs
                )
            else:
                extract_segment(
                    decision.clip_path,
                    str(segment_path),
                    decision.clip_start,
                    slot_duration
                )
            segment_paths.append(str(segment_path))
        
        # Concatenate segments
        temp_video_path = temp_session_dir / "temp_video.mp4"
        concatenate_videos(segment_paths, str(temp_video_path))
        concat_duration = get_video_duration(str(temp_video_path))
        target_duration = blueprint.total_duration
        if abs(concat_duration - target_duration) > 0.05:
            print(f"  [WARN] Concat duration {concat_duration:.2f}s differs from blueprint {target_duration:.2f}s (drift: {concat_duration - target_duration:+.2f}s)")
        
        # v15.0: DURATION TRIM GUARD
        # Floating-point accumulation across many segments causes 0.5-1s tail drift.
        # If video is longer than target by more than 100ms, trim precisely.
        if concat_duration > target_duration + 0.1:
            trimmed_path = temp_session_dir / "temp_video_trimmed.mp4"
            import subprocess as _sp
            trim_cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_video_path),
                "-t", f"{target_duration:.6f}",
                "-c", "copy",
                str(trimmed_path)
            ]
            try:
                _sp.run(trim_cmd, check=True, capture_output=True)
                temp_video_path = trimmed_path
                print(f"  [TRIM] Duration trimmed: {concat_duration:.2f}s -> {target_duration:.2f}s")
            except Exception as _te:
                print(f"  [WARN] Duration trim failed: {_te}, using untrimmed video")

        # Style metadata is retained for the Vault/editor UI, but exports are clean.
        # Captions/color treatments are no longer burned into the MP4 here.
        current_style_config = style_config or getattr(blueprint, 'style_config', None)
        print("[STYLE] Skipping MP4 burn-in; style/text kept as editable metadata")
        render_source = temp_video_path
        
        # Handle audio
        audio_path = temp_session_dir / "ref_audio.aac"
        # Prioritize music_path, then reference_path
        source_audio_path = music_path if music_path else reference_path
        
        audio_extracted = False
        if source_audio_path:
            audio_extracted = extract_audio(source_audio_path, str(audio_path))
        
        # Final output (use full session_id to prevent collisions)
        output_filename = f"{base_output_name}.mp4"
        final_output_path = Path(output_dir) / output_filename
        
        # Remove old file if it exists (force regeneration)
        if final_output_path.exists():
            print(f"[WARN] Removing existing output file: {final_output_path}")
            final_output_path.unlink()
        
        if audio_extracted:
            # P1 SAFEGUARD: Video timing is sacred, audio adapts.
            # Reference audio is merged using the authoritative video duration.
            merge_audio_video(
                str(render_source),
                str(audio_path),
                str(final_output_path)
            )
        else:
            create_silent_video(str(render_source), str(final_output_path))
        
        # Validate output
        if not validate_output(str(final_output_path)):
            raise RuntimeError("Output video validation failed")
        
        # ==================================================================
        # SUCCESS
        # ==================================================================
        processing_time = time.time() - start_time
        
        output_duration = get_video_duration(str(final_output_path))
        ref_duration = blueprint.total_duration
        
        print(f"\n{'='*80}")
        print("[OK] SUCCESS!")
        print(f"{'='*80}")
        print(f"\n[REPORT] Basic Results:")
        print(f"   Output: {final_output_path.name}")
        print(f"   Duration: {output_duration:.2f}s (ref: {ref_duration:.2f}s)")
        print(f"   Difference: {abs(output_duration - ref_duration):.2f}s")
        print(f"   Processing time: {processing_time:.1f}s")
        
        # Print comprehensive analysis (matching test_ref.py style)
        _print_comprehensive_analysis(blueprint, edl, clip_index, clip_paths, advisor=advisor_hints)
        
        print(f"\n{'='*80}")
        print(f" Watch the result: {final_output_path}")
        print(f"{'='*80}\n")
        
        # ==================================================================
        # STEP 6: VAULT INTELLIGENCE (The Creative Partner)
        # ==================================================================
        update_progress(6, 6, "Generating Vault intelligence report...")
        try:
            # Legacy Reflector (DirectorCritique) is now ARCHIVED
            # critique = reflect_on_edit(blueprint, edl, clip_index, advisor=advisor_hints)
            critique_placeholder = DirectorCritique(
                overall_score=8.0, 
                monologue="Legacy reflector archived. See Vault report.",
                technical_fidelity="System active."
            )
            
            # v12.2: Vault Intelligence Report is now the ONLY explanation system
            vault_report = generate_vault_report(blueprint, edl, advisor_hints, critique_placeholder)
            print(f"  [OK] Vault Report generated.")
        except Exception as e:
            print(f"  [WARN] Vault generation failed: {e}")
            vault_report = None
            critique_placeholder = None

        result = PipelineResult(
            success=True,
            output_path=str(final_output_path),
            blueprint=blueprint,
            clip_index=clip_index,
            edl=edl,
            advisor=advisor_hints,
            critique=critique_placeholder, # Kept for schema compatibility but inactive
            vault_report=vault_report,
            library_health=library_health,
            iteration=iteration,
            processing_time_seconds=processing_time,
            style_config=current_style_config, # v14.9 Style Control (Post-Editor Layer)
            contract={
                "type": "result",
                "version": REFERENCE_CACHE_VERSION,
                "session_id": session_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        )
        
        # SAVE INTELLIGENCE REPORT FOR FRONTEND (Master Whitebox File)
        try:
            print(f"[PROCESS] Exporting master intelligence report...")
            if result.advisor:
                print(f"   (Intelligence data confirmed: {len(result.advisor.editorial_strategy)} chars)")
            
            with open(json_report_path, "w", encoding="utf-8") as jf:
                json_data = result.model_dump_json(indent=2)
                jf.write(json_data)
                jf.flush()
                # Force OS to write to disk
                import os
                os.fsync(jf.fileno())
            print(f"[OK] Intelligence report saved: {json_report_path} ({len(json_data)} bytes)")
        except Exception as e:
            print(f"[WARN] Failed to save JSON report: {e}")
            import traceback
            traceback.print_exc()

        # Restore stdout and close log file
        if log_file:
            sys.stdout = original_stdout
            log_file.close()
            print(f"[OK] Analysis log saved: {log_path}")
        
        # CLEANUP CACHE CLUTTER (Optional: disabled for demo speed)
        # try:
        #     for muted_vid in Path("data/cache").glob("muted_*.mp4"):
        #         muted_vid.unlink()
        # except:
        #     pass
            
        return result
        
    except Exception as e:
        processing_time = time.time() - start_time
        
        print(f"\n{'='*80}")
        print("NO FAILED")
        print(f"{'='*80}")
        print(f"   Error: {str(e)}")
        print(f"{'='*80}\n")
        
        import traceback
        traceback.print_exc()
        
        # Restore stdout and close log file even on error
        if log_file:
            sys.stdout = original_stdout
            log_file.close()
            print(f"Error log saved: {log_path}")
        
        return PipelineResult(
            success=False,
            error=str(e),
            processing_time_seconds=processing_time
        )


# ============================================================================
# VALIDATION
# ============================================================================

def _print_comprehensive_analysis(blueprint: StyleBlueprint, edl: EDL, clip_index: ClipIndex, clip_paths: List[str], advisor: Optional[AdvisorHints] = None) -> None:
    """Print comprehensive debugging analysis matching test_ref.py style."""
    if not blueprint or not edl:
        return
    
    print(f"\n{'='*80}")
    print("[AI] COMPREHENSIVE SYSTEM ANALYSIS")
    print(f"{'='*80}")
    
    # 1. Reference Analysis Breakdown
    print(f"\n[VIDEO] Reference Analysis:")
    print(f"   Editing Style: {blueprint.editing_style}")
    print(f"   Emotional Intent: {blueprint.emotional_intent}")
    arc_desc = blueprint.arc_description[:100] + "..." if len(blueprint.arc_description) > 100 else blueprint.arc_description
    print(f"   Arc Description: {arc_desc}")
    print(f"   Total Segments: {len(blueprint.segments)}")
    
    # 1.5. Blueprint Full Detail
    print(f"\n[PLAN] BLUEPRINT FULL SEGMENT LIST:")
    for i, seg in enumerate(blueprint.segments):
        print(f"   {i+1:02d}: {seg.start:5.2f}-{seg.end:5.2f}s | {seg.energy.value:6} | Vibe: {seg.vibe:10} | {seg.arc_stage}")
    
    # 2. Arc Stage Distribution
    arc_stages = Counter([seg.arc_stage for seg in blueprint.segments])
    print(f"\n[RISE] Arc Stage Distribution:")
    for stage, count in arc_stages.most_common():
        pct = (count / len(blueprint.segments)) * 100
        print(f"   {stage}: {count} segments ({pct:.1f}%)")
    
    # 3. Vibe Distribution
    vibes = Counter([seg.vibe for seg in blueprint.segments if seg.vibe != "General"])
    if vibes:
        print(f"\n[PROMPT] Vibe Distribution:")
        for vibe, count in vibes.most_common():
            pct = (count / len(blueprint.segments)) * 100
            print(f"   {vibe}: {count} segments ({pct:.1f}%)")
    
    # 4. Clip Usage Analysis
    clip_usage = defaultdict(int)
    clip_reasoning = defaultdict(list)
    for decision in edl.decisions:
        clip_name = Path(decision.clip_path).name
        clip_usage[clip_name] += 1
        clip_reasoning[clip_name].append(decision.reasoning)
    
    print(f"\n[CLIP] Clip Usage Analysis:")
    print(f"   Unique clips used: {len(clip_usage)}/{len(clip_paths)}")
    print(f"   Most used clips:")
    for clip_name, count in sorted(clip_usage.items(), key=lambda x: x[1], reverse=True)[:5]:
        pct = (count / len(edl.decisions)) * 100
        print(f"     {clip_name}: {count} times ({pct:.1f}%)")
    
    # 5. Reasoning Breakdown
    smart_matches = sum(1 for d in edl.decisions if " Smart Match" in d.reasoning)
    good_fits = sum(1 for d in edl.decisions if "[MATCH] Good Fit" in d.reasoning)
    constraint_relax = sum(1 for d in edl.decisions if "[FALLBACK] Constraint Relaxation" in d.reasoning)
    
    print(f"\n[AI] AI Reasoning Breakdown:")
    if len(edl.decisions) > 0:
        print(f"    Smart Match: {smart_matches} ({smart_matches/len(edl.decisions)*100:.1f}%)")
        print(f"   [MATCH] Good Fit: {good_fits} ({good_fits/len(edl.decisions)*100:.1f}%)")
        print(f"   [FALLBACK] Constraint Relaxation: {constraint_relax} ({constraint_relax/len(edl.decisions)*100:.1f}%)")
    
    # 6. Vibe Matching Stats
    vibe_matches = sum(1 for d in edl.decisions if d.vibe_match)
    print(f"\n[PROMPT] Vibe Matching:")
    if len(edl.decisions) > 0:
        print(f"   Matches: {vibe_matches}/{len(edl.decisions)} ({vibe_matches/len(edl.decisions)*100:.1f}%)")
    
    # 7. Cut Statistics by Arc Stage
    print(f"\n[TIMING] Cut Statistics by Arc Stage:")
    for stage in ["Intro", "Build-up", "Peak", "Outro", "Main"]:
        stage_decisions = []
        for decision in edl.decisions:
            for seg in blueprint.segments:
                if seg.start <= decision.timeline_start < seg.end:
                    if seg.arc_stage == stage:
                        stage_decisions.append(decision.timeline_end - decision.timeline_start)
                    break
        
        if stage_decisions:
            avg = sum(stage_decisions) / len(stage_decisions)
            print(f"   {stage}: {len(stage_decisions)} cuts, avg {avg:.2f}s")
    
    # 8. Overall Cut Statistics
    durations = [(d.timeline_end - d.timeline_start) for d in edl.decisions]
    if durations:
        avg_cut = sum(durations) / len(durations)
        min_cut = min(durations)
        max_cut = max(durations)
        
        print(f"\n[TIMING] Overall Cut Statistics:")
        print(f"   Total cuts: {len(edl.decisions)}")
        print(f"   Average cut: {avg_cut:.2f}s")
        print(f"   Shortest cut: {min_cut:.2f}s")
        print(f"   Longest cut: {max_cut:.2f}s")
    
    # 9. Sample Reasoning Examples
    print(f"\n[NOTE] Sample AI Reasoning (first 5 decisions):")
    for i, decision in enumerate(edl.decisions[:5], 1):
        clip_name = Path(decision.clip_path).name
        reasoning_preview = decision.reasoning[:80] + "..." if len(decision.reasoning) > 80 else decision.reasoning
        print(f"   {i}. {clip_name}: {reasoning_preview}")
    
    # 10. Clip Index Stats
    if clip_index:
        print(f"\n[CACHE] CLIP REGISTRY ({len(clip_index.clips)} total):")
        for i, clip in enumerate(sorted(clip_index.clips, key=lambda x: x.filename)):
            vibes_str = ", ".join(clip.vibes[:3]) if hasattr(clip, 'vibes') and clip.vibes else "N/A"
            print(f"   {i+1:02d}: {clip.filename:15} | {clip.energy.value:6} | {clip.duration:5.1f}s | Vibes: {vibes_str}")
        
        clips_with_moments = sum(1 for c in clip_index.clips if hasattr(c, 'best_moments') and c.best_moments)
        clips_with_vibes = sum(1 for c in clip_index.clips if hasattr(c, 'vibes') and c.vibes)
        
        print(f"\n[LIST] Metadata Coverage:")
        print(f"   Best Moments: {clips_with_moments}/{len(clip_index.clips)}")
        print(f"   Vibes: {clips_with_vibes}/{len(clip_index.clips)}")
    
    # 11. Temporal Drift Check
    gaps = []
    overlaps = []
    for i in range(1, len(edl.decisions)):
        gap = edl.decisions[i].timeline_start - edl.decisions[i-1].timeline_end
        if abs(gap) > 0.001:
            if gap > 0:
                gaps.append((i, gap))
            else:
                overlaps.append((i, abs(gap)))
    
    print(f"\n[CHECK] Temporal Precision Check:")
    if gaps:
        print(f"   [WARN] WARNING: Timeline Gaps Detected ({len(gaps)}):")
        for i, gap in gaps[:5]:
            print(f"     Gap after decision {i}: {gap:.6f}s")
        if len(gaps) > 5:
            print(f"     ... and {len(gaps) - 5} more gaps")
    elif overlaps:
        print(f"   [WARN] WARNING: Timeline Overlaps Detected ({len(overlaps)}):")
        for i, overlap in overlaps[:5]:
            print(f"     Overlap after decision {i}: {overlap:.6f}s")
        if len(overlaps) > 5:
            print(f"     ... and {len(overlaps) - 5} more overlaps")
    else:
        print(f"   [OK] TIMELINE INTEGRITY: No gaps or overlaps detected (all within 0.001s tolerance)")
    
    # 12. Material Efficiency Stats
    if clip_index:
        total_available_duration = sum(c.duration for c in clip_index.clips)
        used_unique_duration = sum(d.clip_end - d.clip_start for d in edl.decisions)
        
        unique_segments = set()
        for decision in edl.decisions:
            clip_name = Path(decision.clip_path).name
            segment_key = f"{clip_name}:{decision.clip_start:.2f}-{decision.clip_end:.2f}"
            unique_segments.add(segment_key)
        
        print(f"\n[CACHE] Material Efficiency:")
        print(f"   Total source duration available: {total_available_duration:.2f}s")
        print(f"   Total duration used in edit: {used_unique_duration:.2f}s")
        print(f"   Unique clip segments used: {len(unique_segments)}")
        if total_available_duration > 0:
            utilization = (used_unique_duration / total_available_duration) * 100
            print(f"   Utilization Ratio: {utilization:.1f}%")
            if utilization < 10:
                print(f"   [INFO] Note: Low utilization suggests clips may not match reference vibes well")

    # 13. ADVISOR STRATEGIC CRITIQUE (v11.0: Director's Cut)
    if advisor:
        print(f"\n{'='*80}")
        print("[INFO] POST-EDIT CREATIVE REVIEW (ADVISOR CRITIQUE)")
        print(f"{'='*80}")
        
        # A. Library Alignment (The Debrief)
        alignment = advisor.library_alignment
        if alignment:
            print(f"\n[PROMPT] THE EDITORIAL DEBRIEF:")
            if hasattr(alignment, 'strengths') and alignment.strengths:
                print(f"   [OK] STRENGTHS:")
                for s in alignment.strengths: print(f"      - {s}")
            
            if hasattr(alignment, 'editorial_tradeoffs') and alignment.editorial_tradeoffs:
                print(f"\n   [WARN] EDITORIAL TRADEOFFS:")
                for t in alignment.editorial_tradeoffs: print(f"      - {t}")
            
            if hasattr(alignment, 'constraint_gaps') and alignment.constraint_gaps:
                print(f"\n   [CHECK] CONSTRAINT GAPS:")
                for g in alignment.constraint_gaps: print(f"      - {g}")
        
        # B. Overall Strategy
        print(f"\n[AI] EDITORIAL STRATEGY:")
        print(f"   {advisor.editorial_strategy}")

        # C. Remake Strategy (The Forward-Looking Advice)
        if hasattr(advisor, 'remake_strategy') and advisor.remake_strategy:
            print(f"\n[REMAKE] REMAKE STRATEGY (HOW TO REACH DIRECTOR'S CUT):")
            print(f"   {advisor.remake_strategy}")
        
        print(f"\n{'='*80}\n")


def _validate_inputs(reference_path: Optional[str], clip_paths: List[str]) -> None:
    """
    Validate inputs before pipeline execution.
    
    Raises:
        ValueError: If inputs are invalid
    """
    
    # Check reference video exists (only if no text prompt)
    if reference_path:
        if not Path(reference_path).exists():
            raise ValueError(f"Reference video not found: {reference_path}")
        
        # Check reference duration (3-20 seconds)
        try:
            ref_duration = get_video_duration(reference_path)
            if not (3.0 <= ref_duration <= 60.0):
                raise ValueError(
                    f"Reference video must be 3-60 seconds (got {ref_duration:.1f}s)"
                )
        except Exception as e:
            raise ValueError(f"Could not read reference video: {e}")
    
    # Check clip count (minimum 2)
    if len(clip_paths) < 2:
        raise ValueError(f"Need at least 2 clips (got {len(clip_paths)})")
    
    # Check all clips exist
    for i, clip_path in enumerate(clip_paths, start=1):
        if not Path(clip_path).exists():
            raise ValueError(f"Clip {i} not found: {clip_path}")
        
        # Basic validation
        try:
            get_video_duration(clip_path)
        except Exception as e:
            raise ValueError(f"Could not read clip {i}: {e}")


