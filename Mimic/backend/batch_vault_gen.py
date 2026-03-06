import json
import hashlib
from pathlib import Path
from models import PipelineResult, DirectorCritique
from engine.reflector import generate_vault_report

def batch_generate_vault_artifacts():
    """
    Iterates over all existing cached edits and generates Vault artifacts.
    Treats the Vault pipeline as the ONLY explanation system.
    """
    BASE_DIR = Path(__file__).resolve().parent.parent
    RESULTS_DIR = BASE_DIR / "data" / "results"
    VAULT_DIR = BASE_DIR / "data" / "cache" / "vault"
    
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    
    if not RESULTS_DIR.exists():
        print(f"Results directory not found: {RESULTS_DIR}")
        return

    result_files = list(RESULTS_DIR.glob("*.json"))
    print(f"Found {len(result_files)} result files to process...")

    # Placeholder for legacy critique since compiler expects it
    critique_placeholder = DirectorCritique(
        overall_score=8.0,
        monologue="Legacy reflector archived. See Vault report.",
        technical_fidelity="System active."
    )

    for rf in result_files:
        try:
            data = json.loads(rf.read_text(encoding='utf-8'))
            result = PipelineResult.model_validate(data)
            
            if not result.success or not result.blueprint or not result.edl or not result.advisor:
                continue
            
            edl_hash = hashlib.md5(result.edl.model_dump_json().encode()).hexdigest()
            print(f"Processing edit {edl_hash} ({rf.name})...")
            
            # FORCE REFRESH to apply new strict rules
            report = generate_vault_report(
                result.blueprint,
                result.edl,
                result.advisor,
                critique_placeholder,
                cache_dir=VAULT_DIR,
                force_refresh=True
            )
            
            result.vault_report = report
            result.critique = critique_placeholder
            rf.write_text(result.model_dump_json(indent=2), encoding='utf-8')
            
            print(f"Generated Vault report for edit {edl_hash}")
            
        except Exception as e:
            print(f"  [ERROR] Failed to process {rf.name}: {e}")

if __name__ == "__main__":
    batch_generate_vault_artifacts()
