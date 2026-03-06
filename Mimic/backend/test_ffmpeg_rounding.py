import subprocess
import json
from pathlib import Path

def get_frame_count(video_path):
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_packets", "-show_entries", "stream=nb_read_packets",
        "-of", "csv=p=0", str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return int(result.stdout.strip())

def test_extraction(duration):
    # Absolute pathing for robustness
    base_dir = Path(__file__).resolve().parent.parent
    input_video = base_dir / "data" / "samples" / "reference" / "ref22.mp4"
    output_video = Path(__file__).resolve().parent / f"test_{duration}.mp4"
    
    cmd = [
        "ffmpeg", "-y", "-i", str(input_video),
        "-ss", "2.0000", "-t", str(duration),
        "-vf", "setpts=PTS-STARTPTS", "-af", "asetpts=PTS-STARTPTS",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k", "-vsync", "cfr",
        "-avoid_negative_ts", "make_zero",
        str(output_video)
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg failed for {duration}: {e.stderr}")
        return
    
    frames = get_frame_count(output_video)
    actual_duration = frames / 30.0
    print(f"Requested: {duration}s | Frames: {frames} | Actual Duration: {actual_duration:.6f}s | Diff: {actual_duration - duration:+.6f}s")
    output_video.unlink()

if __name__ == "__main__":
    print("Testing 30fps Frame Rounding Drift:")
    test_extraction(0.24)
    test_extraction(0.29)
    test_extraction(0.54)
    test_extraction(1.07)
