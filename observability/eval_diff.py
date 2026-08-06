#!/usr/bin/env python3
"""B-15: Eval Diff - compare eval results across runs."""
import json
from pathlib import Path
from datetime import datetime, timezone

EVAL_DIR = Path("/root/.hermes/state/evals")
LATEST = EVAL_DIR / "latest.json"
PREVIOUS = EVAL_DIR / "previous.json"


def main():
    if not LATEST.exists():
        print("No latest.json - nothing to diff")
        return
    
    latest = json.loads(LATEST.read_text())
    previous = {}
    if PREVIOUS.exists():
        previous = json.loads(PREVIOUS.read_text())
    
    # Diff
    diff = {}
    for k, v in latest.items():
        if k in previous:
            if isinstance(v, (int, float)):
                diff[k] = {"old": previous[k], "new": v, "delta": v - previous[k]}
        else:
            diff[k] = {"old": "new", "new": v, "delta": "added"}
    
    print(f"Diffs: {len(diff)}")
    for k, v in diff.items():
        if isinstance(v.get("delta"), (int, float)):
            print(f"  {k}: {v['old']} → {v['new']} (Δ {v['delta']:+.2f})")
        else:
            print(f"  {k}: {v['old']} → {v['new']} ({v['delta']})")


if __name__ == "__main__":
    main()
