"""Prepare a reviewable public report from CloudGuard trial JSONL files."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    files = sorted(args.input_dir.glob("*.jsonl"))
    if not files:
        parser.error("No JSONL files found in the input directory.")
    if args.output.exists():
        parser.error("Output already exists. Choose a new path.")

    trials = []
    for path in files:
        if path.stem.endswith("-explicit"):
            context = "explicit"
        elif path.stem.endswith("-distributed"):
            context = "distributed"
        else:
            context = None
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                trial = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{number} is not valid JSON") from exc
            required = {"model", "family_id", "variant_id", "status", "expected_decision"}
            if not required.issubset(trial):
                raise ValueError(f"{path}:{number} is not a CloudGuard trial record")
            metadata = trial.get("metadata") or {}
            decision = trial.get("decision") or {}
            trials.append({
                "source_file": path.name,
                "context": context,
                "model": trial["model"],
                "returned_model": metadata.get("returned_model"),
                "run_date_utc": metadata.get("started_at_utc"),
                "scenario_family": trial["family_id"],
                "variant": trial["variant_id"],
                "status": trial["status"],
                "expected_decision": trial["expected_decision"],
                "expected_rationale": trial.get("reference_rationale"),
                "model_decision": decision.get("decision"),
                "model_rationale": decision.get("rationale"),
                "error": trial.get("error"),
            })
    if not trials:
        parser.error("The JSONL files contain no trials.")
    models = {trial["model"] for trial in trials}
    if len(models) != 1:
        parser.error("Input contains multiple models. Prepare one model per report.")
    completed = [t for t in trials if t["status"] == "completed" and t["model_decision"]]
    correct = sum(t["expected_decision"] == t["model_decision"] for t in completed)
    report = {
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": next(iter(models)),
        "family_count": len({t["scenario_family"] for t in trials}),
        "trial_count": len(trials),
        "scored_trials": len(completed),
        "failed_trials": len(trials) - len(completed),
        "correct_trials": correct,
        "overall_accuracy": correct / len(completed) if completed else None,
        "trials": trials,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, ensure_ascii=False)
        output.write("\n")
    print(f"Prepared {len(trials)} trials in {args.output}")


if __name__ == "__main__":
    main()
