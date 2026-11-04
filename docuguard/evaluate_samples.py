"""Evaluate the 10 fictional BIAI documents; optional on-device AI review.

The hand-reasoned reference labels are not official BIAI hidden labels.
Run the baseline first; add --ai only after local Ollama model is installed.
"""
import argparse
import csv
from pathlib import Path

from .config import PROJECT_ROOT, sample_pdfs
from .workflow import analyze_sample

REFERENCE = {
    "01": "Approve", "02": "Approve", "03": "Reject", "04": "Needs a person to check",
    "05": "Reject", "06": "Reject", "07": "Needs a person to check",
    "08": "Reject", "09": "Needs a person to check", "10": "Reject",
}


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Compare supplier decisions with manual reference labels")
    p.add_argument("--ai", action="store_true", help="Run optional LOCAL Ollama review on ALL 10 sample PDFs")
    p.add_argument("--model", default="qwen2.5:1.5b", help="Locally installed model name (no cloud models)")
    p.add_argument("--timeout", type=int, default=150, help="Seconds to wait per local AI call")
    args = p.parse_args(argv)
    results = [analyze_sample(path, use_ai=args.ai, ai_model=args.model, ai_timeout=args.timeout) for path in sample_pdfs()]
    output = PROJECT_ROOT / ("evaluation-ai-results.csv" if args.ai else "evaluation-results.csv")
    correct = 0
    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["document", "prediction", "reference", "match", "findings", "ai_status", "ai_supported_observations", "ai_discarded", "ai_model_only_uncertainty", "ai_seconds"])
        for result in results:
            case = Path(result.filename).stem.split("-")[-1]
            expected = REFERENCE[case]
            match = result.decision == expected
            correct += match
            review = result.ai_review
            writer.writerow([
                result.filename, result.decision, expected, match,
                "; ".join(x.rule for x in result.findings),
                review.status if review else "not requested",
                len(review.observations) if review else 0,
                review.ungrounded_count if review else 0,
                review.model_only_count if review else 0,
                round(review.elapsed_seconds, 2) if review else 0,
            ])
            print(f"{result.filename:22}  {result.decision:25}  {'MATCH' if match else 'DIFF'}" + (f"  AI:{review.status}" if review else ""), flush=True)
    print(f"\nAgreement with independently reasoned reference labels: {correct}/{len(results)}")
    print(f"Results CSV: {output}")
    print("Reference labels are NOT an official answer key; inspect issues and exact source evidence.")


if __name__ == "__main__":
    main()
