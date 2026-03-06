"""
Pre-cache all clips: Parallel AI Analysis + Parallel FFmpeg Standardization.
Maximum speed: Phase 1 (Net/Gemini) and Phase 2 (GPU/FFmpeg) run simultaneously.
"""

import os
import shutil
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# MIMIC Imports
from engine.brain import analyze_all_clips
from engine.processors import standardize_clip
from utils import get_file_hash, ensure_directory, save_hash_registry
from models import EnergyLevel

load_dotenv()

def phase_ai(clip_paths):
    print(f"[PHASE 1] Starting AI Analysis (Network/Gemini)...")
    try:
        clip_index = analyze_all_clips(clip_paths)
        print(f"[OK] Phase 1: AI Analysis complete ({len(clip_index.clips)} clips).")
        return clip_index
    except Exception as e:
        print(f"[ERROR] Phase 1 failed: {e}")
        return None

def phase_standardize(clip_paths, standardized_cache):
    print(f"[PHASE 2] Starting Standardization (GPU/FFmpeg)...")
    
    def process_one(clip_path):
        p = Path(clip_path)
        h = get_file_hash(p)
        cached_path = standardized_cache / f"std_{h}.mp4"
        
        if cached_path.exists():
            return True
            
        temp_out = standardized_cache / f"tmp_{h}.mp4"
        try:
            # Note: energy is now ignored by processors.py logic, using MEDIUM as placeholder
            standardize_clip(str(p), str(temp_out), energy=EnergyLevel.MEDIUM)
            temp_out.rename(cached_path)
            return True
        except Exception as e:
            print(f"  [ERR] {p.name}: {e}")
            if temp_out.exists(): temp_out.unlink()
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(process_one, clip_paths))
    
    success_count = sum(1 for r in results if r)
    print(f"[OK] Phase 2: Standardization complete ({success_count}/{len(clip_paths)} clips).")
    return success_count

def main():
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"
    clips_dir = data_dir / "samples" / "clips"
    cache_dir = data_dir / "cache"
    standardized_cache = cache_dir / "standardized"
    
    ensure_directory(standardized_cache)
    
    clip_files = sorted(clips_dir.glob("*.mp4"))
    if not clip_files:
        print("ERROR: No clips found.")
        return
    
    clip_paths = [str(f) for f in clip_files]
    
    print(f"\n{'='*60}")
    print(f"ULTRA-FAST PARALLEL PRE-CACHE: {len(clip_files)} CLIPS")
    print(f"{'='*60}\n")

    # RUN PHASES IN PARALLEL
    with ThreadPoolExecutor(max_workers=2) as main_executor:
        future_ai = main_executor.submit(phase_ai, clip_paths)
        future_std = main_executor.submit(phase_standardize, clip_paths, standardized_cache)
        
        # Wait for both
        clip_index = future_ai.result()
        std_count = future_std.result()

    print(f"\n{'='*60}")
    print(f"FINAL STATUS")
    print(f"{'='*60}")
    print(f"AI Index: {len(clip_index.clips if clip_index else [])} clips total")
    print(f"Standardized: {std_count}/{len(clip_files)} files in cache")
    print(f"{'='*60}\n")
    
    save_hash_registry()

if __name__ == "__main__":
    main()
