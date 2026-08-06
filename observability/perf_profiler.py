#!/usr/bin/env python3
"""
Performance Profiler - Measures hermes hook, tool, workflow timings.

Drop-in decorators + context managers for any Python code.

Usage:
    from perf_profiler import profile, PerfTimer

    @profile("my-tool")
    def my_tool():
        ...

    with PerfTimer("my-workflow"):
        do_work()
"""
import os
import time
import json
import functools
from datetime import datetime, timezone
from contextlib import contextmanager

PERF_FILE = "/root/.hermes/observability/perf_events.log"
PERF_STATS = "/root/.hermes/observability/perf_stats.json"


def profile(name, category=None):
    """Decorator: time a function."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            status = "ok"
            error = None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                error = str(e)[:200]
                raise
            finally:
                duration_ms = int((time.perf_counter() - start) * 1000)
                _record(name, category or fn.__module__, duration_ms, status, error)
        return wrapper
    return decorator


@contextmanager
def PerfTimer(name, category=None):
    """Context manager: time a block of code."""
    start = time.perf_counter()
    status = "ok"
    error = None
    try:
        yield
    except Exception as e:
        status = "error"
        error = str(e)[:200]
        raise
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        _record(name, category or "block", duration_ms, status, error)


def _record(name, category, duration_ms, status, error):
    """Persist perf event."""
    os.makedirs(os.path.dirname(PERF_FILE), exist_ok=True)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "name": name,
        "category": category,
        "duration_ms": duration_ms,
        "status": status,
        "error": error,
    }
    with open(PERF_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")
    _update_stats(event)


def _update_stats(event):
    """Update aggregate stats by name."""
    stats = {}
    if os.path.exists(PERF_STATS):
        try:
            stats = json.loads(open(PERF_STATS).read())
        except:
            stats = {}
    key = f"{event['category']}/{event['name']}"
    if key not in stats:
        stats[key] = {"calls": 0, "errors": 0, "total_ms": 0, "min_ms": 999999, "max_ms": 0}
    s = stats[key]
    s["calls"] += 1
    if event["status"] == "error":
        s["errors"] += 1
    s["total_ms"] += event["duration_ms"]
    s["min_ms"] = min(s["min_ms"], event["duration_ms"])
    s["max_ms"] = max(s["max_ms"], event["duration_ms"])
    s["avg_ms"] = int(s["total_ms"] / s["calls"])
    with open(PERF_STATS, "w") as f:
        f.write(json.dumps(stats, indent=2, sort_keys=True))


def get_stats(name_filter=None):
    """Read stats. Optional filter by name substring."""
    if not os.path.exists(PERF_STATS):
        return {}
    stats = json.loads(open(PERF_STATS).read())
    if name_filter:
        return {k: v for k, v in stats.items() if name_filter.lower() in k.lower()}
    return stats


if __name__ == "__main__":
    # Self-test
    @profile("test-function")
    def slow_func():
        time.sleep(0.1)
        return "done"

    with PerfTimer("test-block", "demo"):
        time.sleep(0.05)

    slow_func()
    slow_func()
    print("Stats:")
    print(json.dumps(get_stats("test"), indent=2))
