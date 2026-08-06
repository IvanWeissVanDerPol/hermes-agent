#!/usr/bin/env python3
"""A-11: Cron Performance Monitor - tracks how long each cron takes."""
import json
from pathlib import Path
from datetime import datetime, timezone

JOBS = Path("/root/.hermes/cron/jobs.json")
OUTPUT = Path("/root/.hermes/observability/cron_performance.json")


def main():
    if not JOBS.exists():
        print("No jobs.json")
        return
    
    data = json.loads(JOBS.read_text())
    perf = {}
    
    for job in data.get("jobs", []):
        name = job.get("name", "unknown")
        # Look at last_run_at and last_status
        perf[name] = {
            "schedule": job.get("schedule_display", "?"),
            "last_run_at": job.get("last_run_at"),
            "last_status": job.get("last_status"),
            "enabled": job.get("enabled", True),
        }
    
    # Aggregate
    total = len(perf)
    ok = sum(1 for j in perf.values() if j["last_status"] == "ok")
    err = sum(1 for j in perf.values() if j["last_status"] == "error")
    
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {"total": total, "ok": ok, "error": err, "health_pct": round(100 * ok / total, 1) if total else 0},
        "jobs": perf,
    }
    
    OUTPUT.write_text(json.dumps(result, indent=2))
    print(f"Total: {total}, OK: {ok}, Error: {err}, Health: {result['totals']['health_pct']}%")


if __name__ == "__main__":
    main()
