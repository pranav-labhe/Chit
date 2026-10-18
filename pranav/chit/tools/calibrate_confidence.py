"""Isotonic Regression confidence calibrator using standard library only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def fit_isotonic_regression(x: list[float], y: list[float]) -> list[tuple[float, float]]:
    """Fit isotonic regression using the Pool Adjacent Violators Algorithm (PAVA).

    Returns a list of (x_threshold, calibrated_prob) monotonically increasing pairs.
    """
    if not x or not y or len(x) != len(y):
        return [(0.0, 0.0), (1.0, 1.0)]

    # 1. Sort by x
    paired = sorted(zip(x, y), key=lambda item: item[0])

    # 2. PAVA
    # Each block is [weight, sum_y, min_x, max_x]
    blocks: list[dict] = []
    for xi, yi in paired:
        blocks.append({"w": 1.0, "sum_y": float(yi), "min_x": float(xi), "max_x": float(xi)})
        while len(blocks) >= 2:
            prev = blocks[-2]
            curr = blocks[-1]
            prev_val = prev["sum_y"] / prev["w"]
            curr_val = curr["sum_y"] / curr["w"]
            if prev_val > curr_val:
                # Merge curr into prev (violation of monotonicity)
                prev["w"] += curr["w"]
                prev["sum_y"] += curr["sum_y"]
                prev["max_x"] = curr["max_x"]
                blocks.pop()
            else:
                break

    mapping: list[tuple[float, float]] = []
    # Anchor at 0.0
    mapping.append((0.0, max(0.0, min(1.0, blocks[0]["sum_y"] / blocks[0]["w"]))))
    for b in blocks:
        val = max(0.0, min(1.0, b["sum_y"] / b["w"]))
        mapping.append((round(b["max_x"], 4), round(val, 4)))
    # Anchor at 1.0: preserve monotonicity up to high-confidence exact matches
    top_val = mapping[-1][1]
    if any(yi >= 1.0 for yi in y) and top_val < 0.85:
        if mapping[-1][0] >= 1.0:
            mapping[-1] = (0.99, top_val)
        mapping.append((1.0, round(max(top_val, 0.85), 4)))
    else:
        mapping.append((1.0, top_val))

    # Deduplicate and sort
    seen_x = set()
    cleaned = []
    for x_val, y_val in sorted(mapping, key=lambda item: item[0]):
        if x_val not in seen_x:
            cleaned.append((x_val, y_val))
            seen_x.add(x_val)

    return cleaned


def calibrate(raw_conf: float, mapping: list[dict[str, float]] | list[tuple[float, float]] | None) -> float:
    """Map raw confidence to calibrated confidence via piecewise linear interpolation."""
    if not mapping:
        return raw_conf

    # Convert mapping to list of tuples if needed
    points: list[tuple[float, float]] = []
    for pt in mapping:
        if isinstance(pt, dict):
            points.append((float(pt["raw"]), float(pt["calibrated"])))
        else:
            points.append((float(pt[0]), float(pt[1])))

    if not points:
        return raw_conf

    x_val = max(0.0, min(1.0, float(raw_conf)))
    if x_val <= points[0][0]:
        return points[0][1]
    if x_val >= points[-1][0]:
        return points[-1][1]

    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        if x1 <= x_val <= x2:
            if x2 == x1:
                return y1
            slope = (y2 - y1) / (x2 - x1)
            return round(y1 + slope * (x_val - x1), 4)

    return raw_conf


def train_calibration_from_eval(eval_file: Path | str, output_file: Path | str) -> Path:
    eval_p = Path(eval_file)
    out_p = Path(output_file)
    data = json.loads(eval_p.read_text(encoding="utf-8"))
    details = data.get("details", [])

    confidences = []
    accuracies = []
    for item in details:
        if "confidence" in item and "is_correct" in item:
            raw_c = float(item.get("raw_confidence", item["confidence"]))
            if item.get("source") == "tool" and item["is_correct"]:
                raw_c = 1.0
            confidences.append(raw_c)
            accuracies.append(1.0 if item["is_correct"] else 0.0)

    mapping_pairs = fit_isotonic_regression(confidences, accuracies)
    mapping_dicts = [{"raw": pt[0], "calibrated": pt[1]} for pt in mapping_pairs]

    payload = {
        "version": 1,
        "sample_count": len(confidences),
        "mapping": mapping_dicts,
    }
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Calibration table with {len(mapping_dicts)} points saved to {out_p}")
    return out_p


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate model confidence with Isotonic Regression.")
    parser.add_argument("-e", "--eval", "--eval-file", dest="eval_file", type=Path, default=Path("docs/benchmarks/bridge-baseline-phase0.json"), help="Path to evaluation JSON")
    parser.add_argument("-o", "--output", type=Path, default=Path("data/calibration.json"), help="Path to output calibration JSON")
    args = parser.parse_args()

    train_calibration_from_eval(args.eval_file, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
