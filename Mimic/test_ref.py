import os
import sys
from pathlib import Path

# Add the backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from backend.engine.orchestrator import run_mimic_pipeline
from backend.models import PipelineResult

def run_test(ref_name: str, session_suffix: str = "master"):
    # 1. Setup paths
    BASE_DIR = Path(__file__).resolve().parent
    ref_path = str(BASE_DIR / "data" / "samples" / "reference" / ref_name)
    clips_dir = BASE_DIR / "data" / "samples" / "clips"
    output_dir = str(BASE_DIR / "data" / "results")
    
    # Check if reference exists
    if not os.path.exists(ref_path):
        print(f"❌ Error: Reference video not found at {ref_path}")
        return

    # Get all mp4 clips
    clip_paths = [str(p) for p in clips_dir.glob("*.mp4")]
    
    print("=" * 80)
    print(f"🚀 RUNNING MIMIC TEST: {ref_name.upper()}")
    print("=" * 80)
    print(f"📹 Reference: {ref_name}")
    print(f"📎 Clips count: {len(clip_paths)}")
    
    # 2. Run Pipeline
    # Use the naming convention that generated your existing results
    session_id = f"{ref_name.split('.')[0]}_{session_suffix}"
    
    result: PipelineResult = run_mimic_pipeline(
        reference_path=ref_path,
        clip_paths=clip_paths,
        session_id=session_id,
        output_dir=output_dir
    )
    
    if result.success:
        print("\n" + "=" * 80)
        print(f"🎉 SUCCESS! Video rendered to: {result.output_path}")
        print("=" * 80)
    else:
        print(f"\n❌ Pipeline failed: {result.error}")

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent
    ref_dir = BASE_DIR / "data" / "samples" / "reference"
    
    # Priority 1: Command line argument
    if len(sys.argv) > 1:
        ref_to_test = sys.argv[1]
    # Priority 2: Environment variable
    elif os.environ.get("TEST_REFERENCE"):
        ref_to_test = os.environ.get("TEST_REFERENCE")
    # Priority 3: Interactive Prompt
    else:
        available_refs = sorted([p.name for p in ref_dir.glob("*.mp4")])
        print("\n🎬 AVAILABLE REFERENCE VIDEOS:")
        print("-" * 30)
        for i, ref in enumerate(available_refs, 1):
            print(f"  {i:2d}. {ref}")
        print("-" * 30)
        
        choice = input("\n👉 Which reference would you like to run? (Name or Number): ").strip()
        
        if not choice:
            ref_to_test = "ref3.mp4"
            print(f"ℹ️ No choice made, using default: {ref_to_test}")
        elif choice.isdigit() and 1 <= int(choice) <= len(available_refs):
            ref_to_test = available_refs[int(choice) - 1]
        else:
            # Add .mp4 if they forgot it
            ref_to_test = choice if choice.endswith(".mp4") else f"{choice}.mp4"

    run_test(ref_to_test)

