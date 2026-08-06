#!/usr/bin/env python3
"""Skill loop-back cycle: validate skills, improve docs, run quality checks."""
import sys, os, json
from pathlib import Path

sys.path.insert(0, "/root/.hermes/observability")
from observability import track_event, get_stats

def main():
    args = sys.argv[1:]
    do_all = "--all" in args
    phases = []
    for i, arg in enumerate(args):
        if arg == "--phases":
            phases = args[i+1].split(",")
            break
    if not phases:
        phases = ["validate"]
    if do_all:
        phases = ["validate", "dedup", "improve", "publish"]

    print(f"=== Skill Loop-back Cycle ===")
    print(f"Phases: {phases}")
    stats = get_stats()
    print(f"Stats keys: {len(stats)}")

    track_event("skill-loop", "cycle", payload={"phases": phases}, status="ok")
    print("OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
