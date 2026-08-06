#!/usr/bin/env python3
"""A-10: Model Latency Tracker - p50/p95/p99 per model."""
import json
from pathlib import Path
from collections import defaultdict

TRACES = Path("/root/.hermes/observability/traces.log")
OUTPUT = Path("/root/.hermes/observability/latency_stats.json")


def main():
    if not TRACES.exists():
        print("No traces.log")
        return
    
    by_model = defaultdict(list)
    with open(TRACES) as f:
        for line in f:
            try:
                e = json.loads(line)
                if "latency_ms" in e:
                    by_model[e.get("model", "unknown")].append(e["latency_ms"])
            except:
                continue
    
    result = {}
    for model, lats in by_model.items():
        if not lats:
            continue
        lats_sorted = sorted(lats)
        n = len(lats_sorted)
        p50 = lats_sorted[n // 2]
        p95 = lats_sorted[int(n * 0.95)] if n > 1 else lats_sorted[0]
        p99 = lats_sorted[int(n * 0.99)] if n > 1 else lats_sorted[0]
        result[model] = {
            "samples": n,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "max_ms": max(lats),
        }
    
    OUTPUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
