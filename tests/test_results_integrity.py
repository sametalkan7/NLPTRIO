
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "nlptrio_results"

with open(RESULTS / "baseline_summary.json", encoding="utf-8") as f:
    baseline = json.load(f)

with open(RESULTS / "berturk_runs.json", encoding="utf-8") as f:
    pilot = json.load(f)

assert baseline, "Baseline results must not be empty"
assert pilot, "BERTurk pilot results must not be empty"

print("Results files exist and contain data.")
