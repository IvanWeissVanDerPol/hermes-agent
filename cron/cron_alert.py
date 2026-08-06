#!/usr/bin/env python3
"""
Cron health alerter - monitors cron dashboard + sends alert when failures detected.

Run this periodically (every 5-15 min). Only sends alerts when state changes
(healthy -> failing OR failing count increases).
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, "/root/.hermes/observability")
from alert_router import alert

DASHBOARD = Path("/root/.hermes/cron/dashboard.json")
STATE_FILE = Path("/root/.hermes/cron/.alert_state.json")


def get_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    if not DASHBOARD.exists():
        print("cron dashboard not found")
        return 0
    
    data = json.loads(DASHBOARD.read_text())
    failing = data.get("failing", [])
    failing_count = len(failing)
    total = data.get("total", 0)
    
    state = get_state()
    last_failing_count = state.get("last_failing_count", 0)
    last_alert_at = state.get("last_alert_at")
    
    if failing_count == 0 and last_failing_count == 0:
        print(f"All {total} crons healthy. No alert needed.")
        return 0
    
    # Only alert on changes
    if failing_count > last_failing_count or (failing_count > 0 and not last_alert_at):
        names = ", ".join(f["name"] for f in failing[:5])
        msg = f"{failing_count}/{total} cron jobs failing: {names}"
        if failing_count > 5:
            msg += f" (+{failing_count - 5} more)"
        
        level = "critical" if failing_count >= 5 else "warning"
        result = alert(msg, level=level, context={"failing": failing})
        print(f"Alert sent ({level}): {msg}")
        print(f"Result: {json.dumps(result, indent=2)}")
        
        state["last_alert_at"] = __import__("datetime").datetime.now().isoformat()
    else:
        print(f"{failing_count} failing, {last_failing_count} last time - no new alert")
    
    state["last_failing_count"] = failing_count
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
