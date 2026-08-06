#!/usr/bin/env python3
"""Observability wrapper - drop-in decorator for any script."""
import sys, os, functools, json
from datetime import datetime, timezone

OBS_DIR = "/root/.hermes/observability"
EVENTS_LOG = os.path.join(OBS_DIR, "events.log")


def track(category, name, payload=None, status="ok", duration_ms=None):
    """Track a custom event."""
    os.makedirs(OBS_DIR, exist_ok=True)
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "category": category,
        "name": name,
        "status": status,
        "duration_ms": duration_ms,
        "payload": payload or {},
    }
    with open(EVENTS_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def observe(category=None):
    """Decorator: track function calls."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            cat = category or fn.__module__
            import time
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
                track(cat, fn.__name__,
                      payload={"args": str(args)[:200], "kwargs": str(kwargs)[:200]},
                      status=status, duration_ms=duration_ms)
                if error:
                    pass  # could push to langfuse here
        return wrapper
    return decorator


# Self-test
if __name__ == "__main__":
    @observe("test")
    def hello(name):
        return f"hi {name}"

    hello("world")
    hello("obs")
    print(f"Logged to {EVENTS_LOG}")
