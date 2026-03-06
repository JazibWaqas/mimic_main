import subprocess
import json
from pathlib import Path

def get_duration(video_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])

base_dir = Path(__file__).parent.parent

ref_path = base_dir / "data" / "samples" / "reference" / "refrence_vid.mp4"
if ref_path.exists():
    duration = get_duration(ref_path)
    print(f"Reference video duration: {duration:.2f} seconds")

clips_dir = base_dir / "data" / "samples" / "clips"
if clips_dir.exists():
    print("\nClip durations:")
    for clip_file in sorted(clips_dir.glob("*.mp4")):
        try:
            dur = get_duration(clip_file)
            print(f"  {clip_file.name}: {dur:.2f}s")
        except:
            print(f"  {clip_file.name}: ERROR")
