#!/usr/bin/env python3
"""
Unified Observability Library - Combines Langfuse + LLM Tracer + Perf Profiler.
Import this in any hermes script to get full observability.
"""
import os
import sys
import json
import time
from datetime import datetime, timezone

# Local imports
sys.path.insert(0, os.path.dirname(__file__))
from llm_tracer import traced_llm_call, TRACES_FILE as LLM_LOG
from perf_profiler import profile, PerfTimer, get_stats
try:
    from langfuse_client import LangfuseTrace
except ImportError:
    LangfuseTrace = None


__all__ = ["traced_llm_call", "profile", "PerfTimer", "get_stats",
           "LangfuseTrace", "track_event", "DashboardCollector"]


def track_event(category, name, payload=None, duration_ms=None, status="ok"):
    """Track a custom event in the observability log."""
    os.makedirs("/root/.hermes/observability", exist_ok=True)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "name": name,
        "status": status,
        "duration_ms": duration_ms,
        "payload": payload or {},
    }
    log_file = "/root/.hermes/observability/events.log"
    with open(log_file, "a") as f:
        f.write(json.dumps(event) + "\n")


class DashboardCollector:
    """Aggregates all observability data into a single dashboard JSON."""
    DASHBOARD = "/root/.hermes/observability/dashboard.json"

    def __init__(self):
        self.start = time.time()

    def collect(self):
        """Build a dashboard from all logs + stats."""
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": int(time.time() - self.start),
            "llm": self._llm_stats(),
            "perf": self._perf_stats(),
            "events": self._event_count(),
            "traces": self._trace_count(),
        }

    def _llm_stats(self):
        if not os.path.exists("/root/.hermes/observability/llm_stats.json"):
            return {}
        try:
            return json.loads(open("/root/.hermes/observability/llm_stats.json").read())
        except:
            return {}

    def _perf_stats(self):
        if not os.path.exists("/root/.hermes/observability/perf_stats.json"):
            return {}
        try:
            return json.loads(open("/root/.hermes/observability/perf_stats.json").read())
        except:
            return {}

    def _event_count(self):
        if not os.path.exists("/root/.hermes/observability/events.log"):
            return 0
        n = 0
        with open("/root/.hermes/observability/events.log") as f:
            for _ in f:
                n += 1
        return n

    def _trace_count(self):
        for log_name in ["traces.log", "llm_traces.log"]:
            path = f"/root/.hermes/observability/{log_name}"
            if os.path.exists(path):
                n = 0
                with open(path) as f:
                    for _ in f:
                        n += 1
                return n
        return 0

    def save(self):
        """Save dashboard to file."""
        data = self.collect()
        with open(self.DASHBOARD, "w") as f:
            json.dump(data, f, indent=2)
        return data


if __name__ == "__main__":
    # Demo
    dc = DashboardCollector()
    dc.track_event("demo", "test", payload={"key": "value"}) if False else None

    @profile("demo-tool")
    def tool():
        time.sleep(0.01)

    tool()
    tool()

    dashboard = dc.save()
    print(json.dumps(dashboard, indent=2)[:1500])
