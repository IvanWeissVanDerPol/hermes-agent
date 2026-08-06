#!/usr/bin/env python3
"""Cron health dashboard."""
import json
from datetime import datetime, timezone
from pathlib import Path

JOBS_FILE = "/root/.hermes/cron/jobs.json"
OUTPUT = "/root/.hermes/cron/dashboard.json"


def collect():
    if not Path(JOBS_FILE).exists():
        return {"error": JOBS_FILE + " not found"}
    jobs = json.loads(Path(JOBS_FILE).read_text())["jobs"]

    healthy, failing, disabled, never_run = [], [], [], []
    for j in jobs:
        last_status = j.get("last_status", "unknown")
        enabled = j.get("enabled", True)
        last_run = j.get("last_run_at")
        name = j["name"]
        if not enabled:
            disabled.append(name)
        elif last_status == "ok":
            healthy.append(name)
        elif last_status == "error":
            failing.append({
                "name": name,
                "last_run": last_run,
                "last_error": (j.get("last_error") or "")[:200],
            })
        elif not last_run:
            never_run.append(name)

    total = len(jobs)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "healthy_count": len(healthy),
        "failing_count": len(failing),
        "disabled_count": len(disabled),
        "never_run_count": len(never_run),
        "failing": failing,
        "healthy_pct": round(len(healthy) / max(total, 1) * 100, 1),
        "ok": len(failing) == 0 and len(never_run) == 0,
    }


def save():
    data = collect()
    Path(OUTPUT).write_text(json.dumps(data, indent=2))
    return data


def print_summary(data):
    """Print human-readable summary."""
    status = "OK" if data["ok"] else "FAIL"
    print(status + " Cron Health: " + str(data["healthy_count"]) + "/" + str(data["total"])
          + " healthy (" + str(data["healthy_pct"]) + "%)")

    if data["failing_count"]:
        print("")
        print("Failing jobs (" + str(data["failing_count"]) + "):")
        for f in data["failing"]:
            err = f["last_error"][:80]
            last = (f["last_run"] or "never")[:10]
            print("  X " + f["name"].ljust(40) + " " + last)
            print("    err: " + err)

    if data.get("never_run_count", 0):
        print("")
        print("Never run (" + str(data["never_run_count"]) + "):")
        for n in data["never_run"][:5]:
            print("  ? " + n)
        if data["never_run_count"] > 5:
            print("  ... (" + str(data["never_run_count"] - 5) + " more)")


if __name__ == "__main__":
    data = save()
    print_summary(data)
