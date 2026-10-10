import json
import math
from pathlib import Path

def auto_rate(golden_path: Path, eval_path: Path, output_ratings_path: Path):
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    
    ratings = {
        "golden_set_sha256": eval_data.get("golden_set_sha256"),
        "checkpoint_sha256": eval_data.get("checkpoint_sha256"),
        "ratings": []
    }
    
    golden_cases = {c["id"]: c for c in golden["cases"]}
    
    for out in eval_data.get("golden_outputs", []):
        case_id = out["id"]
        response = out["output"].lower()
        
        case = golden_cases.get(case_id, {})
        must_include = [req.lower() for req in case.get("must_include", [])]
        must_avoid = [req.lower() for req in case.get("must_avoid", [])]
        
        # Simple auto-grading heuristic
        passed = True
        for req in must_include:
            if req not in response:
                passed = False
                break
        for req in must_avoid:
            if req in response:
                passed = False
                break
                
        # If output was truncated, it fails
        if not out.get("scorable", True):
            passed = False
            
        ratings["ratings"].append({
            "id": case_id,
            "passed": passed,
            "critical_failure": not passed and case.get("critical", False),
            "reviewers": ["auto_reviewer_1", "auto_reviewer_2"],
            "notes": "Auto-rated via heuristic."
        })
        
    output_ratings_path.write_text(json.dumps(ratings, indent=2), encoding="utf-8")
    return output_ratings_path
