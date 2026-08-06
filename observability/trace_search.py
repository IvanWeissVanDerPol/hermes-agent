#!/usr/bin/env python3
"""A-15: Trace Search CLI - search traces by skill/repo/model."""
import json
import sys
from pathlib import Path

TRACES = Path("/root/.hermes/observability/traces.log")


def search(query):
    """query format: 'skill:X repo:Y model:Z' (all optional)"""
    filters = {}
    for part in query.split():
        if ":" in part:
            k, v = part.split(":", 1)
            filters[k] = v
    
    if not TRACES.exists():
        print("No traces.log")
        return
    
    results = []
    with open(TRACES) as f:
        for line in f:
            try:
                e = json.loads(line)
            except:
                continue
            match = True
            for k, v in filters.items():
                if str(e.get(k, "")) != v:
                    match = False
                    break
            if match:
                results.append(e)
    
    print(f"Found {len(results)} matches")
    for e in results[-10:]:
        print(f"  {e.get('ts', '?')} {e.get('skill', '?')} {e.get('model', '?')} {e.get('status', '?')}")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    search(q)
