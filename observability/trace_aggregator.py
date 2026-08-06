#!/usr/bin/env python3
"""A-3: Trace Aggregator - rolls up spans by skill+model+repo."""
import json
import sys
from collections import defaultdict
from pathlib import Path

TRACES_LOG = Path("/root/.hermes/observability/traces.log")
OUTPUT = Path("/root/.hermes/observability/trace_aggregates.json")


def aggregate():
    if not TRACES_LOG.exists():
        print("No traces.log found")
        return None
    
    by_skill = defaultdict(lambda: {"calls": 0, "tokens": 0, "errors": 0})
    by_model = defaultdict(lambda: {"calls": 0, "tokens": 0, "errors": 0})
    by_repo = defaultdict(lambda: {"calls": 0, "tokens": 0, "errors": 0})
    
    with open(TRACES_LOG) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except:
                continue
            skill = entry.get("skill", "unknown")
            model = entry.get("model", "unknown")
            repo = entry.get("repo", "unknown")
            tokens = entry.get("total_tokens", 0)
            error = entry.get("status", "ok") != "ok"
            
            for k, v in [(skill, by_skill), (model, by_model), (repo, by_repo)]:
                v[k]["calls"] += 1
                v[k]["tokens"] += tokens
                if error:
                    v[k]["errors"] += 1
    
    result = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "by_skill": dict(by_skill),
        "by_model": dict(by_model),
        "by_repo": dict(by_repo),
    }
    OUTPUT.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    result = aggregate()
    if result:
        print(json.dumps(result, indent=2)[:500])
        print(f"
Saved to {OUTPUT}")
