"""
Quick script to re-standardize clips with new Intel QSV + uniform cinematic settings.
Skips AI analysis - clips are already cached. Just re-encodes video.
"""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from engine.processors import standardize_clip, get_video_info
from utils import get_file_hash, ensure_directory


def main():
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"
    clips_dir = data_dir / "samples" / "clips"
    cache_dir = data_dir / "cache" / "standardized"
    
    ensure_directory(cache_dir)
    
    if not clips_dir.exists():
        print(f"ERROR: Clips directory not found: {clips_dir}")
        return
    
    clip_files = sorted(clips_dir.glob("*.mp4"))
    
    if not clip_files:
        print(f"ERROR: No MP4 files found in {clips_dir}")
        return
    
    print(f"\n{'='*60}")
    print(f"STANDARDIZING {len(clip_files)} CLIPS")
    print(f"{'='*60}")
    print("Settings: Intel QSV (GPU), Cinematic Preserve, High Quality")
    print(f"Cache: {cache_dir}\n")
    
    def process_clip(clip_path):
        p = Path(clip_path)
        
        # Get hash for cache key
        try:
            h = get_file_hash(p)
        except Exception as e:
            print(f"  [ERROR] Failed to hash {p.name}: {e}")
            return False
            
        cached_path = cache_dir / f"std_{h}.mp4"
        
        # Always re-standardize - delete old cache
        if cached_path.exists():
            cached_path.unlink()
            print(f"  [DEL] Removing old cache: {p.name}")
        
        print(f"  [RUN] Standardizing: {p.name}...")
        
        try:
            # Get clip info for logging
            info = get_video_info(str(p))
            streams = info.get("streams", [{}])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), streams[0])
            width = video_stream.get("width", 0)
            height = video_stream.get("height", 0)
            print(f"        Source: {width}x{height}")
            
            # Standardize with new settings (energy=None since we removed energy-based logic)
            standardize_clip(str(p), str(cached_path), energy=None, is_reference=False)
            
            # Verify output
            if cached_path.exists() and cached_path.stat().st_size > 100000:  # >100KB
                print(f"  [OK] Done: {cached_path.name}")
                return True
            else:
                print(f"  [ERROR] Output file missing or too small: {p.name}")
                return False
                
        except Exception as e:
            print(f"  [ERROR] Failed to standardize {p.name}: {e}")
            return False
    
    # Process in parallel (3 workers for Intel QSV encoder sessions)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(process_clip, clip_files))
    
    success_count = sum(1 for r in results if r)
    
    print(f"\n{'='*60}")
    print(f"DONE: {success_count}/{len(clip_files)} clips standardized")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
