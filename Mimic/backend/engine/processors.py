"""
Processor module: FFmpeg wrappers for video manipulation.

All functions here are PURE: they take input paths, produce output files,
and have no side effects. They do NOT manage state or session data.
"""

import subprocess
import json
from pathlib import Path
from typing import List, Tuple, Optional

# ============================================================================
# VIDEO INFORMATION
# ============================================================================

def get_video_duration(video_path: str) -> float:
    """
    Get video duration using ffprobe.
    
    Args:
        video_path: Path to video file
    
    Returns:
        Duration in seconds
    
    Raises:
        RuntimeError: If ffprobe fails
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        raise RuntimeError(f"Failed to get duration for {video_path}: {e}")


def get_video_info(video_path: str) -> dict:
    """
    Get comprehensive video metadata.
    
    Returns:
        Dictionary with width, height, fps, duration, codec, etc.
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name,duration",
        "-show_entries", "format=duration",
        "-of", "json",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except Exception as e:
        raise RuntimeError(f"Failed to get info for {video_path}: {e}")


def has_audio(video_path: str) -> bool:
    """
    Check if video has an audio track.
    
    Args:
        video_path: Path to video file
    
    Returns:
        True if video has audio, False otherwise
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return "audio" in result.stdout.lower()
    except Exception:
        return False


def get_beat_grid(duration: float, bpm: int = 120) -> List[float]:
    """
    Generate beat timestamps assuming fixed BPM.

    This creates a "beat grid" for aligning cuts to music, even without
    real beat detection. Works well for most electronic/pop music.

    Args:
        duration: Total video duration in seconds
        bpm: Beats per minute (default 120 = common pop/electronic tempo)

    Returns:
        List of beat timestamps in seconds [0.0, 0.5, 1.0, 1.5, ...]

    Examples:
        120 BPM = 0.5s per beat (2 beats/second)
        140 BPM = 0.428s per beat
        100 BPM = 0.6s per beat
    """
    # Guardrail: avoid division by zero / nonsense BPMs
    if bpm is None or bpm <= 0:
        return []
    beat_interval = 60.0 / bpm
    timestamps = []
    t = 0.0

    while t < duration:
        timestamps.append(t)
        t += beat_interval

    return timestamps


def align_to_nearest_beat(time: float, beat_grid: List[float], tolerance: float = 0.15) -> float:
    """
    Snap a time value to the nearest beat on the grid.
    
    Args:
        time: Original time in seconds
        beat_grid: List of beat timestamps from get_beat_grid()
        tolerance: Maximum distance to snap (default 0.15s)
    
    Returns:
        Nearest beat timestamp, or original time if no beat is close enough
    
    Example:
        align_to_nearest_beat(1.23, [0.0, 0.5, 1.0, 1.5]) → 1.0
        align_to_nearest_beat(0.75, [0.0, 0.5, 1.0, 1.5]) → 0.5
    """
    if not beat_grid:
        return time
    
    # Find nearest beat
    nearest_beat = min(beat_grid, key=lambda t: abs(t - time))
    
    # Only snap if within tolerance
    if abs(nearest_beat - time) <= tolerance:
        return nearest_beat
    
    return time


def remove_audio(input_path: str, output_path: str) -> str:
    """
    Remove audio track from video (bypass recitation blocks).
    Uses stream copying for speed.
    """
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-an",  # No audio
        "-vcodec", "copy",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except Exception as e:
        raise RuntimeError(f"Failed to remove audio: {e}")


def analyze_music(audio_path: str) -> dict:
    """
    Full music intelligence analysis in a single librosa pass.

    Extracts everything the editor needs to make musically-grounded decisions:
    - BPM (tempo)
    - Onset timestamps (real musical hit points - snare, bass, lyric emphasis)
    - Normalized energy curve (loudness per second, 0.0–1.0)

    This replaces detect_bpm() for the PROMPT MODE pipeline.
    detect_bpm() is kept as a thin wrapper for backwards compatibility.

    Args:
        audio_path: Path to WAV audio file

    Returns:
        dict with keys: bpm, onset_times, energy_curve
        - bpm: float (beats per minute)
        - onset_times: List[float] (timestamps in seconds of strong musical hits)
        - energy_curve: List[float] (normalized RMS energy, one value per second)
    """
    import scipy.signal

    # P1 BUGFIX: Scipy 1.9.0+ moved hann to windows.hann
    if not hasattr(scipy.signal, 'hann'):
        import scipy.signal.windows
        scipy.signal.hann = scipy.signal.windows.hann
        print("  [FIX] Patched scipy.signal.hann for librosa compatibility.")

    try:
        import librosa
        import numpy as np

        print(f"  [MUSIC] Analyzing: {Path(audio_path).name}...")
        y, sr = librosa.load(audio_path)

        # === 1. BPM ===
        tempo_result = librosa.beat.beat_track(y=y, sr=sr)
        tempo = tempo_result[0] if isinstance(tempo_result, tuple) else tempo_result
        if hasattr(tempo, "__len__"):
            tempo = float(tempo[0])
        else:
            tempo = float(tempo)
        if not (30 < tempo < 300):
            tempo = 120.0
        print(f"  [OK] BPM: {tempo:.2f}")

        # === 2. ONSET DETECTION (real musical hit points) ===
        # These are the actual moments a real editor would cut on:
        # snare cracks, bass hits, lyric emphasis, instrumental accents
        onset_frames = librosa.onset.onset_detect(
            y=y, sr=sr,
            units="frames",
            delta=0.07,       # sensitivity: lower = more onsets detected
            wait=3            # minimum frames between onsets (~0.07s at 22kHz)
        )
        onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()

        # Filter to only keep onsets that are musically significant
        # (Onset strength above median — removes noise, keeps real hits)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_env_frames = onset_env[onset_frames] if len(onset_frames) > 0 else np.array([])
        if len(onset_env_frames) > 0:
            median_strength = float(np.median(onset_env_frames))
            strong_mask = onset_env_frames >= (median_strength * 0.85)
            onset_times = [t for t, keep in zip(onset_times, strong_mask) if keep]

        print(f"  [OK] Found {len(onset_times)} musical onsets")

        # === 3. ENERGY CURVE (normalized loudness per second) ===
        # This tells us where the music is quiet vs. loud:
        # quiet intro → longer clip holds | loud peak → faster cuts
        hop_length = 512
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        # Convert frame-level RMS to per-second values
        frames_per_second = sr / hop_length
        total_seconds = int(len(y) / sr)
        energy_curve = []
        for sec in range(total_seconds):
            start_f = int(sec * frames_per_second)
            end_f = int((sec + 1) * frames_per_second)
            chunk = rms[start_f:end_f]
            energy_curve.append(float(np.mean(chunk)) if len(chunk) > 0 else 0.0)

        # Normalize 0→1 (avoid division by zero)
        max_e = max(energy_curve) if energy_curve else 1.0
        if max_e > 0:
            energy_curve = [e / max_e for e in energy_curve]

        print(f"  [OK] Energy curve: {len(energy_curve)}s, peak at {energy_curve.index(max(energy_curve))}s")

        return {
            "bpm": tempo,
            "onset_times": onset_times,
            "energy_curve": energy_curve,
        }

    except Exception as e:
        print(f"  [WARN] Music analysis failed: {e}. Using defaults.")
        return {
            "bpm": 120.0,
            "onset_times": [],
            "energy_curve": [],
        }


def detect_bpm(audio_path: str) -> float:
    """
    Thin wrapper around analyze_music() for backwards compatibility.
    Prefer analyze_music() for new code — it does one pass and returns everything.
    """
    return analyze_music(audio_path)["bpm"]


def extract_audio_wav(video_path: str, wav_output_path: str) -> bool:
    """
    Extract audio from video to a WAV file for BPM analysis.

    Args:
        video_path: Source video path
        wav_output_path: Output WAV file path

    Returns:
        True if extraction succeeded, False if failed/no audio
    """
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        "-y",
        wav_output_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="ignore") if isinstance(e.stderr, (bytes, bytearray)) else (e.stderr or "")
        if "does not contain any stream" in stderr or "no audio" in stderr.lower():
            return False
        print(f"  [WARN] WAV audio extraction failed: {stderr}")
        return False


# ============================================================================
# VIDEO STANDARDIZATION
# ============================================================================

def standardize_clip(input_path: str, output_path: str, energy: Optional["EnergyLevel"] = None, is_reference: bool = False) -> None:
    """
    Standardize video to 1080x1920 (vertical), 30fps, h.264, AAC audio.

    Single geometry path: scale to fit inside 1080x1920, pad with black (letterbox).
    No adaptive crop. Preserves full frame, deterministic, social-ready.

    Args:
        input_path: Source video file
        output_path: Destination for standardized video
        energy: DEPRECATED - no longer used for geometry decisions
        is_reference: If True, forces precision CPU encoding (libx264) for blueprint accuracy.
    """
    mode = "premium_nostalgia_letterbox"
    geometry_filters = "scale=1080:1920:flags=lanczos:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,hqdn3d=1.5:1.5:6:6,unsharp=3:3:0.5:3:3:0.5"
    
    print(f"  [GEOMETRY] Mode: {mode} (clean + sharp + preserve context)")


    def run_ffmpeg(encoder: str):
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-vf", (
                f"{geometry_filters},"
                "fps=30,"                           # Force consistent 30fps
                "format=yuv420p,"                   # Ensure maximal compatibility
                "setsar=1"
            ),
            "-c:v", encoder,
            "-vsync", "cfr",                     # Sync Lock: Ensure grid-aligned source (v14.7)
            "-preset", "slow" if encoder == "h264_qsv" else "veryfast",
            "-c:a", "aac",
            "-b:a", "256k",
            "-ar", "48000",
            "-map_metadata", "-1",
            "-metadata:s:v:0", "rotate=0", 
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            "-y",
            output_path
        ]

        if encoder == "h264_qsv":
            # Quality setting for QSV
            cmd.insert(-1, "-global_quality")
            cmd.insert(-1, "20")
        else:
            # Quality setting for libx264
            cmd.insert(-1, "-crf")
            cmd.insert(-1, "23")

        return subprocess.run(cmd, capture_output=True, text=True, check=True)

    try:
        # P1 SAFEGUARD: Skip QSV for reference videos to ensure absolute timestamp precision
        if is_reference:
            print(f"  [GEOMETRY] Reference Mode detected: forcing libx264 for narrative precision...")
            run_ffmpeg("libx264")
            print(f"  [OK] Standardized (Precision CPU, {mode}): {Path(output_path).name}")
        else:
            # Try hardware acceleration first (Intel QSV)
            print(f"  [GEOMETRY] Standardizing with Intel QSV (GPU acceleration)...")
            run_ffmpeg("h264_qsv")
            print(f"  [OK] Standardized (QSV, {mode}): {Path(output_path).name}")
    except Exception as e:
        if not is_reference:
            print(f"  [WARN] Intel QSV failed or unavailable. Falling back to libx264 (Software CPU)...")
        try:
            # Fallback to software encoding (libx264) - universal
            run_ffmpeg("libx264")
            print(f"  [OK] Standardized (libx264, {mode}): {Path(output_path).name}")
        except subprocess.CalledProcessError as e2:
            raise RuntimeError(
                f"FFmpeg standardization failed totally:\n"
                f"STDOUT: {e2.stdout}\n"
                f"STDERR: {e2.stderr}"
            )



# ============================================================================
# AUDIO EXTRACTION
# ============================================================================

def extract_audio(video_path: str, audio_output_path: str) -> bool:
    """
    Extract audio track from video.
    
    Args:
        video_path: Source video
        audio_output_path: Destination for audio file (should end in .aac)
    
    Returns:
        True if audio extracted successfully, False if video has no audio
    
    Raises:
        RuntimeError: If FFmpeg fails unexpectedly
    """
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # No video
        "-acodec", "aac",
        "-b:a", "192k",
        "-y",
        audio_output_path
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print(f"  [OK] Audio extracted: {Path(audio_output_path).name}")
        return True
    except subprocess.CalledProcessError as e:
        # Check if it's a "no audio stream" error
        if "does not contain any stream" in e.stderr or "no audio" in e.stderr.lower():
            print(f"  [WARN] No audio track found in {Path(video_path).name}")
            return False
        else:
            raise RuntimeError(f"Audio extraction failed: {e.stderr}")


# ============================================================================
# VIDEO SEGMENTATION
# ============================================================================

EXTRACT_FPS = 30.0


def extract_segment(
    input_path: str,
    output_path: str,
    start_time: float,
    duration: float,
    hold_last_frame_seconds: Optional[float] = None
) -> None:
    """
    Extract a segment from a video (precise frame-accurate cutting).
    If hold_last_frame_seconds is set, output duration = duration + hold_last_frame_seconds
    by holding the last frame (demo fill so timeline matches blueprint).
    """
    n_frames = max(1, round(duration * EXTRACT_FPS))
    exact_duration = n_frames / EXTRACT_FPS
    out_duration = exact_duration
    vf = "setpts=PTS-STARTPTS,fps=30"
    if hold_last_frame_seconds and hold_last_frame_seconds > 0.01:
        hold_frames = max(1, round(hold_last_frame_seconds * EXTRACT_FPS))
        hold_duration = hold_frames / EXTRACT_FPS
        out_duration = exact_duration + hold_duration
        vf = f"setpts=PTS-STARTPTS,fps=30,tpad=stop_mode=clone:stop_duration={hold_duration:.6f}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ss", f"{start_time:.4f}",
        "-t", f"{exact_duration:.6f}",
        "-vf", vf,
        "-af", "asetpts=PTS-STARTPTS",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-vsync", "cfr",
        "-avoid_negative_ts", "make_zero",
        "-t", f"{out_duration:.6f}",
        output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"    [OK] Segment extracted: {start_time:.2f}s + {exact_duration:.2f}s" + (f" + {hold_last_frame_seconds:.2f}s hold" if hold_last_frame_seconds else "") + f" -> {out_duration:.2f}s")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Segment extraction failed: {e.stderr}")


# ============================================================================
# ADVANCED DIAGNOSTICS (NEW)
# ============================================================================

def detect_scene_changes(video_path: str, threshold: float = 0.3) -> List[float]:
    """
    Use FFmpeg visual analysis to find ACTUAL cut points in a video.
    
    Returns:
        List of timestamps (seconds) where a scene change was detected.
    """
    print(f"  [DIAGNOSTIC] Detecting visual scene changes (threshold={threshold})...")
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-"
    ]
    
    try:
        # Scene detection info goes to stderr
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stderr
        
        timestamps = []
        import re
        # Look for 'pts_time:9.833333' pattern
        matches = re.findall(r"pts_time:([\d\.]+)", output)
        for m in matches:
            ts = float(m)
            # Clamp to >= 0.1s to avoid issues with start of video
            if ts >= 0.1 and ts not in timestamps:
                timestamps.append(ts)
        
        # Sort and filter close timestamps
        timestamps.sort()
        final_ts = []
        if timestamps:
            final_ts.append(timestamps[0])
            for i in range(1, len(timestamps)):
                # CRITICAL: Lowered from 0.3s to 0.15s to capture fast-paced edits
                # Music videos and reels often have cuts every 0.2-0.3s
                if timestamps[i] - final_ts[-1] > 0.15:
                    final_ts.append(timestamps[i])
        
        print(f"  [OK] Detected {len(final_ts)} visual cuts.")
        return final_ts
    except Exception as e:
        print(f"  [WARN] Scene detection failed: {e}")
        return []

# ============================================================================
# VIDEO CONCATENATION
# ============================================================================

def concatenate_videos(input_paths: List[str], output_path: str) -> None:
    """
    Concatenate multiple videos into a single file.
    
    CRITICAL: Uses re-encoding (not stream copy) to ensure frame-perfect cuts.
    Stream copy only cuts on keyframes (2-5s apart), causing sync drift.
    
    Args:
        input_paths: List of video files to join (in order)
        output_path: Destination for concatenated video
    
    Raises:
        RuntimeError: If concatenation fails
    """
    # Create a temporary file list for FFmpeg
    concat_list_path = Path(output_path).parent / "concat_list.txt"
    
    with open(concat_list_path, "w") as f:
        for path in input_paths:
            # FFmpeg concat requires absolute paths and "file" prefix
            f.write(f"file '{Path(path).absolute()}'\n")
    
    cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_path),
        "-filter:v", "fps=30", # Sync Lock: Force output frame rate via filter (v14.7.2)
        "-c:v", "libx264",     # Re-encode video for frame-perfect cuts
        "-preset", "ultrafast", 
        "-crf", "23", 
        "-c:a", "aac",         # Re-encode audio to avoid clicks/metadata gaps (v14.7.2)
        "-b:a", "192k",
        "-vsync", "cfr",       # Sync Lock: Force constant frame rate (v14.7.2)
        "-y",
        output_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"  [OK] Concatenated {len(input_paths)} segments (frame-perfect)")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Concatenation failed: {e.stderr}")
    finally:
        # Clean up temp file
        if concat_list_path.exists():
            concat_list_path.unlink()


# ============================================================================
# AUDIO/VIDEO MERGING
# ============================================================================

def merge_audio_video(
    video_path: str,
    audio_path: str,
    output_path: str
) -> None:
    """
    Merge audio track onto video.
    
    P1 SAFEGUARD (v12.6): Video duration is AUTHORITATIVE.
    If audio < video, audio is padded with silence to match video duration.
    This enforces the invariant: "Video timing is sacred, audio adapts."
    
    OPTIMIZED: Video stream is copied (already encoded), only audio is re-encoded.
    This prevents double-encoding quality loss and speeds up rendering.
    
    Args:
        video_path: Video file (can be silent)
        audio_path: Audio file to overlay
        output_path: Destination for merged video
    """
    # P1 SAFEGUARD: Detect durations and pad/trim audio to match video exactly
    try:
        video_duration = get_video_duration(video_path)
    except Exception as e:
        print(f"  [WARN] Could not detect video duration, proceeding without padding/trim: {e}")
        video_duration = None
    
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",  # Don't re-encode video (already encoded in concat step)
    ]

    if video_duration is not None:
        # Make the audio track exactly match the video duration.
        # This avoids "silent tail" issues caused by AAC duration metadata drift.
        cmd.extend([
            "-filter_complex",
            f"[1:a]apad,atrim=0:{video_duration:.4f},asetpts=N/SR/TB[a]",
            "-map", "0:v:0",
            "-map", "[a]",
            "-c:a", "aac",
            "-b:a", "192k",
        ])
    else:
        cmd.extend([
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:a", "aac",
            "-b:a", "192k",
        ])
    
    # CRITICAL: Never use -shortest (video timing is sacred)
    # trim_to_shortest parameter is ignored for safety
    
    cmd.extend(["-y", output_path])
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"  [OK] Audio merged onto video (optimized)")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Audio/video merge failed: {e.stderr}")


# ============================================================================
# SILENT VIDEO (When reference has no audio)
# ============================================================================

def create_silent_video(input_path: str, output_path: str) -> None:
    """
    Create a copy of video with no audio track.
    
    Args:
        input_path: Source video
        output_path: Destination for silent video
    """
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "copy",
        "-an",  # No audio
        "-y",
        output_path
    ]
    
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"  [OK] Silent video created")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Silent video creation failed: {e.stderr}")


# ============================================================================
# THUMBNAIL GENERATION (NEW)
# ============================================================================

def generate_thumbnail(video_path: str, thumbnail_path: str, time: float = 2.0) -> bool:
    """
    Extract a single frame from video to use as thumbnail.
    Optimized: calls ffprobe once.
    """
    Path(thumbnail_path).parent.mkdir(parents=True, exist_ok=True)
    
    try:
        duration = get_video_duration(video_path)
    except Exception:
        duration = 0

    # Try multiple offsets: 2.0s, 5.0s, 0.5s, 0.0s
    for offset in [time, 5.0, 0.5, 0.0]:
        if duration > 0 and offset > duration:
            continue
            
        cmd = [
            "ffmpeg", "-v", "error",
            "-ss", str(offset),
            "-i", video_path,
            "-frames:v", "1",
            "-q:v", "4",
            "-y",
            thumbnail_path
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            if Path(thumbnail_path).exists() and Path(thumbnail_path).stat().st_size > 2000:
                return True
        except Exception:
            continue
            
    return False


def convert_to_mp4(input_path: str, output_path: str) -> None:
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        "-y",
        output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        stderr = e.stderr or "Unknown FFmpeg error"
        raise RuntimeError(f"MP4 conversion failed: {stderr}")


# ============================================================================
# VALIDATION
# ============================================================================

def validate_output(output_path: str, min_size_kb: int = 100) -> bool:
    """
    Validate that output video was created successfully.
    
    Args:
        output_path: Path to output video
        min_size_kb: Minimum file size in KB (to catch empty files)
    
    Returns:
        True if valid, False otherwise
    """
    path = Path(output_path)
    
    if not path.exists():
        return False
    
    size_kb = path.stat().st_size / 1024
    if size_kb < min_size_kb:
        return False
    
    # Try to probe the file
    try:
        get_video_duration(output_path)
        return True
    except:
        return False

