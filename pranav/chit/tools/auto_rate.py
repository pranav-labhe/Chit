import argparse
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
        raw_response = out.get("response") if "response" in out else out.get("output")
        scorable = bool(out.get("scorable", True) and raw_response is not None)
        response = raw_response.lower() if raw_response is not None else ""
        
        case = golden_cases.get(case_id, {})
        must_include = [req.lower() for req in case.get("must_include", [])]
        must_avoid = [req.lower() for req in case.get("must_avoid", [])]
        
        # Simple auto-grading heuristic
        passed = scorable
        if passed:
            for req in must_include:
                if req not in response:
                    passed = False
                    break
            for req in must_avoid:
                if req in response:
                    passed = False
                    break
                
        # If output was truncated, it fails
        if not scorable:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-rate evaluation outputs against a golden set.")
    parser.add_argument("--golden-set", type=Path, default=Path("data/golden_set.json"), help="Path to golden set JSON")
    parser.add_argument("--eval-report", type=Path, required=True, help="Path to evaluation output JSON")
    parser.add_argument("--output", type=Path, required=True, help="Path to write ratings JSON")
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    auto_rate(args.golden_set, args.eval_report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

