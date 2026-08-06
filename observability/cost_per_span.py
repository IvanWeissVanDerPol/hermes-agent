#!/usr/bin/env python3
"""A-16: Cost Per Span - tag each span with model+tokens+cost."""
import json
from pathlib import Path
from collections import defaultdict

TRACES = Path("/root/.hermes/observability/traces.log")
OUTPUT = Path("/root/.hermes/observability/cost_per_span.json")

# Cost per 1k tokens (approximate)
COST_PER_1K = {
    "deepseek-chat": 0.00014,
    "gpt-oss-120b": 0.0002,
    "claude-sonnet-4-6": 0.003,
    "MiniMax-M3": 0.0001,
}


def estimate_cost(model, tokens):
    rate = COST_PER_1K.get(model, 0.0001)
    return (tokens / 1000) * rate


def main():
    if not TRACES.exists():
        print("No traces.log")
        return
    
    by_model = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost_usd": 0.0})
    with open(TRACES) as f:
        for line in f:
            try:
                e = json.loads(line)
            except:
                continue
            model = e.get("model", "unknown")
            tokens = e.get("total_tokens", 0)
            cost = estimate_cost(model, tokens)
            by_model[model]["calls"] += 1
            by_model[model]["tokens"] += tokens
            by_model[model]["cost_usd"] = round(by_model[model]["cost_usd"] + cost, 6)
    
    OUTPUT.write_text(json.dumps(dict(by_model), indent=2))
    total = sum(v["cost_usd"] for v in by_model.values())
    print(f"Total cost: ${total:.4f}")
    for model, v in by_model.items():
        print(f"  {model}: {v['calls']} calls, {v['tokens']} tokens, ${v['cost_usd']:.4f}")


if __name__ == "__main__":
    main()
