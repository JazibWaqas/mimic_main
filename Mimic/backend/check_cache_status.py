from pathlib import Path
import hashlib
import json

def get_fast_hash(path: Path) -> str:
    file_size = path.stat().st_size
    hasher = hashlib.md5()
    try:
        with open(path, "rb") as f:
            if file_size < 128 * 1024:
                hasher.update(f.read())
            else:
                hasher.update(f.read(64 * 1024))
                f.seek(max(0, file_size - 64 * 1024))
                hasher.update(f.read(64 * 1024))
        hasher.update(str(file_size).encode())
        return hasher.hexdigest()
    except Exception:
        return hashlib.md5(path.name.encode()).hexdigest()

def check_cache():
    base_dir = Path(r"c:\Users\OMNIBOOK\Documents\GitHub\Mimic")
    clips_dir = base_dir / "data" / "samples" / "clips"
    cache_dir = base_dir / "data" / "cache" / "clips"
    
    clips = list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.MPG")) + list(clips_dir.glob("*.avi"))
    
    print(f"Total clips found: {len(clips)}")
    
    missing = []
    cached = 0
    
    for clip in clips:
        h = get_fast_hash(clip)
        cache_file = cache_dir / f"clip_comprehensive_{h}.json"
        
        if cache_file.exists():
            cached += 1
        else:
            missing.append(clip.name)
            
    print(f"Cached: {cached}")
    print(f"Missing: {len(missing)}")
    
    if missing:
        print("\nMissing Clips:")
        for m in sorted(missing):
            print(f"- {m}")

if __name__ == "__main__":
    check_cache()
