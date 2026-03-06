import json
import hashlib
from pathlib import Path
from models import PipelineResult, DirectorCritique
from engine.reflector import generate_vault_report

def generate_single_vault_artifact(filename: str):
    """
    Generates Vault artifacts for a single results file.
    """
    BASE_DIR = Path(__file__).resolve().parent.parent
    RESULTS_DIR = BASE_DIR / "data" / "results"
    VAULT_DIR = BASE_DIR / "data" / "cache" / "vault"
    
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    
    rf = RESULTS_DIR / filename
    if not rf.exists():
        print(f"File not found: {rf}")
        return

    # Placeholder for legacy critique
    critique_placeholder = DirectorCritique(
        overall_score=8.0,
        monologue="Legacy reflector archived. See Vault report.",
        technical_fidelity="System active."
    )

    try:
        data = json.loads(rf.read_text(encoding='utf-8'))
        result = PipelineResult.model_validate(data)
        
        if not result.success or not result.blueprint or not result.edl or not result.advisor:
            print(f"Result file {filename} is missing required data for Vault generation.")
            return
        
        edl_hash = hashlib.md5(result.edl.model_dump_json().encode()).hexdigest()
        print(f"Processing edit {edl_hash} ({rf.name})...")
        
        # Generate the report
        report = generate_vault_report(
            result.blueprint,
            result.edl,
            result.advisor,
            critique_placeholder,
            cache_dir=VAULT_DIR,
            force_refresh=True
        )
        
        # Save the updated result back (optional, but good for verification)
        result.vault_report = report
        result.critique = critique_placeholder
        # We'll write to a NEW file to avoid overwriting the original during inspection
        inspection_file = RESULTS_DIR / f"inspect_{filename}"
        inspection_file.write_text(result.model_dump_json(indent=2), encoding='utf-8')
        
        print(f"\n[SUCCESS] Generated Vault artifacts for {filename}")
        print(f"Reasoning: data/cache/vault/reasoning_{edl_hash}.json")
        print(f"Report: data/cache/vault/vault_{edl_hash}.json")
        print(f"Full Result (with report): data/results/inspect_{filename}")
        
    except Exception as e:
        print(f"  [ERROR] Failed to process {filename}: {e}")

if __name__ == "__main__":
    # Using ref6_sess_043a6eb_v1.json as the reference as requested
    generate_single_vault_artifact("ref6_sess_043a6eb_v1.json")
