#!/usr/bin/env python3
"""A-12: Error Rate Dashboard - emits hourly error rate per skill."""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta

EVENTS = Path("/root/.hermes/observability/events.log")
OUTPUT = Path("/root/.hermes/observability/error_rate.json")


def main():
    if not EVENTS.exists():
        print("No events.log")
        return
    
    # Bucket by hour + skill
    buckets = defaultdict(lambda: {"total": 0, "errors": 0})
    
    with open(EVENTS) as f:
        for line in f:
            try:
                e = json.loads(line)
            except:
                continue
            ts = e.get("ts", "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except:
                continue
            hour = dt.strftime("%Y-%m-%d %H:00")
            cat = e.get("category", "unknown")
            key = f"{hour}|{cat}"
            buckets[key]["total"] += 1
            if e.get("status") == "error":
                buckets[key]["errors"] += 1
    
    # Build hourly rates
    by_hour = defaultdict(list)
    for key, v in buckets.items():
        hour, cat = key.split("|")
        rate = (v["errors"] / v["total"] * 100) if v["total"] else 0
        by_hour[hour].append({"category": cat, "total": v["total"], "errors": v["errors"], "error_rate_pct": round(rate, 2)})
    
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours": dict(sorted(by_hour.items(), reverse=True)[:24]),
    }
    OUTPUT.write_text(json.dumps(result, indent=2))
    print(f"Wrote {len(by_hour)} hours of data to {OUTPUT}")


if __name__ == "__main__":
    main()
